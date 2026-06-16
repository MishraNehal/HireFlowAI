"""
Interviews API — Schedule, manage, and retrieve interview sessions + evaluations.
Milestone 1: Core interview lifecycle (schedule → start → end → evaluate).
"""
from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware import get_current_user, get_current_company
from app.models.company import CompanyUser, Company
from app.models.campaign import Campaign
from app.models.candidate import Candidate
from app.models.interview import (
    InterviewSession, InterviewEvaluation,
    InterviewStatus, InterviewMode, InterviewRecommendation, EvaluatedBy,
)

router = APIRouter(prefix="/api/v1/interviews", tags=["interviews"])


def _envelope(success: bool, message: str, data=None, error: str = None):
    return {
        "success": success,
        "message": message,
        "data": data,
        "error": error,
        "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
    }


def _session_to_dict(s: InterviewSession) -> dict:
    base = {
        "id": str(s.id),
        "candidate_id": str(s.candidate_id),
        "campaign_id": str(s.campaign_id),
        "round_id": str(s.round_id) if s.round_id else None,
        "interview_mode": s.interview_mode.value if s.interview_mode else None,
        "status": s.status.value if s.status else None,
        "scheduled_at": s.scheduled_at.isoformat() if s.scheduled_at else None,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "ended_at": s.ended_at.isoformat() if s.ended_at else None,
        "duration_mins": s.duration_mins,
        "daily_room_url": s.daily_room_url,
        "recording_url": s.recording_url,
    }
    if s.evaluation:
        base["evaluation"] = _eval_to_dict(s.evaluation)
    return base


