"""
Dashboard API — Real-time stats from the database.
Milestone 1: Live aggregated data for the HR dashboard.
"""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.middleware import get_current_company
from app.models.company import Company
from app.models.campaign import Campaign, CampaignStatus, Checkpoint, CheckpointStatus, EmailLog
from app.models.candidate import Candidate, CandidateStatus
from app.models.interview import InterviewSession
from app.models.offer import Offer

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


def _envelope(success: bool, message: str, data=None, error: str = None):
    return {
        "success": success,
        "message": message,
        "data": data,
        "error": error,
        "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
    }


@router.get("/stats")
def get_stats(
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Live dashboard stats aggregated from DB."""
    cid = company.id

    total_campaigns = db.query(func.count(Campaign.id)).filter(Campaign.company_id == cid).scalar() or 0
    active_campaigns = db.query(func.count(Campaign.id)).filter(
        Campaign.company_id == cid, Campaign.status == CampaignStatus.active
    ).scalar() or 0

    total_candidates = db.query(func.count(Candidate.id)).filter(Candidate.company_id == cid).scalar() or 0
    shortlisted = db.query(func.count(Candidate.id)).filter(
        Candidate.company_id == cid, Candidate.status == CandidateStatus.shortlisted
    ).scalar() or 0
    selected = db.query(func.count(Candidate.id)).filter(
        Candidate.company_id == cid, Candidate.status == CandidateStatus.selected
    ).scalar() or 0

    pending_checkpoints = db.query(func.count(Checkpoint.id)).join(
        Campaign, Campaign.id == Checkpoint.campaign_id
    ).filter(
        Campaign.company_id == cid,
        Checkpoint.status == CheckpointStatus.pending,
    ).scalar() or 0

    offers_issued = db.query(func.count(Offer.id)).join(
        Candidate, Candidate.id == Offer.candidate_id
    ).filter(Candidate.company_id == cid).scalar() or 0

    return _envelope(True, "OK", {
        "totalCampaigns": total_campaigns,
        "activeCampaigns": active_campaigns,
        "totalCandidates": total_candidates,
        "shortlistedCandidates": shortlisted,
        "selectedCandidates": selected,
        "pendingCheckpoints": pending_checkpoints,
        "offersIssued": offers_issued,
        "hiringRate": round((selected / total_candidates * 100), 1) if total_candidates > 0 else 0.0,
    })


@router.get("/funnel")
def get_funnel(
    campaign_id: str = None,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Candidate funnel breakdown by status."""
    cid = company.id
    q = db.query(Candidate.status, func.count(Candidate.id)).filter(Candidate.company_id == cid)
    if campaign_id:
        q = q.filter(Candidate.campaign_id == campaign_id)
    rows = q.group_by(Candidate.status).all()

    funnel = {s.value: 0 for s in CandidateStatus}
    for status_val, count in rows:
        funnel[status_val.value] = count

    return _envelope(True, "OK", {"funnel": funnel, "campaign_id": campaign_id})


@router.get("/activity")
def get_activity(
    limit: int = 20,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Recent activity feed — latest candidates and checkpoints."""
    cid = company.id
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    # Recent candidates
    recent_candidates = db.query(Candidate).filter(
        Candidate.company_id == cid,
        Candidate.created_at >= cutoff,
    ).order_by(Candidate.created_at.desc()).limit(limit // 2).all()

    # Pending checkpoints
    pending = db.query(Checkpoint).join(
        Campaign, Campaign.id == Checkpoint.campaign_id
    ).filter(
        Campaign.company_id == cid,
        Checkpoint.status == CheckpointStatus.pending,
    ).order_by(Checkpoint.created_at.desc()).limit(limit // 2).all()

    activity = []
    for c in recent_candidates:
        activity.append({
            "type": "candidate_registered",
            "message": f"New candidate registered: {c.name}",
            "timestamp": c.created_at.isoformat(),
            "ref_id": str(c.id),
        })
    for cp in pending:
        activity.append({
            "type": "checkpoint_pending",
            "message": f"Checkpoint '{cp.stage_name}' awaiting approval",
            "timestamp": cp.created_at.isoformat(),
            "ref_id": str(cp.id),
        })

    activity.sort(key=lambda x: x["timestamp"], reverse=True)
    return _envelope(True, "OK", activity[:limit])
