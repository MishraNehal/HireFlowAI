import json
import logging
import re
from typing import List, Dict, Any
from app.services.client import nexus_client

logger = logging.getLogger("hireflow.jd_generator")


def generate_job_description(
    company_name: str,
    role_name: str,
    skills_required: List[str],
    experience_level: str,
    num_openings: int,
    additional_context: str = ""
) -> Dict[str, Any]:
    """
    Generates a professional Job Description using the Nexus LLM.
    Returns a structured dict with all JD sections.
    """
    system_prompt = (
        "You are a senior HR consultant and technical writer. Generate a professional, detailed, "
        "and compelling Job Description for the given hiring requirements.\n\n"
        "Return a JSON object with these exact keys:\n"
        "- 'job_title': Official job title (string)\n"
        "- 'company_overview': 2-3 sentence company introduction (string)\n"
        "- 'responsibilities': List of 6-8 key responsibilities (list of strings)\n"
        "- 'required_skills': List of must-have technical skills (list of strings)\n"
        "- 'preferred_skills': List of nice-to-have skills (list of strings)\n"
        "- 'eligibility_criteria': Educational and experience requirements (string)\n"
        "- 'hiring_process': Ordered list of hiring stages (list of strings)\n"
        "- 'perks': List of 4-5 benefits/perks (list of strings)\n\n"
        "CRITICAL: Return ONLY valid JSON. No markdown, no backticks, no commentary."
    )

    user_content = (
        f"Company: {company_name}\n"
        f"Role: {role_name}\n"
        f"Required Skills: {', '.join(skills_required)}\n"
        f"Experience Level: {experience_level}\n"
        f"Number of Openings: {num_openings}\n"
        f"Additional Context: {additional_context or 'None'}\n"
    )

    try:
        response_text = nexus_client.generate_prompt(system_prompt, user_content, temperature=0.4)
        cleaned_text = response_text.strip()
        if cleaned_text.startswith("```"):
            cleaned_text = re.sub(r"^```(?:json)?\n", "", cleaned_text)
            cleaned_text = re.sub(r"\n```$", "", cleaned_text)

        parsed = json.loads(cleaned_text.strip())

        # Normalize keys
        return {
            "job_title": parsed.get("job_title", f"{role_name} at {company_name}"),
            "company_overview": parsed.get("company_overview", ""),
            "responsibilities": parsed.get("responsibilities", []),
            "required_skills": parsed.get("required_skills", skills_required),
            "preferred_skills": parsed.get("preferred_skills", []),
            "eligibility_criteria": parsed.get("eligibility_criteria", ""),
            "hiring_process": parsed.get("hiring_process", ["Resume Screening", "Technical Interview", "HR Round", "Offer"]),
            "perks": parsed.get("perks", []),
        }

    except Exception as e:
        logger.error(f"JD generation failed: {str(e)}")
        return get_fallback_jd(company_name, role_name, skills_required, experience_level, num_openings)


def get_fallback_jd(
    company_name: str,
    role_name: str,
    skills_required: List[str],
    experience_level: str,
    num_openings: int
) -> Dict[str, Any]:
    """Returns a basic fallback JD structure when LLM fails."""
    logger.info("Using fallback JD structure.")
    return {
        "job_title": f"{role_name}",
        "company_overview": f"{company_name} is a dynamic organization seeking talented professionals to join its team.",
        "responsibilities": [
            f"Develop and maintain solutions using {', '.join(skills_required[:3])}",
            "Collaborate with cross-functional teams on product development",
            "Participate in code reviews and technical discussions",
            "Contribute to documentation and best practices",
            "Troubleshoot and resolve technical issues",
        ],
        "required_skills": skills_required,
        "preferred_skills": ["Git", "Agile/Scrum", "Communication skills"],
        "eligibility_criteria": f"Experience level: {experience_level}. Relevant educational background preferred.",
        "hiring_process": [
            "Resume Screening",
            "Technical Assessment",
            "Technical Interview",
            "HR Interview",
            "Offer"
        ],
        "perks": [
            "Competitive salary",
            "Learning and development opportunities",
            "Flexible working hours",
            "Health benefits",
        ],
    }
