"""
Scoring service — computes a candidate's fit score against a campaign's
requirements.

Total score is out of 100, split across four components:
    - skills_score      (max 40)  rule-based, embedding-similarity matching
    - education_score   (max 15)  rule-based, degree-LEVEL tiers (not tech-specific)
    - project_score      (max 25)  Groq-evaluated
    - experience_score   (max 20)  Groq-evaluated

Skills and education stay rule-based (deterministic, free, instant, and
reproducible — important for a score HR will use to justify shortlist
decisions) but are domain-agnostic: skill matching uses semantic
similarity so "MS Excel" ≈ "Excel" and "public speaking" ≈ "communication
skills" work the same for a non-tech role as "FastAPI" ≈ "fastapi" does
for a tech one. Education tiers key off degree LEVEL (bachelor's/master's
vs. diploma/12th) with a broad keyword list spanning engineering, commerce,
arts, law, and medical degrees — not just B.Tech/MCA/BCA.

Project/experience remain Groq-evaluated since "is this relevant and
impressive" is a judgment call no rule-based system can make reliably
across arbitrary job roles.
"""
import asyncio
import logging
from typing import Any

from app.services.llm import call_llm_json
from app.services.rag import embed_texts

logger = logging.getLogger(__name__)

MAX_SKILLS_SCORE = 40.0
MAX_EDUCATION_SCORE = 15.0
MAX_PROJECT_SCORE = 25.0
MAX_EXPERIENCE_SCORE = 20.0

# Cosine similarity threshold above which two skill strings are considered
# a match. all-MiniLM-L6-v2 typically puts close paraphrases (e.g. "Excel"
# vs "MS Excel", "communication" vs "communication skills") above ~0.6-0.7
# and unrelated skills below ~0.3, so 0.55 leaves headroom for legitimate
# variants without matching unrelated skills.
SKILL_MATCH_THRESHOLD = 0.55

# Degree-LEVEL keyword tiers, not tied to any one field of study, so a
# B.Com/BBA/B.A./LLB candidate is scored the same tier as a B.Tech one.
_DEGREE_TIER_BACHELOR_OR_HIGHER = (
    # Engineering / science
    "b.tech", "btech", "b.e", " be ", "b.sc", "bsc", "m.tech", "mtech",
    "mca", "bca", "m.sc", "msc",
    # Commerce / management
    "b.com", "bcom", "bba", "mba", "m.com", "mcom",
    # Arts / humanities
    "b.a", " ba ", "m.a", " ma ",
    # Law / medical / pharmacy / education
    "llb", "ll.b", "mbbs", "bds", "b.pharm", "m.pharm", "b.ed", "m.ed",
    # Generic catch-alls
    "bachelor", "master", "phd", "ph.d", "doctorate", "post graduate",
    "postgraduate", "post-graduate", "graduate",
)
_DEGREE_TIER_HIGHER_SECONDARY = (
    "diploma", "12th", "hsc", "intermediate", "higher secondary", "puc",
)


