"""
Resumes API -- candidate registration + resume upload, parsing trigger,
and parsed-resume retrieval.

Milestone 4, Task 4.6.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware import get_current_company
from app.models.campaign import Campaign
from app.models.candidate import Candidate, CandidateStatus, ParseStatus, Resume
from app.models.company import Company
from app.services.storage import resume_key, upload_file
from app.tasks.evaluation_tasks import process_resume_task

logger = logging.getLogger("hireflow.api.resumes")

router = APIRouter(prefix="/api/v1", tags=["resumes"])

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5MB
ALLOWED_CONTENT_TYPE = "application/pdf"

CERTIFICATION_STRENGTH_PREFIX = "Certification: "


def _envelope(success: bool, message: str, data=None, error: str = None):
    return {
        "success": success,
        "message": message,
        "data": data,
        "error": error,
        "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
    }


def _get_open_campaign(db: Session, campaign_id: UUID) -> Campaign:
    """Public-facing lookup -- no company scoping, since the applicant has
    no Clerk session. campaign_id in the URL IS the scope: it's a
    long, effectively unguessable UUID, same trust model as any
    unauthenticated "apply via this link" flow (Greenhouse, Lever, etc.)."""
    from app.models.campaign import CampaignStatus

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status != CampaignStatus.active:
        raise HTTPException(
            status_code=400,
            detail="This campaign is not currently accepting applications",
        )
    return campaign


def _get_owned_campaign(db: Session, campaign_id: UUID, company: Company) -> Campaign:
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.company_id == company.id,
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def _resume_to_dict(resume: Resume) -> dict:
    return {
        "id": str(resume.id),
        "file_name": resume.file_name,
        "file_size_kb": resume.file_size_kb,
        "parse_status": resume.parse_status.value if resume.parse_status else None,
        "uploaded_at": resume.uploaded_at.isoformat() if resume.uploaded_at else None,
        "parsed_at": resume.parsed_at.isoformat() if resume.parsed_at else None,
    }


# -- POST /campaigns/{campaign_id}/resumes/upload ----------------------------

@router.post("/campaigns/{campaign_id}/resumes/upload", status_code=status.HTTP_201_CREATED)
async def upload_resume(
    campaign_id: UUID,
    files: List[UploadFile] = File(...),
    candidate_name: str = Form(...),
    candidate_email: str = Form(...),
    candidate_phone: Optional[str] = Form(None),
    cgpa: Optional[float] = Form(None),
    college_id: Optional[UUID] = Form(None),
    db: Session = Depends(get_db),
):
    """Registers one candidate and uploads their resume.

    PUBLIC endpoint, intentionally unauthenticated -- this is the
    student's own application submission, not an HR action, so there's
    no Clerk session to require. campaign_id in the URL is the access
    scope; company_id is derived from the campaign itself rather than
    accepted as input, so a caller can't spoof which company they're
    applying to. Only campaigns with status=active accept uploads.

    Accepts a list under `files` for form-data compatibility (`files[]`
    from a browser), but only the first PDF found is stored -- the DB
    schema (Resume.candidate_id is unique) supports exactly one resume
    per candidate. Any additional files are ignored with a warning.
    """
    campaign = _get_open_campaign(db, campaign_id)
    company_id = campaign.company_id

    if not files:
        raise HTTPException(status_code=400, detail="No file provided")

    resume_file: Optional[UploadFile] = None
    for f in files:
        if f.content_type == ALLOWED_CONTENT_TYPE:
            resume_file = f
            break
    if resume_file is None:
        raise HTTPException(status_code=400, detail="PDF files only")
    if len(files) > 1:
        logger.warning(
            f"[Resumes:Upload] {len(files)} files submitted for one candidate "
            f"upload; only '{resume_file.filename}' will be stored as the resume."
        )

    file_bytes = await resume_file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File too large. Max 5MB")

    if college_id is not None:
        from app.models.campaign import College
        college = db.query(College).filter(College.id == college_id).first()
        if not college:
            raise HTTPException(status_code=404, detail="College not found")

    existing = db.query(Candidate).filter(
        Candidate.campaign_id == campaign_id,
        Candidate.email == candidate_email,
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Candidate with this email already registered for this campaign",
        )

    candidate = Candidate(
        company_id=company_id,
        campaign_id=campaign_id,
        college_id=college_id,
        name=candidate_name,
        email=candidate_email,
        phone=candidate_phone,
        current_cgpa=cgpa,
        status=CandidateStatus.registered,
    )
    db.add(candidate)
    db.flush()

    key = resume_key(str(company_id), str(campaign_id), str(candidate.id))
    try:
        file_url = upload_file(file_bytes, key, content_type=ALLOWED_CONTENT_TYPE)
    except Exception as e:
        db.rollback()
        logger.error(f"[Resumes:Upload] Storage upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail="Failed to upload resume to storage")

    resume = Resume(
        candidate_id=candidate.id,
        file_url=file_url,
        file_name=resume_file.filename or "resume.pdf",
        file_size_kb=len(file_bytes) // 1024,
        parse_status=ParseStatus.pending,
    )
    db.add(resume)
    db.commit()
    db.refresh(candidate)

    process_resume_task.delay(str(candidate.id), str(campaign_id), str(company_id))
    logger.info(f"[Resumes:Upload] Queued process_resume_task for candidate={candidate.id}")

    return _envelope(True, "Resume uploaded, parsing queued", {
        "candidates_created": [
            {"candidate_id": str(candidate.id), "name": candidate.name, "status": candidate.status.value}
        ]
    })


# -- POST /campaigns/{campaign_id}/resumes/parse-all --------------------------

@router.post("/campaigns/{campaign_id}/resumes/parse-all")
def parse_all_resumes(
    campaign_id: UUID,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Queues parsing for every unprocessed (pending or failed) resume in
    this campaign -- useful after a bulk upload or to retry failures."""
    _get_owned_campaign(db, campaign_id, company)

    unprocessed = (
        db.query(Resume)
        .join(Candidate, Resume.candidate_id == Candidate.id)
        .filter(
            Candidate.campaign_id == campaign_id,
            Candidate.company_id == company.id,
            Resume.parse_status.in_([ParseStatus.pending, ParseStatus.failed]),
        )
        .all()
    )

    queued = 0
    for resume in unprocessed:
        process_resume_task.delay(str(resume.candidate_id), str(campaign_id), str(company.id))
        queued += 1

    logger.info(f"[Resumes:ParseAll] Queued {queued} resumes for campaign={campaign_id}")
    return _envelope(True, f"Queued {queued} resume(s) for parsing", {"queued": queued})


