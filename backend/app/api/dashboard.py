"""
Dashboard API — Real-time stats from the database.
Milestone 1: /stats, /funnel, /activity. Milestone 4 (Task 4.10): GET /dashboard and
GET /dashboard/pipeline/{campaign_id}.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.graph.checkpoint_manager import CHECKPOINT_STAGES
from app.middleware import get_current_company
from app.models.company import Company
from app.models.campaign import (
    Campaign, CampaignStatus, Checkpoint, CheckpointStatus, College, EmailLog,
)
from app.models.candidate import AssessmentResult, Candidate, CandidateStatus, Score
from app.models.interview import InterviewSession
from app.models.offer import Offer, OfferStatus

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


# ══════════════════════════════════════════════════════════════════════════════
# Task 4.10 — GET /dashboard and GET /dashboard/pipeline/{campaign_id}
# ══════════════════════════════════════════════════════════════════════════════
#
# "How far did each candidate get" is NOT just Candidate.status: Evaluation
# marks everyone it doesn't shortlist as `rejected`, and `rejected`/`on_hold`
# say nothing about the stage reached. There is no stage-history column, so
# the furthest stage is inferred from the strongest evidence available:
#   - status implies a stage (shortlisted, interview_done, selected, ...)
#   - a Score row            -> screened
#   - an AssessmentResult    -> assessed
#   - a started interview    -> interviewed
#   - an Offer that was sent -> offer_sent (accepted -> offer_accepted)
# Known limit: someone HR manually rejects between screening and assessment
# (with no later records) still counts as screened, not shortlisted.

FUNNEL_STAGES = [
    "registered", "screened", "shortlisted", "assessed",
    "interviewed", "selected", "offer_sent", "offer_accepted",
]
_RANK = {name: i for i, name in enumerate(FUNNEL_STAGES)}

# Furthest funnel stage implied by the status alone. rejected / on_hold are
# intentionally absent: they carry no information about how far someone got.
_STATUS_STAGE = {
    CandidateStatus.registered: "registered",
    CandidateStatus.screened: "screened",
    CandidateStatus.shortlisted: "shortlisted",
    CandidateStatus.assessment_pending: "shortlisted",
    CandidateStatus.assessment_done: "assessed",
    CandidateStatus.interview_scheduled: "assessed",
    CandidateStatus.interview_done: "interviewed",
    CandidateStatus.selected: "selected",
    CandidateStatus.offer_sent: "offer_sent",
    CandidateStatus.offer_declined: "offer_sent",
    CandidateStatus.offer_accepted: "offer_accepted",
    CandidateStatus.onboarding: "offer_accepted",
}
_OFFER_SENT = {OfferStatus.sent, OfferStatus.accepted, OfferStatus.declined, OfferStatus.expired}

_STAGE_LABELS = {
    "checkpoint_jd": "JD Approval",
    "checkpoint_campus": "Campus Selection",
    "checkpoint_shortlist": "Shortlist Approval",
    "checkpoint_assessment": "Assessment Results",
    "checkpoint_schedule": "Interview Schedule",
    "checkpoint_interview": "Interview Results",
    "checkpoint_final": "Final Selection",
    "checkpoint_offer": "Offer Approval",
}
_CHECKPOINT_STATUS_LABEL = {
    CheckpointStatus.approved: "completed",
    CheckpointStatus.pending: "awaiting_approval",
    CheckpointStatus.rejected: "rejected",
    CheckpointStatus.revision_requested: "revision_requested",
    CheckpointStatus.rolled_back: "rolled_back",
}


def _to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Columns mix naive and tz-aware datetimes; normalise before comparing."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    d = _to_utc(dt)
    return d.isoformat() if d else None


# -- pure computations (unit-testable without a database) ----------------------

def _reached_ranks(statuses: dict, scored: set, assessed: set,
                   interviewed: set, offers: dict) -> dict:
    """candidate_id -> index of the furthest FUNNEL_STAGES stage reached."""
    ranks = {}
    for cid, status in statuses.items():
        best = _RANK["registered"]
        implied = _STATUS_STAGE.get(status)
        if implied:
            best = max(best, _RANK[implied])
        if cid in scored:
            best = max(best, _RANK["screened"])
        if cid in assessed:
            best = max(best, _RANK["assessed"])
        if cid in interviewed:
            best = max(best, _RANK["interviewed"])
        offer_status = offers.get(cid)
        if offer_status in _OFFER_SENT:
            best = max(best, _RANK["offer_sent"])
        if offer_status == OfferStatus.accepted:
            best = max(best, _RANK["offer_accepted"])
        ranks[cid] = best
    return ranks


def _stage_counts(ranks: dict) -> dict:
    """Number of candidates that reached AT LEAST each stage."""
    return {stage: sum(1 for r in ranks.values() if r >= i)
            for i, stage in enumerate(FUNNEL_STAGES)}


def _funnel_rows(counts: dict) -> list:
    """conversion_rate = share of the PREVIOUS stage that made it to this one."""
    rows, prev = [], None
    for stage in FUNNEL_STAGES:
        count = counts[stage]
        if prev is None:
            rate = 100.0 if count else 0.0
        else:
            rate = round(count / prev * 100, 1) if prev else 0.0
        rows.append({"stage": stage, "count": count, "conversion_rate": rate})
        prev = count
    return rows


def _top_colleges(ranks: dict, college_of: dict, names: dict, limit: int = 5) -> list:
    """Colleges ranked by hires (candidates who reached `selected`)."""
    selected_rank = _RANK["selected"]
    stats: dict = {}
    for cid, college_id in college_of.items():
        if college_id is None or college_id not in names:
            continue
        s = stats.setdefault(college_id, {"candidates": 0, "hired": 0})
        s["candidates"] += 1
        if ranks.get(cid, 0) >= selected_rank:
            s["hired"] += 1
    rows = [{
        "college": names[college_id],
        "college_id": str(college_id),
        "candidates": s["candidates"],
        "hired": s["hired"],
        "conversion_rate": round(s["hired"] / s["candidates"] * 100, 1),
    } for college_id, s in stats.items()]
    rows.sort(key=lambda r: (-r["hired"], -r["conversion_rate"], -r["candidates"], r["college"]))
    return rows[:limit]


def _avg_days_to_hire(pairs: list) -> Optional[float]:
    """Mean days from registration to accepting the offer; None if no hires yet."""
    spans = []
    for created, responded in pairs:
        created, responded = _to_utc(created), _to_utc(responded)
        if created and responded and responded >= created:
            spans.append((responded - created).total_seconds() / 86400)
    return round(sum(spans) / len(spans), 1) if spans else None


def _merge_activity(items: list, limit: int) -> list:
    items.sort(key=lambda x: x["timestamp"] or "", reverse=True)
    return items[:limit]


# -- database access -----------------------------------------------------------

def _get_owned_campaign(db: Session, campaign_id: UUID, company: Company) -> Campaign:
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id, Campaign.company_id == company.id,
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def _scoped(q, company_id, campaign_id):
    """Restrict a query that already joins Candidate to this company/campaign."""
    q = q.filter(Candidate.company_id == company_id)
    if campaign_id:
        q = q.filter(Candidate.campaign_id == campaign_id)
    return q


def _load_funnel(db: Session, company_id, campaign_id=None):
    """Returns (ranks, college_of) for every candidate in scope."""
    rows = _scoped(
        db.query(Candidate.id, Candidate.status, Candidate.college_id), company_id, campaign_id,
    ).all()
    statuses = {r[0]: r[1] for r in rows}
    college_of = {r[0]: r[2] for r in rows}

    def ids(q):
        return {r[0] for r in q.all()}

    scored = ids(_scoped(
        db.query(Score.candidate_id).join(Candidate, Candidate.id == Score.candidate_id),
        company_id, campaign_id))
    assessed = ids(_scoped(
        db.query(AssessmentResult.candidate_id).join(Candidate, Candidate.id == AssessmentResult.candidate_id),
        company_id, campaign_id))
    interviewed = ids(_scoped(
        db.query(InterviewSession.candidate_id)
        .join(Candidate, Candidate.id == InterviewSession.candidate_id)
        .filter(InterviewSession.started_at.isnot(None)),
        company_id, campaign_id))
    offers = {r[0]: r[1] for r in _scoped(
        db.query(Offer.candidate_id, Offer.status).join(Candidate, Candidate.id == Offer.candidate_id),
        company_id, campaign_id).all()}

    return _reached_ranks(statuses, scored, assessed, interviewed, offers), college_of


def _pending_checkpoints(db: Session, company_id, campaign_id=None):
    q = (
        db.query(Checkpoint, Campaign.title)
        .join(Campaign, Campaign.id == Checkpoint.campaign_id)
        .filter(Campaign.company_id == company_id, Checkpoint.status == CheckpointStatus.pending)
    )
    if campaign_id:
        q = q.filter(Checkpoint.campaign_id == campaign_id)
    return q.order_by(Checkpoint.created_at.asc()).all()


def _recent_activity(db: Session, company_id, campaign_id=None, limit: int = 10) -> list:
    """Latest events across registrations, scoring, checkpoint decisions and
    offers. Each source is capped at `limit` before merging."""
    items = []

    q = db.query(Candidate.id, Candidate.name, Candidate.created_at)
    q = q.filter(Candidate.company_id == company_id)
    if campaign_id:
        q = q.filter(Candidate.campaign_id == campaign_id)
    for cid, name, created in q.order_by(Candidate.created_at.desc()).limit(limit).all():
        items.append({"type": "candidate_registered", "message": f"{name} registered",
                      "timestamp": _iso(created), "ref_id": str(cid)})

    q = _scoped(
        db.query(Candidate.id, Candidate.name, Score.total_score, Score.scored_at)
        .join(Score, Score.candidate_id == Candidate.id), company_id, campaign_id)
    for cid, name, total, scored_at in q.order_by(Score.scored_at.desc()).limit(limit).all():
        items.append({"type": "candidate_scored", "message": f"{name} scored {total}",
                      "timestamp": _iso(scored_at), "ref_id": str(cid)})

    q = (
        db.query(Checkpoint, Campaign.title)
        .join(Campaign, Campaign.id == Checkpoint.campaign_id)
        .filter(Campaign.company_id == company_id)
    )
    if campaign_id:
        q = q.filter(Checkpoint.campaign_id == campaign_id)
    for cp, title in q.order_by(Checkpoint.created_at.desc()).limit(limit).all():
        label = _STAGE_LABELS.get(cp.stage_name, cp.stage_name)
        if cp.status == CheckpointStatus.pending:
            items.append({"type": "checkpoint_pending",
                          "message": f"{label} awaiting approval ({title})",
                          "timestamp": _iso(cp.created_at), "ref_id": str(cp.id)})
        else:
            items.append({"type": f"checkpoint_{cp.status.value}",
                          "message": f"{label} {cp.status.value.replace('_', ' ')} ({title})",
                          "timestamp": _iso(cp.decided_at or cp.created_at), "ref_id": str(cp.id)})

    q = _scoped(
        db.query(Candidate.id, Candidate.name, Offer.sent_at)
        .join(Offer, Offer.candidate_id == Candidate.id).filter(Offer.sent_at.isnot(None)),
        company_id, campaign_id)
    for cid, name, sent_at in q.order_by(Offer.sent_at.desc()).limit(limit).all():
        items.append({"type": "offer_sent", "message": f"Offer sent to {name}",
                      "timestamp": _iso(sent_at), "ref_id": str(cid)})

    return _merge_activity(items, limit)


# -- GET /dashboard ------------------------------------------------------------

@router.get("")
@router.get("/", include_in_schema=False)
def get_dashboard(
    campaign_id: Optional[UUID] = Query(None, description="Limit everything to one campaign"),
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """One-call HR dashboard: headline numbers, funnel with stage-to-stage
    conversion, time to hire, best colleges, approvals waiting on HR, and
    recent activity. Optional ?campaign_id= narrows it to a single campaign."""
    cid = company.id

    if campaign_id:
        campaign = _get_owned_campaign(db, campaign_id, company)
        active_campaigns = 1 if campaign.status == CampaignStatus.active else 0
    else:
        active_campaigns = db.query(func.count(Campaign.id)).filter(
            Campaign.company_id == cid, Campaign.status == CampaignStatus.active,
        ).scalar() or 0

    ranks, college_of = _load_funnel(db, cid, campaign_id)
    counts = _stage_counts(ranks)

    college_ids = {c for c in college_of.values() if c is not None}
    names = {}
    if college_ids:
        names = {r[0]: r[1] for r in db.query(College.id, College.name)
                 .filter(College.id.in_(list(college_ids))).all()}

    hire_pairs = _scoped(
        db.query(Candidate.created_at, Offer.response_at)
        .join(Offer, Offer.candidate_id == Candidate.id)
        .filter(Offer.status == OfferStatus.accepted, Offer.response_at.isnot(None)),
        cid, campaign_id).all()

    pending = [{
        "checkpoint_id": str(cp.id),
        "stage": cp.stage_name,
        "stage_label": _STAGE_LABELS.get(cp.stage_name, cp.stage_name),
        "campaign_id": str(cp.campaign_id),
        "campaign_title": title,
        "waiting_since": _iso(cp.created_at),
    } for cp, title in _pending_checkpoints(db, cid, campaign_id)]

    return _envelope(True, "OK", {
        "summary": {
            "active_campaigns": active_campaigns,
            "total_candidates": counts["registered"],
            "shortlisted": counts["shortlisted"],
            "interviewed": counts["interviewed"],
            "selected": counts["selected"],
            "offers_sent": counts["offer_sent"],
            "offers_accepted": counts["offer_accepted"],
        },
        "funnel": _funnel_rows(counts),
        "time_to_hire_avg_days": _avg_days_to_hire(hire_pairs),
        "top_colleges": _top_colleges(ranks, college_of, names),
        "pending_approvals": pending,
        "recent_activity": _recent_activity(db, cid, campaign_id),
    })


# -- GET /dashboard/pipeline/{campaign_id} -------------------------------------

@router.get("/pipeline/{campaign_id}")
def get_pipeline_status(
    campaign_id: UUID,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Live pipeline view for one campaign: where it is across the 8 HR
    checkpoints, what is waiting on HR, and how candidates are flowing."""
    campaign = _get_owned_campaign(db, campaign_id, company)

    rows = (
        db.query(Checkpoint)
        .filter(Checkpoint.campaign_id == campaign_id)
        .order_by(Checkpoint.created_at.asc())
        .all()
    )
    latest = {}
    for cp in rows:  # ascending, so the last row per stage wins
        latest[cp.stage_name] = cp

    stages = []
    for order, name in enumerate(CHECKPOINT_STAGES, start=1):
        cp = latest.get(name)
        if cp is None:
            status, completed_at = "not_started", None
        else:
            status = _CHECKPOINT_STATUS_LABEL.get(cp.status, cp.status.value)
            completed_at = _iso(cp.decided_at) if cp.status == CheckpointStatus.approved else None
        stages.append({
            "order": order,
            "name": name,
            "label": _STAGE_LABELS.get(name, name),
            "status": status,
            "completed_at": completed_at,
        })

    current = next((s["name"] for s in stages if s["status"] != "completed"), "completed")

    pending_cp = next(
        (cp for cp in sorted(rows, key=lambda c: c.created_at, reverse=True)
         if cp.status == CheckpointStatus.pending), None)

    ranks, _ = _load_funnel(db, company.id, campaign_id)
    counts = _stage_counts(ranks)

    return _envelope(True, "OK", {
        "campaign_id": str(campaign.id),
        "campaign_title": campaign.title,
        "campaign_status": campaign.status.value,
        "pipeline_started": bool(rows),
        "current_stage": current,
        "stages": stages,
        "pending_checkpoint": {
            "checkpoint_id": str(pending_cp.id),
            "stage": pending_cp.stage_name,
            "stage_label": _STAGE_LABELS.get(pending_cp.stage_name, pending_cp.stage_name),
            "waiting_since": _iso(pending_cp.created_at),
        } if pending_cp else None,
        "candidate_flow": {
            "registered": counts["registered"],
            "screened": counts["screened"],
            "shortlisted": counts["shortlisted"],
            "assessed": counts["assessed"],
            "interviewed": counts["interviewed"],
            "selected": counts["selected"],
        },
    })