def calculate_skills_score(
    candidate_skills: list[str],
    required_skills: list[str],
) -> tuple[float, list[str], list[str]]:
    """Skills match via embedding similarity, domain-agnostic.

    Each required skill is matched against the candidate's skill list using
    cosine similarity of sentence-transformer embeddings (same model as the
    RAG service), not exact string matching. This lets "MS Excel" match
    "Excel", or "React.js" match "React", without a hardcoded synonym list —
    and works identically whether the role is technical or not.

    Falls back to a normalized exact-string match first (fast, free, and
    handles the common case) before spending an embedding call only on
    skills that didn't match exactly.

    Returns:
        (score, matched_skills, missing_skills) — matched/missing lists
        preserve the original casing from required_skills.
    """
    if not required_skills:
        return 0.0, [], []

    clean_required = [s for s in required_skills if s and s.strip()]
    clean_candidate = [s for s in candidate_skills if s and s.strip()]
    if not clean_required:
        return 0.0, [], []
    if not clean_candidate:
        return 0.0, [], list(clean_required)

    candidate_norm = {s.strip().lower() for s in clean_candidate}

    matched: list[str] = []
    still_unmatched: list[str] = []
    for skill in clean_required:
        if skill.strip().lower() in candidate_norm:
            matched.append(skill)
        else:
            still_unmatched.append(skill)

    # Semantic pass for anything that didn't match exactly.
    semantically_matched: list[str] = []
    if still_unmatched:
        try:
            required_vecs = embed_texts(still_unmatched)
            candidate_vecs = embed_texts(clean_candidate)
            for skill, req_vec in zip(still_unmatched, required_vecs):
                best_sim = max(
                    (_cosine_sim(req_vec, cand_vec) for cand_vec in candidate_vecs),
                    default=0.0,
                )
                if best_sim >= SKILL_MATCH_THRESHOLD:
                    semantically_matched.append(skill)
        except Exception as e:
            logger.error(
                "Embedding-based skill matching failed (%s); falling back to "
                "exact-match results only for the remaining skills.", e
            )

    matched.extend(semantically_matched)
    missing = [s for s in still_unmatched if s not in semantically_matched]

    total_required = len(matched) + len(missing)
    if total_required == 0:
        return 0.0, [], []

    score = round((len(matched) / total_required) * MAX_SKILLS_SCORE, 2)
    return score, matched, missing


def calculate_education_score(education: list[dict]) -> float:
    """Rule-based education tier score, keyed off degree LEVEL rather than
    a specific field of study — so B.Com/BBA/B.A./LLB score the same tier
    as B.Tech, since all are bachelor's degrees.

    Looks across every degree entry supplied and returns the score for the
    HIGHEST qualification found, so a candidate with both a 12th-grade
    entry and a bachelor's entry is scored on the bachelor's.

    Tiers:
        Bachelor's or higher (any field) -> 15
        Diploma/12th/HSC/Intermediate     -> 8
        Otherwise (or no entries)         -> 4
    """
    if not education:
        return 4.0

    best = 4.0
    for entry in education:
        degree = f" {str((entry or {}).get('degree', '')).strip().lower()} "
        if degree.strip() == "":
            continue
        if any(tier in degree for tier in _DEGREE_TIER_BACHELOR_OR_HIGHER):
            best = max(best, 15.0)
        elif any(tier in degree for tier in _DEGREE_TIER_HIGHER_SECONDARY):
            best = max(best, 8.0)
        else:
            best = max(best, 4.0)

    return best


def _cosine_sim(vec_a: list[float], vec_b: list[float]) -> float:
    """Cosine similarity between two vectors. Since embed_texts() returns
    normalized vectors (see rag.py), this reduces to a plain dot product —
    no need for numpy just to divide by norms that are already 1."""
    return sum(a * b for a, b in zip(vec_a, vec_b))


async def calculate_project_score(
    projects: list[dict],
    job_role: str,
    required_skills: list[str],
) -> tuple[float, str]:
    """Groq-evaluated project relevance/quality score, max 25.

    Returns (score, reasoning). If there are no projects, returns (0.0,
    reasoning) without calling the LLM.
    """
    if not projects:
        return 0.0, "No projects listed on the resume."

    projects_text = _format_list_of_dicts(
        projects, fields=("name", "tech_stack", "description")
    )
    required_skills_text = ", ".join(required_skills) if required_skills else "Not specified"

    system = (
        "You are an expert technical recruiter evaluating a candidate's "
        "project experience for a specific job role. Score strictly and "
        "consistently based on relevance to the role, technical depth, "
        "and use of the required skills. Respond only with a valid JSON "
        "object."
    )
    prompt = f"""Job role: {job_role}
Required skills: {required_skills_text}

Candidate's projects:
{projects_text}

Score these projects out of 25 points based on:
- Relevance of the projects to the job role
- Technical depth and complexity demonstrated
- Overlap with the required skills listed above
- Evidence of real, substantive work (not trivial tutorials)

Return ONLY valid JSON in this exact shape, no markdown, no explanation:
{{"score": <number between 0 and 25>, "reasoning": "<1-3 sentence explanation>"}}"""

    try:
        result = await asyncio.to_thread(call_llm_json, prompt, system=system, temperature=0.2)
        score = _clamp(float(result.get("score", 0)), 0.0, MAX_PROJECT_SCORE)
        reasoning = str(result.get("reasoning", "")).strip() or "No reasoning provided."
        return round(score, 2), reasoning
    except Exception as e:
        logger.error("Project scoring failed, defaulting to 0: %s", e)
        return 0.0, f"Automatic scoring failed ({type(e).__name__}); defaulted to 0."


