import json
import logging
import re
from typing import Dict, Any, List, Optional
from app.services.client import nexus_client

logger = logging.getLogger("hireflow.offer")


def generate_offer_letter(
    candidate_name: str,
    job_role: str,
    company_name: str,
    start_date: Optional[str] = None,
    salary_range: Optional[str] = None,
    additional_notes: Optional[str] = None,
) -> str:
    """
    Generates a professional offer letter draft for a selected candidate.
    Returns the offer letter as plain text.
    """
    system_prompt = (
        "You are an experienced HR professional drafting formal offer letters. "
        "Generate a professional, warm, and complete offer letter. "
        "Include: salutation, congratulatory opening, role details, start date, key responsibilities summary, "
        "compensation (use the given range or write TBD), benefits mention, signing deadline, and closing. "
        "Format it as a proper business letter. Return only the letter text, no JSON."
    )

    user_content = (
        f"Candidate Name: {candidate_name}\n"
        f"Job Role: {job_role}\n"
        f"Company Name: {company_name}\n"
        f"Start Date: {start_date or 'To be confirmed'}\n"
        f"Salary/Compensation: {salary_range or 'As per company standards'}\n"
    )
    if additional_notes:
        user_content += f"Additional Notes/Clauses: {additional_notes}\n"

    try:
        letter_text = nexus_client.generate_prompt(system_prompt, user_content, temperature=0.5)
        return letter_text.strip()
    except Exception as e:
        logger.error(f"Offer letter generation failed: {str(e)}")
        return _fallback_offer_letter(candidate_name, job_role, company_name, start_date)


def _fallback_offer_letter(
    candidate_name: str,
    job_role: str,
    company_name: str,
    start_date: Optional[str]
) -> str:
    """Returns a minimal fallback offer letter."""
    date_line = start_date or "a mutually agreed date"
    return f"""Dear {candidate_name},

We are delighted to extend this offer of employment for the position of {job_role} at {company_name}.

After a thorough evaluation of your qualifications and interviews, we are confident that you will be a valuable addition to our team.

ROLE DETAILS:
- Position: {job_role}
- Company: {company_name}
- Start Date: {date_line}
- Employment Type: Full-Time

COMPENSATION:
Your compensation package will be discussed and confirmed separately by our HR team.

NEXT STEPS:
Please review this offer and confirm your acceptance within 5 business days. If you have any questions, do not hesitate to reach out to our HR team.

We look forward to welcoming you to the {company_name} family.

Warm regards,

HR Department
{company_name}
"""


def generate_onboarding_checklist(
    candidate_name: str,
    job_role: str,
    company_name: str,
) -> List[Dict[str, Any]]:
    """
    Generates a structured onboarding checklist for a new hire.
    Returns a list of task objects with category and description.
    """
    system_prompt = (
        "You are an HR onboarding specialist. Generate a comprehensive onboarding checklist for a new employee. "
        "Return a JSON array of task objects. Each task must have:\n"
        "- 'category': one of 'Documents', 'IT Setup', 'HR Formalities', 'Orientation', 'Role-Specific'\n"
        "- 'task': Short task name (string)\n"
        "- 'description': Brief explanation of what to do (string)\n"
        "- 'priority': 'High', 'Medium', or 'Low'\n\n"
        "Generate 12-15 items covering all categories. "
        "CRITICAL: Return ONLY a valid JSON array. No markdown, no backticks."
    )

    user_content = (
        f"New Hire: {candidate_name}\n"
        f"Role: {job_role}\n"
        f"Company: {company_name}\n"
    )

    try:
        response_text = nexus_client.generate_prompt(system_prompt, user_content, temperature=0.3)
        cleaned_text = response_text.strip()
        if cleaned_text.startswith("```"):
            cleaned_text = re.sub(r"^```(?:json)?\n", "", cleaned_text)
            cleaned_text = re.sub(r"\n```$", "", cleaned_text)

        checklist = json.loads(cleaned_text.strip())
        if isinstance(checklist, list):
            return checklist
        return _fallback_checklist(job_role)

    except Exception as e:
        logger.error(f"Onboarding checklist generation failed: {str(e)}")
        return _fallback_checklist(job_role)


def _fallback_checklist(job_role: str) -> List[Dict[str, Any]]:
    """Returns standard fallback onboarding checklist."""
    return [
        {"category": "Documents", "task": "Submit Aadhaar Card", "description": "Provide a scanned copy of your Aadhaar card for KYC verification.", "priority": "High"},
        {"category": "Documents", "task": "Submit PAN Card", "description": "Required for payroll and tax filing purposes.", "priority": "High"},
        {"category": "Documents", "task": "Submit Educational Certificates", "description": "Originals for verification: Degree, Marksheets.", "priority": "High"},
        {"category": "HR Formalities", "task": "Sign Offer Letter", "description": "Sign and return the accepted offer letter within the deadline.", "priority": "High"},
        {"category": "HR Formalities", "task": "Complete HR Forms", "description": "Fill the employee information form, PF nomination form, and bank details form.", "priority": "High"},
        {"category": "HR Formalities", "task": "Background Verification Consent", "description": "Sign the background check authorization form.", "priority": "Medium"},
        {"category": "IT Setup", "task": "Laptop/Equipment Issuance", "description": "Collect your assigned laptop and accessories from the IT team.", "priority": "High"},
        {"category": "IT Setup", "task": "Company Email Setup", "description": "Activate your company email and set up 2FA.", "priority": "High"},
        {"category": "IT Setup", "task": "Access Provisioning", "description": "Request access to required tools: Slack, Jira, GitHub, etc.", "priority": "Medium"},
        {"category": "Orientation", "task": "Attend Company Orientation", "description": "Mandatory orientation session covering culture, values, and policies.", "priority": "High"},
        {"category": "Orientation", "task": "Meet Your Team", "description": "Introduction meeting with your direct manager and teammates.", "priority": "High"},
        {"category": "Role-Specific", "task": f"Role Briefing for {job_role}", "description": "Detailed briefing on role responsibilities, KPIs, and expectations.", "priority": "High"},
        {"category": "Role-Specific", "task": "30-60-90 Day Plan", "description": "Review and agree on your onboarding goals with your manager.", "priority": "Medium"},
    ]