def _eval_to_dict(e: InterviewEvaluation) -> dict:
    return {
        "id": str(e.id),
        "session_id": str(e.session_id),
        "technical_score": e.technical_score,
        "communication_score": e.communication_score,
        "problem_solving": e.problem_solving,
        "confidence_score": e.confidence_score,
        "behavioral_score": e.behavioral_score,
        "overall_score": e.overall_score,
        "strengths": e.strengths or [],
        "concerns": e.concerns or [],
        "recommendation": e.recommendation.value if e.recommendation else None,
        "evaluated_by": e.evaluated_by.value if e.evaluated_by else None,
        "ai_reasoning": e.ai_reasoning,
        "hr_notes": e.hr_notes,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


# ── Schemas ───────────────────────────────────────────────────────────────────

class InterviewSchedule(BaseModel):
    candidate_id: UUID
    campaign_id: UUID
    round_id: Optional[UUID] = None
    interview_mode: InterviewMode = InterviewMode.ai_only
    scheduled_at: Optional[datetime] = None
    daily_room_url: Optional[str] = None


class InterviewEvaluationCreate(BaseModel):
    technical_score: Optional[float] = Field(None, ge=0, le=100)
    communication_score: Optional[float] = Field(None, ge=0, le=100)
    problem_solving: Optional[float] = Field(None, ge=0, le=100)
    confidence_score: Optional[float] = Field(None, ge=0, le=100)
    behavioral_score: Optional[float] = Field(None, ge=0, le=100)
    overall_score: Optional[float] = Field(None, ge=0, le=100)
    strengths: List[str] = Field(default_factory=list)
    concerns: List[str] = Field(default_factory=list)
    recommendation: Optional[InterviewRecommendation] = None
    ai_reasoning: Optional[str] = None
    hr_notes: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/")
def list_interviews(
    campaign_id: Optional[UUID] = Query(None),
    candidate_id: Optional[UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """List interview sessions for the authenticated company."""
    q = (
        db.query(InterviewSession)
        .join(Campaign, InterviewSession.campaign_id == Campaign.id)
        .filter(Campaign.company_id == company.id)
    )
    if campaign_id:
        q = q.filter(InterviewSession.campaign_id == campaign_id)
    if candidate_id:
        q = q.filter(InterviewSession.candidate_id == candidate_id)
    if status_filter:
        try:
            st = InterviewStatus(status_filter)
            q = q.filter(InterviewSession.status == st)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")

    total = q.count()
    sessions = q.order_by(InterviewSession.scheduled_at.desc()).offset(offset).limit(limit).all()
    return _envelope(True, "OK", {
        "interviews": [_session_to_dict(s) for s in sessions],
        "total": total,
        "limit": limit,
        "offset": offset,
    })


@router.post("/", status_code=status.HTTP_201_CREATED)
def schedule_interview(
    payload: InterviewSchedule,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Schedule a new interview session for a candidate."""
    campaign = db.query(Campaign).filter(
        Campaign.id == payload.campaign_id,
        Campaign.company_id == company.id,
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    candidate = db.query(Candidate).filter(
        Candidate.id == payload.candidate_id,
        Candidate.campaign_id == payload.campaign_id,
    ).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found in this campaign")

    session = InterviewSession(
        candidate_id=payload.candidate_id,
        campaign_id=payload.campaign_id,
        round_id=payload.round_id,
        interview_mode=payload.interview_mode,
        scheduled_at=payload.scheduled_at,
        daily_room_url=payload.daily_room_url,
        status=InterviewStatus.scheduled,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _envelope(True, "Interview scheduled", _session_to_dict(session))


@router.get("/{session_id}")
def get_interview(
    session_id: UUID,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Get an interview session by ID, including evaluation if present."""
    s = (
        db.query(InterviewSession)
        .join(Campaign, InterviewSession.campaign_id == Campaign.id)
        .filter(InterviewSession.id == session_id, Campaign.company_id == company.id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="Interview session not found")
    return _envelope(True, "OK", _session_to_dict(s))


@router.post("/{session_id}/start")
def start_interview(
    session_id: UUID,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Mark an interview as started."""
    s = (
        db.query(InterviewSession)
        .join(Campaign, InterviewSession.campaign_id == Campaign.id)
        .filter(InterviewSession.id == session_id, Campaign.company_id == company.id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="Interview session not found")
    if s.status != InterviewStatus.scheduled:
        raise HTTPException(status_code=400, detail=f"Cannot start interview in '{s.status.value}' status")

    s.status = InterviewStatus.started
    s.started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(s)
    return _envelope(True, "Interview started", _session_to_dict(s))


@router.post("/{session_id}/end")
def end_interview(
    session_id: UUID,
    recording_url: Optional[str] = None,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Mark an interview as completed."""
    s = (
        db.query(InterviewSession)
        .join(Campaign, InterviewSession.campaign_id == Campaign.id)
        .filter(InterviewSession.id == session_id, Campaign.company_id == company.id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="Interview session not found")
    if s.status != InterviewStatus.started:
        raise HTTPException(status_code=400, detail=f"Cannot end interview in '{s.status.value}' status")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    s.status = InterviewStatus.completed
    s.ended_at = now
    if s.started_at:
        s.duration_mins = int((now - s.started_at).total_seconds() / 60)
    if recording_url:
        s.recording_url = recording_url

    db.commit()
    db.refresh(s)
    return _envelope(True, "Interview ended", _session_to_dict(s))


@router.post("/{session_id}/no-show")
def mark_no_show(
    session_id: UUID,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Mark a candidate as no-show for the interview."""
    s = (
        db.query(InterviewSession)
        .join(Campaign, InterviewSession.campaign_id == Campaign.id)
        .filter(InterviewSession.id == session_id, Campaign.company_id == company.id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="Interview session not found")
    if s.status != InterviewStatus.scheduled:
        raise HTTPException(status_code=400, detail=f"Cannot mark no-show in '{s.status.value}' status")

    s.status = InterviewStatus.no_show
    db.commit()
    db.refresh(s)
    return _envelope(True, "Candidate marked as no-show", _session_to_dict(s))


@router.post("/{session_id}/evaluate", status_code=status.HTTP_201_CREATED)
def submit_evaluation(
    session_id: UUID,
    payload: InterviewEvaluationCreate,
    current_user: CompanyUser = Depends(get_current_user),
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Submit or update the evaluation for a completed interview."""
    s = (
        db.query(InterviewSession)
        .join(Campaign, InterviewSession.campaign_id == Campaign.id)
        .filter(InterviewSession.id == session_id, Campaign.company_id == company.id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="Interview session not found")
    if s.status != InterviewStatus.completed:
        raise HTTPException(status_code=400, detail="Can only evaluate completed interviews")

    existing = db.query(InterviewEvaluation).filter(
        InterviewEvaluation.session_id == session_id
    ).first()

    eval_data = payload.model_dump(exclude_none=True)

    if existing:
        for field, value in eval_data.items():
            setattr(existing, field, value)
        existing.evaluated_by = EvaluatedBy.human
        db.commit()
        db.refresh(existing)
        return _envelope(True, "Evaluation updated", _eval_to_dict(existing))
    else:
        evaluation = InterviewEvaluation(
            session_id=session_id,
            candidate_id=s.candidate_id,
            evaluated_by=EvaluatedBy.human,
            **eval_data,
        )
        db.add(evaluation)
        db.commit()
        db.refresh(evaluation)
        return _envelope(True, "Evaluation submitted", _eval_to_dict(evaluation))