async def calculate_experience_score(
    experience: list[dict],
    job_role: str,
    experience_level: str,
) -> tuple[float, str]:
    """Groq-evaluated work experience score, max 20.

    Returns (score, reasoning). If there is no experience listed, this is
    not necessarily a penalty for entry-level roles — the prompt makes
    that context explicit to the model.
    """
    if not experience:
        if experience_level and experience_level.strip().lower() in ("fresher", "entry", "entry-level", "entry_level"):
            return MAX_EXPERIENCE_SCORE * 0.5, (
                "No work experience listed, but role is entry-level; "
                "scored at baseline for freshers."
            )
        return 0.0, "No work experience listed on the resume."

    experience_text = _format_list_of_dicts(
        experience, fields=("company", "role", "duration", "description")
    )

    system = (
        "You are an expert technical recruiter evaluating a candidate's "
        "work experience for a specific job role and seniority level. "
        "Score strictly and consistently. Respond only with a valid JSON "
        "object."
    )
    prompt = f"""Job role: {job_role}
Target experience level: {experience_level or "Not specified"}

Candidate's work experience:
{experience_text}

Score this experience out of 20 points based on:
- Relevance of past roles/companies to the target job role
- Duration and seniority appropriate to the target experience level
- Evidence of real responsibility and impact (not just listed titles)

Return ONLY valid JSON in this exact shape, no markdown, no explanation:
{{"score": <number between 0 and 20>, "reasoning": "<1-3 sentence explanation>"}}"""

    try:
        result = await asyncio.to_thread(call_llm_json, prompt, system=system, temperature=0.2)
        score = _clamp(float(result.get("score", 0)), 0.0, MAX_EXPERIENCE_SCORE)
        reasoning = str(result.get("reasoning", "")).strip() or "No reasoning provided."
        return round(score, 2), reasoning
    except Exception as e:
        logger.error("Experience scoring failed, defaulting to 0: %s", e)
        return 0.0, f"Automatic scoring failed ({type(e).__name__}); defaulted to 0."


MAX_CERTIFICATION_BONUS = 5.0

# Lower than SKILL_MATCH_THRESHOLD deliberately — certifications are titled
# more loosely than skill tags (e.g. "AWS Certified Cloud Practitioner" vs.
# a required skill of just "AWS"), so a stricter threshold would under-credit
# genuinely relevant certifications.
CERTIFICATION_RELEVANCE_THRESHOLD = 0.4


def calculate_certification_score(
    certifications: list[str],
    required_skills: list[str],
    job_role: str,
) -> tuple[float, list[str]]:
    """Small rule-based bonus (max +5) for relevant certifications, on top
    of the 100-point base score — not part of the four core components.

    Relevance is checked via the same embedding similarity used for
    skills: a certification counts if it's semantically close to any
    required skill or to the job role itself, so an "AWS Certified Cloud
    Practitioner" cert counts toward an "AWS"-requiring role, but a
    certification unrelated to the role doesn't inflate the score.

    Returns:
        (bonus, relevant_certifications) — bonus is 1 point per relevant
        certification, capped at MAX_CERTIFICATION_BONUS. If embeddings
        can't be computed for some reason, falls back to crediting every
        listed certification (capped the same way) rather than losing the
        signal entirely.
    """
    clean_certs = [c for c in certifications if c and str(c).strip()]
    if not clean_certs:
        return 0.0, []

    reference_texts = [s for s in required_skills if s and s.strip()]
    if job_role and job_role.strip():
        reference_texts.append(job_role.strip())

    if not reference_texts:
        # No context to judge relevance against — credit them all, capped.
        bonus = min(MAX_CERTIFICATION_BONUS, float(len(clean_certs)))
        return bonus, clean_certs

    try:
        cert_vecs = embed_texts(clean_certs)
        reference_vecs = embed_texts(reference_texts)
        relevant: list[str] = []
        for cert, cert_vec in zip(clean_certs, cert_vecs):
            best_sim = max(
                (_cosine_sim(cert_vec, ref_vec) for ref_vec in reference_vecs),
                default=0.0,
            )
            if best_sim >= CERTIFICATION_RELEVANCE_THRESHOLD:
                relevant.append(cert)
        bonus = min(MAX_CERTIFICATION_BONUS, float(len(relevant)))
        return bonus, relevant
    except Exception as e:
        logger.error(
            "Embedding-based certification relevance check failed (%s); "
            "crediting all listed certifications instead.", e
        )
        bonus = min(MAX_CERTIFICATION_BONUS, float(len(clean_certs)))
        return bonus, clean_certs


