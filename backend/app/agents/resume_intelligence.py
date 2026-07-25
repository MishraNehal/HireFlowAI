"""
Agent 5 — Resume Intelligence

Not a LangGraph node. Called directly by Celery's process_resume_task
(Task 4.5) once per candidate, right after their resume is uploaded.

Pipeline for a single candidate:
    1. Load Candidate + Resume + Campaign from the DB.
    2. Download the resume PDF from Supabase Storage.
    3. Extract raw text (PyMuPDF) and parse it into a structured profile
       (Groq) — both via resume_parser.py.
    4. Embed the profile for future semantic candidate search.
    5. Score the candidate against the campaign's requirements
       (scoring.py) — skills/education/projects/experience + certification
       bonus.
    6. Persist CandidateProfile + Score, update Resume.parse_status and
       Candidate.status.
    7. Notify the HR dashboard over WebSocket.

Failure handling: any error marks Resume.parse_status = "failed", commits
that state (so it's visible even if the exception isn't handled further
up), and re-raises — Celery's retry logic (Task 4.5) is what decides
whether to try again, not this function.
"""
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.candidate import (
    Candidate,
    CandidateProfile,
    CandidateStatus,
    ParseStatus,
    Recommendation,
    Resume,
    Score,
)
from app.services.rag import embed_text
from app.services.resume_parser import extract_text_from_pdf, parse_resume_with_llm
from app.services.scoring import score_candidate
from app.services.storage import download_file, resume_key
from app.services.websocket import ws_manager

logger = logging.getLogger(__name__)

# Campus recruitment campaigns target fresh graduates by default. There's no
# per-campaign experience_level field in the Campaign model yet, so this is
# the assumed baseline for the scoring service's fresher-friendly experience
# handling (see scoring.calculate_experience_score). Revisit if HireFlow
# starts supporting experienced-hire campaigns with different expectations.
DEFAULT_EXPERIENCE_LEVEL = "fresher"


