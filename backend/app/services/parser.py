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
    Sends the extracted resume text to the Nexus LLM to parse key entities in a reliable JSON structure.
    """
    system_prompt = (
        "You are an expert resume parser AI. Analyze the resume text and return a JSON object with the following fields:\n"
        "1. 'name': Full name of the candidate (string)\n"
        "2. 'email': Email address (string)\n"
        "3. 'phone': Phone number if found (string or null)\n"
        "4. 'skills': A list of key technical skills (list of strings)\n"
        "5. 'experience_years': Estimated total years of professional experience (float)\n"
        "6. 'experience_summary': A brief paragraph summarizing their work history and projects (string)\n\n"
        "CRITICAL: Return ONLY a valid JSON object. Do not include markdown code block markers (like ```json) or any conversational text. "
        "Validate that the JSON is fully parsable."
    )

    try:
        response_text = nexus_client.generate_prompt(system_prompt, text_content)
        # Clean response if markdown blocks are accidentally returned
        cleaned_text = response_text.strip()
        if cleaned_text.startswith("```"):
            cleaned_text = re.sub(r"^```(?:json)?\n", "", cleaned_text)
            cleaned_text = re.sub(r"\n```$", "", cleaned_text)
        
        parsed_data = json.loads(cleaned_text.strip())
        
        # Validate data types
        parsed_data["name"] = parsed_data.get("name", "Unknown Candidate")
        parsed_data["email"] = parsed_data.get("email", "")
        parsed_data["phone"] = parsed_data.get("phone", None)
        parsed_data["skills"] = parsed_data.get("skills", [])
        if not isinstance(parsed_data["skills"], list):
            parsed_data["skills"] = []
        try:
            parsed_data["experience_years"] = float(parsed_data.get("experience_years", 0.0))
        except (ValueError, TypeError):
            parsed_data["experience_years"] = 0.0
            
        parsed_data["experience_summary"] = parsed_data.get("experience_summary", "")
        return parsed_data
        
    except Exception as e:
        logger.error(f"JSON parsing failed or Nexus client failed. Error: {str(e)}")
        # Fallback heuristic parser if LLM/JSON fails
        return fallback_regex_parser(text_content)

def fallback_regex_parser(text: str) -> Dict[str, Any]:
    """Fallback parser using regex heuristics if LLM or JSON output fails."""
    logger.info("Using regex fallback parser.")
    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
    phone_match = re.search(r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", text)
    
    # Try to extract first line as name
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    name = lines[0] if lines else "Unknown Candidate"
    
    return {
        "name": name,
        "email": email_match.group(0) if email_match else "",
        "phone": phone_match.group(0) if phone_match else None,
        "skills": [],
        "experience_years": 0.0,
        "experience_summary": "Heuristic fallback parse."
    }

def parse_resume(pdf_path: str) -> Dict[str, Any]:
    """Main function to parse resume from file path."""
    text_content = extract_text_from_pdf(pdf_path)
    parsed = parse_resume_content(text_content)
    parsed["resume_text"] = text_content
    parsed["parsed_skills"] = parsed.get("skills", [])
    return parsed