def get_recommendation(total_score: float) -> str:
    """Maps a total score (0-100) to a recommendation bucket.

    70-100 -> strong_match
    40-69  -> moderate_match
    0-39   -> weak_match
    """
    if total_score >= 70:
        return "strong_match"
    if total_score >= 40:
        return "moderate_match"
    return "weak_match"


async def score_candidate(
    candidate_skills: list[str],
    required_skills: list[str],
    education: list[dict],
    projects: list[dict],
    experience: list[dict],
    job_role: str,
    experience_level: str = "",
    certifications: list[str] | None = None,
) -> dict[str, Any]:
    """Runs all scoring components and returns the full breakdown.

    This is the single entry point resume_intelligence_agent should call.
    The core four components (skills/education/projects/experience) sum to
    a 0-100 base score; certifications add a small relevance-weighted
    bonus (max +5) on top, with the final total capped back at 100 so the
    recommendation thresholds (defined on a 0-100 scale) stay meaningful.
    """
    skills_score, matched_skills, missing_skills = calculate_skills_score(
        candidate_skills, required_skills
    )
    education_score = calculate_education_score(education)

    project_score, project_reasoning = await calculate_project_score(
        projects, job_role, required_skills
    )
    experience_score, experience_reasoning = await calculate_experience_score(
        experience, job_role, experience_level
    )

    certification_bonus, relevant_certifications = calculate_certification_score(
        certifications or [], required_skills, job_role
    )

    base_total = skills_score + education_score + project_score + experience_score
    total_score = round(min(100.0, base_total + certification_bonus), 2)
    recommendation = get_recommendation(total_score)

    strengths = list(matched_skills)
    if relevant_certifications:
        strengths.extend(f"Certification: {c}" for c in relevant_certifications)
    gaps = list(missing_skills)
    if project_score < MAX_PROJECT_SCORE * 0.4:
        gaps.append("Limited relevant project experience")
    if experience_score < MAX_EXPERIENCE_SCORE * 0.4:
        gaps.append("Limited relevant work experience")

    return {
        "skills_score": skills_score,
        "education_score": education_score,
        "project_score": project_score,
        "experience_score": experience_score,
        "certification_bonus": certification_bonus,
        "total_score": total_score,
        "recommendation": recommendation,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "relevant_certifications": relevant_certifications,
        "all_certifications": [c for c in (certifications or []) if c and str(c).strip()],
        "strengths": strengths,
        "gaps": gaps,
        "project_reasoning": project_reasoning,
        "experience_reasoning": experience_reasoning,
    }


# ── Internal helpers ─────────────────────────────────────────────────────────

def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _format_list_of_dicts(items: list[dict], fields: tuple[str, ...]) -> str:
    """Renders a list of dicts as a numbered, human-readable block for
    inclusion in an LLM prompt."""
    lines = []
    for i, item in enumerate(items, start=1):
        item = item or {}
        parts = [f"{field}: {item.get(field, 'N/A')}" for field in fields if item.get(field)]
        lines.append(f"{i}. " + " | ".join(parts) if parts else f"{i}. (no details provided)")
    return "\n".join(lines)
