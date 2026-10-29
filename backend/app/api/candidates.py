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
from app.models.candidate import Candidate, CandidateStatus, Score, Recommendation
from app.models.campaign import Campaign, College

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


def _candidate_list_item(c: Candidate) -> dict:
    """Flat shape for the campaign-scoped candidates list -- matches
    Task 4.7 spec exactly: id, name, email, college, status, total_score,
    recommendation, nothing nested."""
    return {
        "id": str(c.id),
        "name": c.name,
        "email": c.email,
        "college": c.college.name if c.college else None,
        "status": c.status.value if c.status else None,
        "total_score": c.score.total_score if c.score else None,
        "recommendation": c.score.recommendation.value if c.score and c.score.recommendation else None,
    }


def _candidate_full_detail(c: Candidate) -> dict:
    """Full nested detail for GET /candidates/{id} -- candidate, profile,
    score, resume_url, assessment_results, offer, per Task 4.7 spec."""
    return {
        "candidate": {
            "id": str(c.id),
            "name": c.name,
            "email": c.email,
            "phone": c.phone,
            "college": c.college.name if c.college else None,
            "batch_year": c.batch_year,
            "current_cgpa": c.current_cgpa,
            "status": c.status.value if c.status else None,
            "campaign_id": str(c.campaign_id),
            "created_at": c.created_at.isoformat() if c.created_at else None,
        },
        "profile": {
            "skills": c.profile.skills or [],
            "education": c.profile.education or [],
            "experience": c.profile.experience or [],
            "projects": c.profile.projects or [],
            "certifications": c.profile.certifications or [],
            "summary": c.profile.summary,
        } if c.profile else None,
        "score": {
            "skills_score": c.score.skills_score,
            "education_score": c.score.education_score,
            "project_score": c.score.project_score,
            "experience_score": c.score.experience_score,
            "total_score": c.score.total_score,
            "recommendation": c.score.recommendation.value if c.score.recommendation else None,
            "strengths": c.score.strengths or [],
            "gaps": c.score.gaps or [],
            "is_overridden": c.score.is_overridden,
            "override_notes": c.score.override_notes,
        } if c.score else None,
        "resume_url": c.resume.file_url if c.resume else None,
        "assessment_results": [
            {
                "round_id": str(ar.round_id) if ar.round_id else None,
                "mcq_score": ar.mcq_score,
                "coding_score": ar.coding_score,
                "written_score": ar.written_score,
                "total_score": ar.total_score,
                "auto_evaluated": ar.auto_evaluated,
                "submission_at": ar.submission_at.isoformat() if ar.submission_at else None,
            }
            for ar in (c.assessment_results or [])
        ],
        "offer": {
            "status": c.offer.status.value if c.offer.status else None,
            "stipend_offered": c.offer.stipend_offered,
            "joining_date": c.offer.joining_date.isoformat() if c.offer.joining_date else None,
            "sent_at": c.offer.sent_at.isoformat() if c.offer.sent_at else None,
            "response_at": c.offer.response_at.isoformat() if c.offer.response_at else None,
        } if c.offer else None,
    }


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


class ScoreOverride(BaseModel):
    override_recommendation: Recommendation
    notes: Optional[str] = Field(None, max_length=2000)


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
    return _envelope(True, "OK", _candidate_full_detail(c))


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


@router.patch("/{candidate_id}/score")
def override_candidate_score(
    candidate_id: UUID,
    payload: ScoreOverride,
    current_user: CompanyUser = Depends(get_current_user),
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """HR overrides the AI-generated recommendation for a candidate.

    Does NOT touch the underlying component scores (skills_score,
    project_score, etc.) -- those stay as the AI computed them, as a
    factual record. Only the recommendation itself changes, flagged via
    is_overridden so the dashboard can visually distinguish AI vs
    HR-decided recommendations.
    """
    c = db.query(Candidate).filter(
        Candidate.id == candidate_id,
        Candidate.company_id == company.id,
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if not c.score:
        raise HTTPException(
            status_code=400,
            detail="Candidate has not been scored yet -- nothing to override",
        )

    old_recommendation = c.score.recommendation
    c.score.recommendation = payload.override_recommendation
    c.score.is_overridden = True
    c.score.override_by = current_user.id
    c.score.override_notes = payload.notes
    db.commit()
    db.refresh(c.score)

    old_value = old_recommendation.value if old_recommendation else "none"
    return _envelope(
        True,
        f"Recommendation overridden: {old_value} → {payload.override_recommendation.value}",
        _candidate_full_detail(c),
    )


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
            "timestamp": c.offer.sent_at.isoformat() if c.offer.sent_at else None,
            "notes": f"Stipend: {c.offer.stipend_offered}" if c.offer.stipend_offered else None,
        })

    timeline.sort(key=lambda x: x["timestamp"] or "", reverse=False)
    return _envelope(True, "OK", {
        "candidate_id": str(candidate_id),
        "current_status": c.status.value,
        "timeline": timeline,
    })


# ── Campaign-scoped candidates list (Task 4.7) ─────────────────────────────────
# Separate router since the path lives under /campaigns/, not /candidates/.

campaign_candidates_router = APIRouter(prefix="/api/v1/campaigns", tags=["candidates"])


@campaign_candidates_router.get("/{campaign_id}/candidates")
def list_campaign_candidates(
    campaign_id: UUID,
    status_filter: Optional[str] = Query(None, alias="status"),
    sort: str = Query("score", description="score | name | date"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Candidates for one campaign, in the flat shape a shortlist/ranking
    table needs directly -- id, name, email, college, status, total_score,
    recommendation. Use GET /candidates/{id} for the full nested detail."""
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.company_id == company.id,
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    q = db.query(Candidate).filter(
        Candidate.campaign_id == campaign_id,
        Candidate.company_id == company.id,
    )

    if status_filter:
        try:
            q = q.filter(Candidate.status == CandidateStatus(status_filter))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")

    total = q.count()

    if sort == "score":
        q = q.outerjoin(Score, Score.candidate_id == Candidate.id).order_by(Score.total_score.desc().nullslast())
    elif sort == "name":
        q = q.order_by(Candidate.name.asc())
    elif sort == "date":
        q = q.order_by(Candidate.created_at.desc())
    else:
        raise HTTPException(status_code=400, detail="sort must be one of: score, name, date")

    offset = (page - 1) * limit
    candidates = q.offset(offset).limit(limit).all()

    return _envelope(True, "OK", {
        "candidates": [_candidate_list_item(c) for c in candidates],
        "total": total,
        "page": page,
    })