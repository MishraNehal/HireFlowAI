import json
import logging
import re
from typing import Dict, Any, List
from app.services.client import nexus_client

logger = logging.getLogger("hireflow.evaluator")

def evaluate_resume(
    resume_text: str,
    jd_role: str,
    jd_skills: List[str],
    jd_responsibilities: str
) -> Dict[str, Any]:
    """
    Evaluates candidate's resume text against a Job Description.
    Calculates detailed sub-scores and overall total score out of 100, generating evaluation feedback notes.
    """
    system_prompt = (
        "You are an expert technical recruiting agency AI. Your task is to evaluate a candidate's resume text "
        "against a specific Job Description (JD).\n"
        "Assess the candidate and score them on a scale of 0 to 100 on the following components:\n"
        "1. 'skills_score': How well the candidate's parsed skills cover the required skills of the JD.\n"
        "2. 'experience_score': Seniority, career progression, and years of experience alignment.\n"
        "3. 'projects_score': Relevance, complexity, and impact of projects/work accomplishments.\n"
        "4. 'jd_match_score': General alignment with the role responsibilities.\n\n"
        "Then, calculate the 'total_score' (float, 0 to 100) as the average of the four sub-scores.\n"
        "Provide detailed evaluation notes explaining the strengths and gaps in 'breakdown_notes'.\n\n"
        "CRITICAL: You must return ONLY a valid JSON object. Do not include markdown formatting, backticks (like ```json), or any introductory/conversational text."
    )

    user_content = (
        f"JOB DESCRIPTION:\n"
        f"Role: {jd_role}\n"
        f"Required Skills: {', '.join(jd_skills)}\n"
        f"Responsibilities: {jd_responsibilities}\n\n"
        f"CANDIDATE RESUME TEXT:\n"
        f"{resume_text}\n"
    )

    try:
        response_text = nexus_client.generate_prompt(system_prompt, user_content, temperature=0.2)
        cleaned_text = response_text.strip()
        if cleaned_text.startswith("```"):
            cleaned_text = re.sub(r"^```(?:json)?\n", "", cleaned_text)
            cleaned_text = re.sub(r"\n```$", "", cleaned_text)

        parsed_data = json.loads(cleaned_text.strip())
        
        # Ensure all required keys exist and are numeric
        for key in ["skills_score", "experience_score", "projects_score", "jd_match_score", "total_score"]:
            if key not in parsed_data:
                parsed_data[key] = 50.0
            else:
                parsed_data[key] = float(parsed_data[key])
        
        if "breakdown_notes" not in parsed_data:
            parsed_data["breakdown_notes"] = "Evaluation completed successfully."
            
        return parsed_data

    except Exception as e:
        logger.error(f"Failed to evaluate resume using LLM: {str(e)}")
        # Return neutral fallback evaluation
        return {
            "skills_score": 50.0,
            "experience_score": 50.0,
            "projects_score": 50.0,
            "jd_match_score": 50.0,
            "total_score": 50.0,
            "breakdown_notes": f"Fallback evaluation due to system error: {str(e)}"
        }

def evaluate_candidate_response(
    question_text: str,
    expected_answer: str,
    eval_rubric: List[Dict[str, Any]],
    candidate_answer: str
) -> Dict[str, Any]:
    """
    Grades candidate's response to an interview question on a 0.0 - 5.0 scale using a specific rubric.
    """
    system_prompt = (
        "You are an expert interviewer. Your task is to evaluate a candidate's response to an interview question.\n"
        "You will be given:\n"
        "- The interview question\n"
        "- The expected model answer\n"
        "- The specific evaluation rubric (list of criteria with descriptions and weights)\n"
        "- The candidate's response\n\n"
        "Provide a score from 0.0 to 5.0 (where 0.0 is completely incorrect/blank, and 5.0 is outstanding/perfect alignment with expected answers and rubric).\n"
        "Construct constructive feedback highlighting strengths, missed elements, or incorrect assumptions.\n\n"
        "CRITICAL: You must return ONLY a valid JSON object. Do not include markdown formatting, backticks (like ```json), or any introductory/conversational text."
    )

    user_content = (
        f"QUESTION:\n{question_text}\n\n"
        f"EXPECTED ANSWER:\n{expected_answer}\n\n"
        f"RUBRIC:\n{json.dumps(eval_rubric)}\n\n"
        f"CANDIDATE RESPONSE:\n{candidate_answer}\n"
    )

    try:
        response_text = nexus_client.generate_prompt(system_prompt, user_content, temperature=0.1)
        cleaned_text = response_text.strip()
        if cleaned_text.startswith("```"):
            cleaned_text = re.sub(r"^```(?:json)?\n", "", cleaned_text)
            cleaned_text = re.sub(r"\n```$", "", cleaned_text)

        parsed_data = json.loads(cleaned_text.strip())
        
        # Ensure correct keys
        if "score" not in parsed_data:
            parsed_data["score"] = 2.5
        else:
            parsed_data["score"] = min(5.0, max(0.0, float(parsed_data["score"])))
            
        if "feedback" not in parsed_data:
            parsed_data["feedback"] = "Response evaluated."
            
        return parsed_data

    except Exception as e:
        logger.error(f"Failed to evaluate candidate response using LLM: {str(e)}")
        return {
            "score": 0.0,
            "feedback": f"System error evaluating response: {str(e)}"
        }
