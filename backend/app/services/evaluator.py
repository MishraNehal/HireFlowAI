import json
import logging
import re
from typing import Dict, Any, List
from app.services.client import nexus_client

logger = logging.getLogger("hireflow.evaluator")


# ---------------------------------------------------------------------------
# LOCAL HEURISTIC EVALUATOR — runs when LLM API is unavailable
# ---------------------------------------------------------------------------

def _heuristic_evaluate(
    resume_text: str,
    jd_role: str,
    jd_skills: List[str],
    jd_responsibilities: str = ""
) -> Dict[str, Any]:
    """
    Smart local scorer that does NOT require an LLM.
    Scores based on: skill overlap, experience years, keyword density, project signals.
    Returns scores in the same format as the LLM evaluator.
    """
    text_lower = resume_text.lower()

    # ── 1. Skills Score ──────────────────────────────────────────────────────
    # How many JD skills appear in the resume text?
    matched_skills = []
    missing_skills = []
    for skill in jd_skills:
        pattern = re.compile(r'\b' + re.escape(skill.lower()) + r'\b')
        if pattern.search(text_lower):
            matched_skills.append(skill)
        else:
            missing_skills.append(skill)

    if jd_skills:
        skill_ratio = len(matched_skills) / len(jd_skills)
    else:
        skill_ratio = 0.5

    # Score: 0 match = 20, full match = 100
    skills_score = round(20 + skill_ratio * 80, 1)

    # ── 2. Experience Score ───────────────────────────────────────────────────
    # Extract years of experience from resume text
    exp_matches = re.findall(r'(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b', text_lower)
    exp_years = max((float(x) for x in exp_matches), default=0.0)

    # Map years to score (0yr=40, 1yr=60, 2yr=70, 3+yr=85, 5+yr=95)
    if exp_years >= 5:
        experience_score = 92.0
    elif exp_years >= 3:
        experience_score = 80.0
    elif exp_years >= 2:
        experience_score = 70.0
    elif exp_years >= 1:
        experience_score = 62.0
    elif exp_years > 0:
        experience_score = 55.0
    else:
        # Freshers: check for internship / project signals
        has_intern = bool(re.search(r'\b(intern|internship|trainee)\b', text_lower))
        experience_score = 50.0 if has_intern else 40.0

    # ── 3. JD Match Score (keyword density) ──────────────────────────────────
    # Scan for role-relevant keywords from skills list, role name, and responsibilities
    role_words = re.findall(r'\w+', jd_role.lower())
    resp_words = re.findall(r'\w+', jd_responsibilities.lower()) if jd_responsibilities else []
    all_keywords = [w for w in (role_words + resp_words + [s.lower() for s in jd_skills]) if len(w) > 2]
    
    # Optional: Filter out common stop words if necessary, but length > 2 covers some.
    # To prevent inflating due to too many generic words, we can take unique words.
    unique_keywords = list(set(all_keywords))
    
    keyword_hits = sum(1 for kw in unique_keywords if kw in text_lower)
    kw_ratio = keyword_hits / max(len(unique_keywords), 1)
    jd_match_score = round(30 + kw_ratio * 65, 1)

    # ── 4. Projects Score ─────────────────────────────────────────────────────
    # Signals: project headers, github links, hackathons, deployed apps
    project_signals = [
        r'\bproject[s]?\b', r'\bgithub\.com\b', r'\bhackathon\b',
        r'\bdeployed\b', r'\bbuilt\b', r'\bdeveloped\b', r'\bimplemented\b',
        r'\bopen.?source\b', r'\bportfolio\b', r'\bapplication[s]?\b'
    ]
    signal_hits = sum(1 for p in project_signals if re.search(p, text_lower))
    projects_score = round(min(40 + signal_hits * 7, 95), 1)

    # ── Total Score ───────────────────────────────────────────────────────────
    total_score = round(
        skills_score * 0.35 +
        experience_score * 0.25 +
        jd_match_score * 0.25 +
        projects_score * 0.15,
        1
    )

    # ── Breakdown Notes ───────────────────────────────────────────────────────
    notes_parts = [
        f"[Heuristic Evaluation]",
        f"Skills matched: {', '.join(matched_skills) if matched_skills else 'None'} ({len(matched_skills)}/{len(jd_skills)})",
        f"Skills missing: {', '.join(missing_skills[:5]) if missing_skills else 'None'}",
        f"Experience detected: {exp_years} years",
        f"Keyword match ratio: {kw_ratio:.0%}",
        f"Project signals found: {signal_hits}",
    ]
    breakdown_notes = " | ".join(notes_parts)

    return {
        "skills_score": skills_score,
        "experience_score": experience_score,
        "projects_score": projects_score,
        "jd_match_score": jd_match_score,
        "total_score": total_score,
        "breakdown_notes": breakdown_notes,
    }


