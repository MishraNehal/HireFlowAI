"""
Resume parser service -- turns a raw resume PDF into structured candidate
data.

Two-stage pipeline:
    1. extract_text_from_pdf(): PyMuPDF pulls raw text out of the PDF.
       Purely mechanical, no LLM involved, so it's fast and free.
    2. parse_resume_with_llm(): Groq reads that raw text and returns a
       structured JSON profile (skills, education, experience, projects,
       certifications, contact info) -- this is the step that needs
       judgment, since resumes have no consistent format.

This module does not touch the database or Supabase Storage -- it's a pure
text-in, dict-out service. resume_intelligence_agent (Task 4.3) is
responsible for downloading the PDF bytes and persisting the result.
"""
import asyncio
import logging

import fitz  # PyMuPDF

from app.services.llm import call_llm_json

logger = logging.getLogger(__name__)

MAX_RAW_TEXT_CHARS = 15000


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract plain text from a PDF's raw bytes using PyMuPDF."""
    if not file_bytes:
        raise ValueError("file_bytes must be non-empty")

    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as e:
        raise ValueError(f"Could not open file as a PDF: {e}") from e

    try:
        pages_text = []
        for page in doc:
            page_text = page.get_text().strip()
            if page_text:
                pages_text.append(page_text)
        text = "\n\n".join(pages_text)
    finally:
        doc.close()

    text = _clean_extracted_text(text)

    if not text.strip():
        raise ValueError(
            "No extractable text found in PDF. It may be a scanned image "
            "without an OCR text layer."
        )

    if len(text) > MAX_RAW_TEXT_CHARS:
        text = text[:MAX_RAW_TEXT_CHARS]
        logger.warning(
            "Extracted resume text truncated to %d chars (was longer).",
            MAX_RAW_TEXT_CHARS,
        )

    return text


async def parse_resume_with_llm(raw_text: str) -> dict:
    """Send extracted resume text to Groq and get back a structured profile."""
    if not raw_text or not raw_text.strip():
        raise ValueError("raw_text must be non-empty")

    system = (
        "You are an expert resume parser. Extract structured information "
        "from resume text accurately. Do not invent information that "
        "isn't present in the text. Respond ONLY with valid JSON, no "
        "markdown, no explanation, no code fences."
    )

    prompt = f"""Extract structured data from this resume text.

Resume text:
\"\"\"
{raw_text}
\"\"\"

Return ONLY valid JSON in exactly this shape (use empty string "" for
missing text fields and empty list [] for missing list fields -- never
omit a key, never invent data not present in the resume):

{{
  "name": "<full name>",
  "email": "<email address>",
  "phone": "<phone number>",
  "skills": ["<skill1>", "<skill2>", ...],
  "education": [
    {{"degree": "<e.g. B.Tech Computer Science>", "institution": "<college/university name>", "year": "<graduation year>", "cgpa": "<CGPA or percentage as a string>"}}
  ],
  "experience": [
    {{"company": "<company name>", "role": "<job title>", "duration": "<e.g. Jun 2023 - Aug 2023>", "description": "<brief summary of responsibilities>"}}
  ],
  "projects": [
    {{"name": "<project name>", "tech_stack": "<comma-separated technologies used>", "description": "<brief summary>"}}
  ],
  "certifications": ["<certification1>", "<certification2>", ...]
}}

For each project's "tech_stack": list every technology, language, framework,
library, or tool actually used to build it. Read the FULL project title and
description carefully -- technologies are very often named inside them even
when there's no separate "Tech Stack:" label (e.g. a project titled
"Multi-PDF Chatbot (LangChain + FAISS + Gemini 1.5 Flash)" should produce
tech_stack: "LangChain, FAISS, Gemini 1.5 Flash"; a description mentioning
"built with FastAPI and PostgreSQL" should produce tech_stack: "FastAPI,
PostgreSQL"). Only leave tech_stack as "" if the project genuinely gives no
technical detail whatsoever.

Include internships under "experience", not "projects". If a resume section
truly isn't present, return an empty list/string for it rather than guessing."""

    result = await asyncio.to_thread(call_llm_json, prompt, system=system, temperature=0.1)
    return _validate_and_normalize(result)


# -- Internal helpers ---------------------------------------------------------

_EXPECTED_STRING_FIELDS = ("name", "email", "phone")
_EXPECTED_LIST_FIELDS = ("skills", "education", "experience", "projects", "certifications")
_EDUCATION_SUBFIELDS = ("degree", "institution", "year", "cgpa")
_EXPERIENCE_SUBFIELDS = ("company", "role", "duration", "description")
_PROJECT_SUBFIELDS = ("name", "tech_stack", "description")


def _validate_and_normalize(result: dict) -> dict:
    normalized: dict = {}

    for field in _EXPECTED_STRING_FIELDS:
        value = result.get(field)
        normalized[field] = str(value).strip() if value and str(value).strip().lower() != "n/a" else ""

    for field in _EXPECTED_LIST_FIELDS:
        value = result.get(field)
        normalized[field] = value if isinstance(value, list) else []

    normalized["skills"] = [str(s).strip() for s in normalized["skills"] if s and str(s).strip()]
    normalized["certifications"] = [
        str(c).strip() for c in normalized["certifications"] if c and str(c).strip()
    ]

    normalized["education"] = [
        _normalize_subdict(entry, _EDUCATION_SUBFIELDS)
        for entry in normalized["education"] if isinstance(entry, dict)
    ]
    normalized["experience"] = [
        _normalize_subdict(entry, _EXPERIENCE_SUBFIELDS)
        for entry in normalized["experience"] if isinstance(entry, dict)
    ]
    normalized["projects"] = [
        _normalize_subdict(entry, _PROJECT_SUBFIELDS)
        for entry in normalized["projects"] if isinstance(entry, dict)
    ]

    return normalized


def _normalize_subdict(entry: dict, expected_fields: tuple) -> dict:
    return {field: str(entry.get(field, "") or "").strip() for field in expected_fields}


def _clean_extracted_text(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    cleaned_lines = []
    blank_run = 0
    for line in lines:
        if line == "":
            blank_run += 1
            if blank_run > 1:
                continue
        else:
            blank_run = 0
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()