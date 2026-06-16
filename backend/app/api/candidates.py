"""
Candidates API — Full CRUD + status management.
Milestone 1: Core candidate data operations.
"""
from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware import get_current_user, get_current_company
from app.models.company import CompanyUser, Company
from app.models.candidate import Candidate, CandidateStatus
from app.models.campaign import Campaign

router = APIRouter(prefix="/api/v1/candidates", tags=["candidates"])


def _envelope(success: bool, message: str, data=None, error: str = None):
    return {
        "success": success,
        "message": message,
        "data": data,
        "error": error,
        "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
    }


def _candidate_to_dict(c: Candidate) -> dict:
    d = {
        "id": str(c.id),
        "name": c.name,
        "email": c.email,
        "phone": c.phone,
        "batch_year": c.batch_year,
        "current_cgpa": c.current_cgpa,
        "status": c.status.value if c.status else None,
        "campaign_id": str(c.campaign_id),
        "college_id": str(c.college_id) if c.college_id else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }
    if c.profile:
        d["profile"] = {
            "skills": c.profile.skills or [],
            "summary": c.profile.summary,
        }
    if c.score:
        d["score"] = {
            "total_score": c.score.total_score,
            "recommendation": c.score.recommendation.value if c.score.recommendation else None,
        }
    return d


# ── Schemas ───────────────────────────────────────────────────────────────────

class CandidateCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    phone: Optional[str] = None
    campaign_id: UUID
    college_id: Optional[UUID] = None
    batch_year: Optional[int] = None
    current_cgpa: Optional[float] = Field(None, ge=0.0, le=10.0)


class StatusUpdate(BaseModel):
    status: CandidateStatus
    notes: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/")
def list_candidates(
    campaign_id: Optional[UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """List candidates for the authenticated company."""
    q = db.query(Candidate).filter(Candidate.company_id == company.id)

    if campaign_id:
        q = q.filter(Candidate.campaign_id == campaign_id)
    if status_filter:
        try:
            q = q.filter(Candidate.status == CandidateStatus(status_filter))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")
    if search:
        like = f"%{search}%"
        q = q.filter((Candidate.name.ilike(like)) | (Candidate.email.ilike(like)))

    total = q.count()
    candidates = q.order_by(Candidate.created_at.desc()).offset(offset).limit(limit).all()
    return _envelope(True, "OK", {
        "candidates": [_candidate_to_dict(c) for c in candidates],
        "total": total,
        "limit": limit,
        "offset": offset,
    })


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_candidate(
    payload: CandidateCreate,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Register a new candidate. Campaign must belong to the same company."""
    # Verify campaign ownership
    campaign = db.query(Campaign).filter(
        Campaign.id == payload.campaign_id,
        Campaign.company_id == company.id,
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Check for duplicate email within campaign
    existing = db.query(Candidate).filter(
        Candidate.campaign_id == payload.campaign_id,
        Candidate.email == str(payload.email),
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Candidate with this email already registered for this campaign")

    candidate = Candidate(
        company_id=company.id,
        campaign_id=payload.campaign_id,
        college_id=payload.college_id,
        name=payload.name,
        email=str(payload.email),
        phone=payload.phone,
        batch_year=payload.batch_year,
        current_cgpa=payload.current_cgpa,
        status=CandidateStatus.registered,
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return _envelope(True, "Candidate registered", _candidate_to_dict(candidate))


@router.get("/{candidate_id}")
def get_candidate(
    candidate_id: UUID,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Get full candidate details."""
    c = db.query(Candidate).filter(
        Candidate.id == candidate_id,
        Candidate.company_id == company.id,
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return _envelope(True, "OK", _candidate_to_dict(c))


@router.patch("/{candidate_id}/status")
def update_candidate_status(
    candidate_id: UUID,
    payload: StatusUpdate,
    current_user: CompanyUser = Depends(get_current_user),
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Update a candidate's pipeline status."""
    c = db.query(Candidate).filter(
        Candidate.id == candidate_id,
        Candidate.company_id == company.id,
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")

    old_status = c.status
    c.status = payload.status
    db.commit()
    db.refresh(c)
    return _envelope(True, f"Status updated: {old_status.value} → {payload.status.value}", _candidate_to_dict(c))


@router.get("/{candidate_id}/timeline")
def get_candidate_timeline(
    candidate_id: UUID,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Get a candidate's full activity timeline."""
    c = db.query(Candidate).filter(
        Candidate.id == candidate_id,
        Candidate.company_id == company.id,
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")

    timeline = [{"event": "registered", "timestamp": c.created_at.isoformat(), "notes": None}]

    if c.resume:
        timeline.append({
            "event": "resume_uploaded",
            "timestamp": c.resume.uploaded_at.isoformat(),
            "notes": c.resume.file_name,
        })
    for ar in (c.assessment_results or []):
        if ar.submission_at:
            timeline.append({
                "event": "assessment_submitted",
                "timestamp": ar.submission_at.isoformat(),
                "notes": f"Score: {ar.total_score}",
            })
    for session in (c.interview_sessions or []):
        if session.started_at:
            timeline.append({
                "event": "interview_conducted",
                "timestamp": session.started_at.isoformat(),
                "notes": session.notes,
            })
    if c.offer:
        timeline.append({
            "event": "offer_issued",
            "timestamp": c.offer.issued_at.isoformat() if c.offer.issued_at else None,
            "notes": f"CTC: {c.offer.ctc_lpa} LPA",
        })

    timeline.sort(key=lambda x: x["timestamp"] or "", reverse=False)
    return _envelope(True, "OK", {
        "candidate_id": str(candidate_id),
        "current_status": c.status.value,
        "timeline": timeline,
    })
