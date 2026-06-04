import fitz  # PyMuPDF
import json
import re
import logging
from typing import Dict, Any, List
from app.services.client import nexus_client

logger = logging.getLogger("hireflow.parser")

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extracts raw text from a PDF file using PyMuPDF."""
    text = ""
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            text += page.get_text()
        doc.close()
    except Exception as e:
        logger.error(f"Error opening or reading PDF file {pdf_path}: {str(e)}")
        raise e
    return text

def parse_resume_content(text_content: str) -> Dict[str, Any]:
    """
    Parses key entities from resume text using fast regex heuristics.
    LLM-based parsing is skipped here because it requires a valid API key
    and adds 10-30s latency that causes upload timeouts.
    Accurate AI-based extraction happens during the evaluation step instead.
    """
    logger.info("Using fast regex parser for resume upload.")
    return fallback_regex_parser(text_content)

def fallback_regex_parser(text: str) -> Dict[str, Any]:
    """Fast regex heuristic parser — runs in <5ms, no LLM needed."""
    logger.info("Using regex fallback parser.")
    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
    phone_match = re.search(r"[\+\(]?\d[\d\s\-\(\)]{7,}\d", text)

    # Extract name: look for the first 1-3 word line that is NOT a common header
    SKIP_WORDS = {"resume", "curriculum", "vitae", "cv", "profile", "summary", "objective",
                  "experience", "education", "skills", "contact", "references", "projects"}
    name = "Unknown Candidate"
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    for line in lines[:10]:
        words = line.split()
        if 1 <= len(words) <= 4 and not any(w.lower() in SKIP_WORDS for w in words):
            # Looks like a name — mostly alphabetic, reasonably short
            if sum(c.isalpha() or c in " .-" for c in line) / max(len(line), 1) > 0.7:
                name = line.title()
                break

    # Extract known tech skills by keyword scan
    TECH_KEYWORDS = [
        "Python", "Java", "JavaScript", "TypeScript", "React", "Node.js", "FastAPI",
        "Django", "Flask", "SQL", "MySQL", "PostgreSQL", "MongoDB", "Redis", "Docker",
        "Kubernetes", "AWS", "GCP", "Azure", "Git", "REST", "GraphQL", "TensorFlow",
        "PyTorch", "Machine Learning", "Deep Learning", "NLP", "Data Science", "Pandas",
        "NumPy", "Scikit-learn", "C++", "C#", "Golang", "Rust", "HTML", "CSS",
        "Vue", "Angular", "Spring", "Kafka", "Spark", "Hadoop", "Linux", "Bash"
    ]
    found_skills = [kw for kw in TECH_KEYWORDS if re.search(rf"\b{re.escape(kw)}\b", text, re.IGNORECASE)]

    # Estimate years of experience from text patterns like "2 years", "3+ years"
    exp_matches = re.findall(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b", text, re.IGNORECASE)
    experience_years = max((float(x) for x in exp_matches), default=0.0)

    return {
        "name": name,
        "email": email_match.group(0) if email_match else "",
        "phone": phone_match.group(0).strip() if phone_match else None,
        "skills": found_skills,
        "experience_years": experience_years,
        "experience_summary": "Parsed via fast heuristic extraction.",
    }

def parse_resume(pdf_path: str) -> Dict[str, Any]:
    """Main function to parse resume from file path."""
    text_content = extract_text_from_pdf(pdf_path)
    parsed = parse_resume_content(text_content)
    parsed["resume_text"] = text_content
    parsed["parsed_skills"] = parsed.get("skills", [])
    return parsed