# -- GET /candidates/{candidate_id}/resume -------------------------------------

@router.get("/candidates/{candidate_id}/resume")
def get_candidate_resume(
    candidate_id: UUID,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Returns the candidate's resume metadata, parsed profile, and score
    breakdown -- everything the HR dashboard needs for one candidate."""
    candidate = db.query(Candidate).filter(
        Candidate.id == candidate_id,
        Candidate.company_id == company.id,
    ).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if not candidate.resume:
        raise HTTPException(status_code=404, detail="No resume uploaded for this candidate")

    data = {
        "candidate_id": str(candidate.id),
        "candidate_name": candidate.name,
        "resume": _resume_to_dict(candidate.resume),
        "profile": None,
        "score": None,
    }

    if candidate.profile:
        p = candidate.profile
        data["profile"] = {
            "skills": p.skills or [],
            "education": p.education or [],
            "experience": p.experience or [],
            "projects": p.projects or [],
            "certifications": p.certifications or [],
            "summary": p.summary,
        }

    if candidate.score:
        s = candidate.score
        strengths = s.strengths or []

        # certification_bonus/relevant_certifications aren't separate DB
        # columns (score_candidate() folds them into total_score + strengths
        # already) -- derived here for display rather than adding a
        # migration for two fields fully recoverable from existing data.
        base_total = (s.skills_score or 0) + (s.education_score or 0) + \
                     (s.project_score or 0) + (s.experience_score or 0)
        certification_bonus = round(max(0.0, (s.total_score or 0) - base_total), 2)
        relevant_certifications = [
            strength[len(CERTIFICATION_STRENGTH_PREFIX):]
            for strength in strengths
            if strength.startswith(CERTIFICATION_STRENGTH_PREFIX)
        ]

        data["score"] = {
            "skills_score": s.skills_score,
            "education_score": s.education_score,
            "project_score": s.project_score,
            "experience_score": s.experience_score,
            "certification_bonus": certification_bonus,
            "total_score": s.total_score,
            "recommendation": s.recommendation.value if s.recommendation else None,
            "strengths": strengths,
            "gaps": s.gaps or [],
            "relevant_certifications": relevant_certifications,
            "is_overridden": s.is_overridden,
        }

    return _envelope(True, "OK", data)