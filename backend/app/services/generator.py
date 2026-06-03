import json
import logging
import re
from typing import List, Dict, Any
from app.services.client import nexus_client
from app.services.rag_service import rag_service

logger = logging.getLogger("hireflow.generator")

def generate_rubric_and_questions(
    role_name: str, 
    skills_required: List[str], 
    responsibilities: str
) -> Dict[str, Any]:
    """
    Retrieves candidate questions from RAG, combines them with Job Description metadata,
    and calls Nexus LLM to generate the global evaluation rubric and exactly 5 customized interview questions.
    """
    # 1. Retrieve raw questions via RAG
    rag_questions = rag_service.get_questions_for_role(role_name, skills_required, limit=5)
    
    # Format questions to show the LLM
    questions_context = ""
    for idx, q in enumerate(rag_questions):
        questions_context += f"Question {idx+1}: {q['question_text']}\nExpected Answer: {q['expected_answer']}\nRubric: {json.dumps(q['eval_rubric'])}\n\n"

    system_prompt = (
        "You are an elite AI recruiting director. You generate robust, tailored evaluation rubrics and structured interview questions.\n"
        "Given the Job Description details and a list of reference questions retrieved from our knowledge base, you must produce:\n"
        "1. A global candidate evaluation rubric defining criteria for candidate scoring. This must have exactly 4 keys: 'skills', 'experience', 'projects', and 'jd_match'. "
        "Each key must map to an object with 'weight' (float, total sum of all 4 weights MUST be exactly 1.0) and 'description' (string).\n"
        "2. A list of exactly 5 interview questions. You can refine or adapt the reference questions, or write new ones if needed, to fit the role perfectly. "
        "Each question object must contain:\n"
        "   - 'question_text': Clear, open-ended question (string)\n"
        "   - 'expected_answer': Detailed answer indicating high performance (string)\n"
        "   - 'eval_rubric': A list of evaluation criteria objects for grading the answer. Each criteria object must have 'criteria' (string), 'weight' (float summing to 1.0), and 'description' (string).\n\n"
        "CRITICAL: You must return ONLY a valid JSON object. Do not include markdown formatting, backticks (like ```json), or any introductory/conversational text."
    )

    user_content = (
        f"JOB DESCRIPTION:\n"
        f"Role: {role_name}\n"
        f"Required Skills: {', '.join(skills_required)}\n"
        f"Responsibilities: {responsibilities}\n\n"
        f"REFERENCE QUESTIONS (incorporate and adapt these where appropriate):\n"
        f"{questions_context}\n"
    )

    try:
        response_text = nexus_client.generate_prompt(system_prompt, user_content, temperature=0.3)
        cleaned_text = response_text.strip()
        if cleaned_text.startswith("```"):
            cleaned_text = re.sub(r"^```(?:json)?\n", "", cleaned_text)
            cleaned_text = re.sub(r"\n```$", "", cleaned_text)
        
        parsed_data = json.loads(cleaned_text.strip())
        return parsed_data
    except Exception as e:
        logger.error(f"Failed to generate rubric and questions via LLM. Error: {str(e)}")
        # Return fallback structures if LLM fails
        return get_fallback_rubric_and_questions(role_name, skills_required, rag_questions)

def get_fallback_rubric_and_questions(
    role_name: str, 
    skills_required: List[str], 
    rag_questions: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Generates standard fallbacks if LLM fails to return valid JSON."""
    logger.info("Falling back to static rubric and question formatting.")
    
    fallback_rubric = {
        "skills": {"weight": 0.3, "description": f"Match with required skills: {', '.join(skills_required)}"},
        "experience": {"weight": 0.3, "description": "Candidate years of experience and seniority match."},
        "projects": {"weight": 0.2, "description": "Candidate project experience and complexity."},
        "jd_match": {"weight": 0.2, "description": "Overall alignment with JD responsibilities."}
    }

    fallback_questions = []
    # Use RAG questions if available, otherwise make standard ones
    if rag_questions:
        fallback_questions = rag_questions[:5]
    
    # Fill up if less than 5 questions
    while len(fallback_questions) < 5:
        idx = len(fallback_questions) + 1
        fallback_questions.append({
            "role_name": role_name,
            "question_text": f"Standard interview question {idx} for {role_name}. Can you describe your experience with this stack?",
            "expected_answer": "Detailed explanation of candidate's technical achievements and implementation details.",
            "eval_rubric": [
                {"criteria": "Technical Depth", "weight": 0.5, "description": "Demonstrates deep knowledge of the concepts."},
                {"criteria": "Communication", "weight": 0.5, "description": "Explains complex ideas clearly."}
            ]
        })

    return {
        "rubric": fallback_rubric,
        "questions": fallback_questions
    }