async def resume_intelligence_agent(
    candidate_id: str,
    campaign_id: str,
    company_id: str,
    db: Session,
) -> dict[str, Any]:
    """Processes one candidate's resume end-to-end: download, parse, embed,
    score, persist, notify.

    Returns:
        {"candidate_id": str, "total_score": float, "recommendation": str}

    Raises:
        ValueError: if the candidate/resume/campaign can't be found.
        Exception: propagates any parsing/scoring/DB failure after marking
            the resume as failed, so Celery's retry decorator can act on it.
    """
    logger.info(f"[Agent5:ResumeIntelligence] Starting — candidate={candidate_id}")

    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise ValueError(f"Candidate {candidate_id} not found")

    resume = candidate.resume
    if resume is None:
        raise ValueError(f"No resume record found for candidate {candidate_id}")

    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise ValueError(f"Campaign {campaign_id} not found")

    try:
        # ── Step 1: Download + extract + parse ────────────────────────────
        key = resume_key(company_id, campaign_id, candidate_id)
        file_bytes = download_file(key)

        raw_text = extract_text_from_pdf(file_bytes)
        parsed = await parse_resume_with_llm(raw_text)

        # ── Step 2: Embed the profile for future semantic search ─────────
        embedding_text = _build_embedding_text(parsed)
        profile_embedding = embed_text(embedding_text) if embedding_text else None

        # ── Step 3: Score against this campaign's requirements ────────────
        score_result = await score_candidate(
            candidate_skills=parsed["skills"],
            required_skills=list(campaign.skills_required or []),
            education=parsed["education"],
            projects=parsed["projects"],
            experience=parsed["experience"],
            job_role=campaign.role,
            experience_level=DEFAULT_EXPERIENCE_LEVEL,
            certifications=parsed["certifications"],
        )

        # ── Step 4: Persist — profile ──────────────────────────────────────
        profile = candidate.profile
        if profile is None:
            profile = CandidateProfile(candidate_id=candidate.id)
            db.add(profile)
            candidate.profile = profile

        profile.skills = parsed["skills"]
        profile.projects = parsed["projects"]
        profile.experience = parsed["experience"]
        profile.education = parsed["education"]
        profile.certifications = parsed["certifications"]
        profile.summary = _build_summary(parsed)
        profile.embedding = profile_embedding

        # ── Step 5: Persist — score ────────────────────────────────────────
        score_row = candidate.score
        if score_row is None:
            score_row = Score(candidate_id=candidate.id, campaign_id=campaign.id)
            db.add(score_row)
            candidate.score = score_row

        score_row.campaign_id = campaign.id
        score_row.skills_score = score_result["skills_score"]
        score_row.project_score = score_result["project_score"]
        score_row.experience_score = score_result["experience_score"]
        score_row.education_score = score_result["education_score"]
        score_row.total_score = score_result["total_score"]
        score_row.strengths = score_result["strengths"]
        score_row.gaps = score_result["gaps"]
        score_row.recommendation = Recommendation(score_result["recommendation"])
        score_row.is_overridden = False
        score_row.override_by = None
        score_row.override_notes = None
        score_row.scored_at = datetime.now(timezone.utc)

        # ── Step 6: Update resume + candidate status ───────────────────────
        resume.parse_status = ParseStatus.parsed
        resume.raw_text = raw_text
        resume.parsed_at = datetime.now(timezone.utc)
        candidate.status = CandidateStatus.screened

        db.commit()

        logger.info(
            f"[Agent5:ResumeIntelligence] Completed — candidate={candidate_id}, "
            f"total_score={score_result['total_score']}, "
            f"recommendation={score_result['recommendation']}"
        )

        await ws_manager.send_event(
            company_id=company_id,
            campaign_id=campaign_id,
            event="candidate.scored",
            payload={
                "candidate_id": str(candidate_id),
                "candidate_name": candidate.name,
                "total_score": score_result["total_score"],
                "recommendation": score_result["recommendation"],
            },
        )

        return {
            "candidate_id": str(candidate_id),
            "total_score": score_result["total_score"],
            "recommendation": score_result["recommendation"],
        }

    except Exception as e:
        logger.error(
            f"[Agent5:ResumeIntelligence] Failed — candidate={candidate_id}: {e}",
            exc_info=True,
        )
        db.rollback()
        try:
            resume.parse_status = ParseStatus.failed
            db.commit()
        except Exception as mark_failed_err:
            logger.error(
                f"[Agent5:ResumeIntelligence] Could not mark resume as failed "
                f"for candidate={candidate_id}: {mark_failed_err}"
            )
            db.rollback()

        await ws_manager.send_event(
            company_id=company_id,
            campaign_id=campaign_id,
            event="agent.failed",
            payload={
                "agent": "resume_intelligence",
                "candidate_id": str(candidate_id),
                "error": str(e),
            },
        )
        raise


# ── Internal helpers ─────────────────────────────────────────────────────────

def _build_embedding_text(parsed: dict) -> str:
    """Flattens a parsed resume profile into one text block suitable for
    embedding — used for future semantic candidate search (e.g. "find
    candidates similar to X" across campaigns), not for scoring itself."""
    parts: list[str] = []
    if parsed.get("skills"):
        parts.append("Skills: " + ", ".join(parsed["skills"]))
    for edu in parsed.get("education", []):
        degree = edu.get("degree", "")
        institution = edu.get("institution", "")
        if degree or institution:
            parts.append(f"Education: {degree} at {institution}".strip())
    for proj in parsed.get("projects", []):
        name = proj.get("name", "")
        tech = proj.get("tech_stack", "")
        if name:
            parts.append(f"Project: {name} ({tech})".strip())
    for exp in parsed.get("experience", []):
        role = exp.get("role", "")
        company = exp.get("company", "")
        if role or company:
            parts.append(f"Experience: {role} at {company}".strip())
    if parsed.get("certifications"):
        parts.append("Certifications: " + ", ".join(parsed["certifications"]))
    return "\n".join(parts)


def _build_summary(parsed: dict) -> str:
    """Builds a short human-readable summary line from parsed data, since
    resume_parser.py doesn't generate one directly (no extra Groq call
    spent on a field that's mostly a convenience for the HR dashboard)."""
    top_degree = parsed["education"][0]["degree"] if parsed.get("education") else "N/A"
    skills_preview = ", ".join(parsed["skills"][:5]) if parsed.get("skills") else "No skills listed"
    project_count = len(parsed.get("projects", []))
    cert_count = len(parsed.get("certifications", []))
    return (
        f"{top_degree} | Key skills: {skills_preview} | "
        f"{project_count} project(s), {cert_count} certification(s)"
    )
