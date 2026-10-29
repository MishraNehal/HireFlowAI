"""
Colleges API -- campus partner directory + per-campaign college selection.

Milestone 4, Task 4.8.

Two routers:
  - router                      /api/v1/colleges              (global directory)
  - campaign_colleges_router    /api/v1/campaigns/{id}/colleges (per-campaign selection)

The directory is global (colleges are shared across tenants, seeded once);
only campaign selection is company-scoped.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware import get_current_company, get_current_user
from app.models.campaign import (
    Campaign,
    CampaignCollege,
    CampaignCollegeStatus,
    CampaignStatus,
    Checkpoint,
    CheckpointStatus,
    College,
    CollegeTier,
)
from app.models.company import Company, CompanyUser, UserRole
from app.schemas.college import CollegeCreate

logger = logging.getLogger("hireflow.api.colleges")

router = APIRouter(prefix="/api/v1/colleges", tags=["colleges"])
campaign_colleges_router = APIRouter(prefix="/api/v1/campaigns", tags=["colleges"])

CAMPUS_CHECKPOINT_STAGE = "checkpoint_campus"

# Colleges stored with full state names ("Madhya Pradesh"); API callers
# commonly send the 2-letter code ("MP"). Unknown values fall through to a
# case-insensitive exact match on the name.
_STATE_CODES = {
    "AP": "Andhra Pradesh", "AR": "Arunachal Pradesh", "AS": "Assam",
    "BR": "Bihar", "CG": "Chhattisgarh", "CH": "Chandigarh", "DL": "Delhi",
    "GA": "Goa", "GJ": "Gujarat", "HP": "Himachal Pradesh", "HR": "Haryana",
    "JH": "Jharkhand", "JK": "Jammu and Kashmir", "KA": "Karnataka",
    "KL": "Kerala", "LA": "Ladakh", "MH": "Maharashtra", "ML": "Meghalaya",
    "MN": "Manipur", "MP": "Madhya Pradesh", "MZ": "Mizoram", "NL": "Nagaland",
    "OD": "Odisha", "OR": "Odisha", "PB": "Punjab", "PY": "Puducherry",
    "RJ": "Rajasthan", "SK": "Sikkim", "TG": "Telangana", "TN": "Tamil Nadu",
    "TR": "Tripura", "TS": "Telangana", "UK": "Uttarakhand", "UP": "Uttar Pradesh",
    "UT": "Uttarakhand", "WB": "West Bengal",
}

_ACTIVE_STATUSES = (
    CampaignCollegeStatus.approved,
    CampaignCollegeStatus.contacted,
    CampaignCollegeStatus.confirmed,
)
_OUTREACH_STARTED = (CampaignCollegeStatus.contacted, CampaignCollegeStatus.confirmed)


def _envelope(success: bool, message: str, data=None, error: str = None):
    return {
        "success": success,
        "message": message,
        "data": data,
        "error": error,
        "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
    }


def require_admin(current_user: CompanyUser = Depends(get_current_user)) -> CompanyUser:
    """Admin-only gate. The colleges directory is shared across tenants,
    so adding to it is restricted to the admin role."""
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def _college_to_dict(c: College) -> dict:
    return {
        "id": str(c.id),
        "name": c.name,
        "city": c.city,
        "state": c.state,
        "tier": c.tier.value if c.tier else None,
        "placement_email": c.placement_email,
        "tpo_name": c.tpo_name,
        "tpo_contact": c.tpo_contact,
        "historical_rating": c.historical_rating,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _resolve_state(value: str) -> str:
    cleaned = value.strip()
    return _STATE_CODES.get(cleaned.upper(), cleaned)


def _apply_college_filters(q, tier: Optional[str], state: Optional[str]):
    if tier:
        try:
            q = q.filter(College.tier == CollegeTier(tier.lower()))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid tier '{tier}'. Use one of: "
                       f"{', '.join(t.value for t in CollegeTier)}",
            )
    if state and state.strip():
        q = q.filter(func.lower(College.state) == _resolve_state(state).lower())
    return q


# -- GET /colleges -------------------------------------------------------------

@router.get("/")
def list_colleges(
    tier: Optional[str] = Query(None, description="tier1 | tier2 | tier3"),
    state: Optional[str] = Query(None, description="State name or 2-letter code, e.g. MP"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _user: CompanyUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = _apply_college_filters(db.query(College), tier, state)
    total = q.count()
    colleges = (
        q.order_by(College.historical_rating.desc().nullslast(), College.name.asc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return _envelope(True, "OK", {
        "colleges": [_college_to_dict(c) for c in colleges],
        "total": total,
        "page": page,
        "limit": limit,
    })


# -- GET /colleges/{college_id} ------------------------------------------------

@router.get("/{college_id}")
def get_college(
    college_id: UUID,
    _user: CompanyUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    college = db.query(College).filter(College.id == college_id).first()
    if not college:
        raise HTTPException(status_code=404, detail="College not found")

    campaigns_participated = (
        db.query(CampaignCollege).filter(CampaignCollege.college_id == college_id).count()
    )
    data = _college_to_dict(college)
    data["campaigns_participated"] = campaigns_participated
    return _envelope(True, "OK", data)


# -- POST /colleges (admin only) -----------------------------------------------

@router.post("/", status_code=status.HTTP_201_CREATED)
def add_college(
    payload: CollegeCreate,
    _admin: CompanyUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    duplicate = db.query(College).filter(
        func.lower(College.name) == payload.name.strip().lower(),
        func.lower(func.coalesce(College.city, "")) == (payload.city or "").strip().lower(),
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="A college with this name and city already exists")

    college = College(
        name=payload.name.strip(),
        city=payload.city,
        state=payload.state,
        tier=payload.tier,
        placement_email=str(payload.placement_email) if payload.placement_email else None,
        tpo_name=payload.tpo_name,
        tpo_contact=payload.tpo_contact,
        historical_rating=payload.historical_rating,
    )
    db.add(college)
    db.commit()
    db.refresh(college)
    logger.info(f"[Colleges] Added college '{college.name}' ({college.id})")
    return _envelope(True, "College added", _college_to_dict(college))


# -- Campaign college selection ------------------------------------------------

class CollegeSelectionUpdate(BaseModel):
    add: List[UUID] = Field(default_factory=list, max_length=100)
    remove: List[UUID] = Field(default_factory=list, max_length=100)


def _get_owned_campaign(db: Session, campaign_id: UUID, company: Company) -> Campaign:
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.company_id == company.id,
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def _safe_uuid(value) -> Optional[UUID]:
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


def _build_campaign_colleges(db: Session, campaign: Campaign, include_removed: bool) -> dict:
    """Merges two sources into one view:
      1. AI recommendations -- Campus Discovery keeps these in the
         checkpoint_campus snapshot (it never writes CampaignCollege rows).
      2. CampaignCollege rows -- HR edits (approved/removed) and Outreach
         progress (contacted/confirmed/declined, timestamps, registrations).
    A DB row always wins over the AI default for that college.
    """
    checkpoint = (
        db.query(Checkpoint)
        .filter(
            Checkpoint.campaign_id == campaign.id,
            Checkpoint.stage_name == CAMPUS_CHECKPOINT_STAGE,
        )
        .order_by(Checkpoint.created_at.desc())
        .first()
    )

    ai_by_id: dict = {}
    if checkpoint:
        for entry in (checkpoint.state_snapshot or {}).get("selected_colleges") or []:
            cid = _safe_uuid(entry.get("id")) if isinstance(entry, dict) else None
            if cid:
                ai_by_id[cid] = entry

    # Once HR approves the campus checkpoint, Outreach emails the AI picks,
    # so they're effectively approved even before a CampaignCollege row exists.
    checkpoint_approved = bool(checkpoint and checkpoint.status == CheckpointStatus.approved)
    ai_default_status = "approved" if checkpoint_approved else "recommended"

    rows = db.query(CampaignCollege).filter(CampaignCollege.campaign_id == campaign.id).all()
    rows_by_id = {r.college_id: r for r in rows}

    all_ids = set(ai_by_id) | set(rows_by_id)
    colleges = {}
    if all_ids:
        colleges = {c.id: c for c in db.query(College).filter(College.id.in_(list(all_ids))).all()}

    entries = []
    for cid in all_ids:
        college = colleges.get(cid)
        if college is None:
            continue
        row = rows_by_id.get(cid)
        ai = ai_by_id.get(cid)
        entry_status = row.status.value if row else ai_default_status

        if entry_status == "removed" and not include_removed:
            continue

        entries.append({
            "college": _college_to_dict(college),
            "status": entry_status,
            "selected": entry_status in {s.value for s in _ACTIVE_STATUSES},
            "recommended_by_ai": ai is not None,
            "ai_recommendation": {
                "rank": ai.get("rank"),
                "priority": ai.get("priority"),
                "expected_candidates": ai.get("expected_candidates"),
                "selection_reasoning": ai.get("selection_reasoning"),
            } if ai else None,
            "outreach": {
                "sent_at": row.outreach_sent_at.isoformat() if row and row.outreach_sent_at else None,
                "confirmed_at": row.confirmed_at.isoformat() if row and row.confirmed_at else None,
                "students_registered": row.students_registered if row else 0,
            },
        })

    entries.sort(key=lambda e: (
        (e["ai_recommendation"] or {}).get("rank") or 10_000,
        e["college"]["name"],
    ))

    summary = {s.value: 0 for s in CampaignCollegeStatus}
    for e in entries:
        summary[e["status"]] = summary.get(e["status"], 0) + 1

    return {
        "colleges": entries,
        "summary": summary,
        "campus_checkpoint_status": checkpoint.status.value if checkpoint else None,
    }


# -- GET /campaigns/{campaign_id}/colleges -------------------------------------

@campaign_colleges_router.get("/{campaign_id}/colleges")
def get_campaign_colleges(
    campaign_id: UUID,
    include_removed: bool = Query(False),
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    campaign = _get_owned_campaign(db, campaign_id, company)
    return _envelope(True, "OK", _build_campaign_colleges(db, campaign, include_removed))


# -- POST /campaigns/{campaign_id}/colleges ------------------------------------

@campaign_colleges_router.post("/{campaign_id}/colleges")
def update_campaign_colleges(
    campaign_id: UUID,
    payload: CollegeSelectionUpdate,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """HR adds/removes colleges for this campaign.

    Removal is a soft delete (status=removed) so the history and any
    outreach already sent stay on record. Colleges already contacted or
    confirmed are never silently downgraded by an add.
    """
    campaign = _get_owned_campaign(db, campaign_id, company)

    if campaign.status in (CampaignStatus.completed, CampaignStatus.cancelled):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot modify colleges for a {campaign.status.value} campaign",
        )

    add_ids = list(dict.fromkeys(payload.add))
    remove_ids = list(dict.fromkeys(payload.remove))

    if not add_ids and not remove_ids:
        raise HTTPException(status_code=400, detail="Provide at least one college in 'add' or 'remove'")
    overlap = set(add_ids) & set(remove_ids)
    if overlap:
        raise HTTPException(
            status_code=400,
            detail=f"College(s) cannot be both added and removed: {sorted(str(i) for i in overlap)}",
        )

    wanted = set(add_ids) | set(remove_ids)
    found = {c.id for c in db.query(College).filter(College.id.in_(list(wanted))).all()}
    missing = wanted - found
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"College(s) not found: {sorted(str(i) for i in missing)}",
        )

    rows = {
        r.college_id: r
        for r in db.query(CampaignCollege).filter(CampaignCollege.campaign_id == campaign_id).all()
    }

    added, removed, unchanged, warnings = [], [], [], []

    for cid in add_ids:
        row = rows.get(cid)
        if row is None:
            db.add(CampaignCollege(
                campaign_id=campaign_id,
                college_id=cid,
                status=CampaignCollegeStatus.approved,
            ))
            added.append(str(cid))
        elif row.status in _ACTIVE_STATUSES:
            unchanged.append(str(cid))
        else:
            row.status = CampaignCollegeStatus.approved
            added.append(str(cid))

    for cid in remove_ids:
        row = rows.get(cid)
        if row is None:
            # Recorded even with no prior row, so an AI-recommended college
            # HR rejects stays excluded from the campaign view.
            db.add(CampaignCollege(
                campaign_id=campaign_id,
                college_id=cid,
                status=CampaignCollegeStatus.removed,
            ))
            removed.append(str(cid))
        elif row.status == CampaignCollegeStatus.removed:
            unchanged.append(str(cid))
        else:
            if row.status in _OUTREACH_STARTED:
                warnings.append(
                    f"College {cid} was already contacted; removal does not recall emails already sent"
                )
            row.status = CampaignCollegeStatus.removed
            removed.append(str(cid))

    db.commit()
    logger.info(
        f"[Colleges] campaign={campaign_id} added={len(added)} "
        f"removed={len(removed)} unchanged={len(unchanged)}"
    )

    data = _build_campaign_colleges(db, campaign, include_removed=False)
    data["changes"] = {
        "added": added,
        "removed": removed,
        "unchanged": unchanged,
        "warnings": warnings,
    }
    return _envelope(True, f"Updated: {len(added)} added, {len(removed)} removed", data)