# ---------------------------------------------------------------------------
# PRIMARY EVALUATOR — tries LLM first, heuristic fallback
# ---------------------------------------------------------------------------

def evaluate_resume(
    resume_text: str,
    jd_role: str,
    jd_skills: List[str],
    jd_responsibilities: str
) -> Dict[str, Any]:
    """
    Evaluates candidate resume against a Job Description.
    Tries LLM first; falls back to smart heuristic scorer if LLM is unavailable.
    """
    system_prompt = (
        "You are an expert technical recruiting agency AI. Your task is to evaluate a candidate's resume text "
        "against a specific Job Description (JD).\n"
        "Assess the candidate and score them on a scale of 0 to 100 on the following components:\n"
        "1. 'skills_score': How well the candidate's parsed skills cover the required skills of the JD.\n"
        "2. 'experience_score': Seniority, career progression, and years of experience alignment.\n"
        "3. 'projects_score': Relevance, complexity, and impact of projects/work accomplishments.\n"
        "4. 'jd_match_score': General alignment with the role responsibilities.\n\n"
        "Then, calculate the 'total_score' (float, 0 to 100) as the weighted average.\n"
        "Provide detailed evaluation notes in 'breakdown_notes'.\n\n"
        "CRITICAL: Return ONLY a valid JSON object. No markdown, no backticks, no extra text."
    )

    user_content = (
        f"JOB DESCRIPTION:\n"
        f"Role: {jd_role}\n"
        f"Required Skills: {', '.join(jd_skills)}\n"
        f"Responsibilities: {jd_responsibilities}\n\n"
        f"CANDIDATE RESUME TEXT:\n"
        f"{resume_text[:4000]}\n"  # cap at 4000 chars to avoid token limits
    )

    try:
        response_text = nexus_client.generate_prompt(system_prompt, user_content, temperature=0.2)
        cleaned_text = response_text.strip()
        if cleaned_text.startswith("```"):
            cleaned_text = re.sub(r"^```(?:json)?\n", "", cleaned_text)
            cleaned_text = re.sub(r"\n```$", "", cleaned_text)

        parsed_data = json.loads(cleaned_text.strip())

        for key in ["skills_score", "experience_score", "projects_score", "jd_match_score", "total_score"]:
            parsed_data[key] = float(parsed_data.get(key, 50.0))

        if "breakdown_notes" not in parsed_data:
            parsed_data["breakdown_notes"] = "LLM evaluation completed."

        logger.info(f"LLM evaluation success. Total score: {parsed_data['total_score']}")
        return parsed_data

    except Exception as e:
        logger.warning(f"LLM evaluation failed ({type(e).__name__}), using heuristic scorer.")
        return _heuristic_evaluate(resume_text, jd_role, jd_skills, jd_responsibilities)


# ---------------------------------------------------------------------------
# INTERVIEW RESPONSE EVALUATOR
# ---------------------------------------------------------------------------

def evaluate_candidate_response(
    question_text: str,
    expected_answer: str,
    eval_rubric: List[Dict[str, Any]],
    candidate_answer: str
) -> Dict[str, Any]:
    """
    Grades candidate's response to an interview question on a 0.0 - 5.0 scale.
    """
    system_prompt = (
        "You are an expert interviewer. Evaluate the candidate's response to an interview question.\n"
        "You will be given the question, expected answer, rubric, and candidate's response.\n"
        "Provide a score from 0.0 to 5.0 and constructive feedback.\n\n"
        "CRITICAL: Return ONLY a valid JSON object with 'score' and 'feedback' keys. No markdown."
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

        if "score" not in parsed_data:
            parsed_data["score"] = 2.5
        else:
            parsed_data["score"] = min(5.0, max(0.0, float(parsed_data["score"])))

        if "feedback" not in parsed_data:
            parsed_data["feedback"] = "Response evaluated."

        return parsed_data

    except Exception as e:
        logger.error(f"Failed to evaluate candidate response: {str(e)}")
        return {
            "score": 0.0,
            "feedback": f"System error evaluating response: {str(e)}"
        }
