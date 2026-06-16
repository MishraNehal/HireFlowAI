"""
Campaigns API — Full CRUD + lifecycle management.
Milestone 1: Core campaign operations backed by real DB.
"""
from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware import get_current_user, get_current_company
from app.models.company import CompanyUser, Company
from app.models.campaign import Campaign, CampaignStatus, WorkMode, CampaignWorkflowConfig

router = APIRouter(prefix="/api/v1/campaigns", tags=["campaigns"])


def _envelope(success: bool, message: str, data=None, error: str = None):
    return {
        "success": success,
        "message": message,
        "data": data,
        "error": error,
        "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
    }


def _campaign_to_dict(c: Campaign) -> dict:
    return {
        "id": str(c.id),
        "title": c.title,
        "role": c.role,
        "batch_year": c.batch_year,
        "openings": c.openings,
        "skills_required": c.skills_required or [],
        "skills_preferred": c.skills_preferred or [],
        "stipend": c.stipend,
        "location": c.location,
        "work_mode": c.work_mode.value if c.work_mode else None,
        "status": c.status.value if c.status else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "company_id": str(c.company_id),
    }


# ── Schemas ───────────────────────────────────────────────────────────────────

class CampaignCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    role: str = Field(..., min_length=2, max_length=255)
    batch_year: Optional[int] = None
    openings: int = Field(default=1, ge=1)
    skills_required: List[str] = Field(default_factory=list)
    skills_preferred: List[str] = Field(default_factory=list)
    stipend: Optional[str] = None
    location: Optional[str] = None
    work_mode: WorkMode = WorkMode.onsite


class CampaignUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=255)
    role: Optional[str] = Field(None, min_length=2, max_length=255)
    batch_year: Optional[int] = None
    openings: Optional[int] = Field(None, ge=1)
    skills_required: Optional[List[str]] = None
    skills_preferred: Optional[List[str]] = None
    stipend: Optional[str] = None
    location: Optional[str] = None
    work_mode: Optional[WorkMode] = None


class WorkflowConfigUpdate(BaseModel):
    rounds_selected: dict = Field(default_factory=dict)
    approval_gates: dict = Field(default_factory=dict)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/")
def list_campaigns(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """List all campaigns for the authenticated company."""
    q = db.query(Campaign).filter(Campaign.company_id == company.id)
    if status_filter:
        try:
            st = CampaignStatus(status_filter)
            q = q.filter(Campaign.status == st)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")
    total = q.count()
    campaigns = q.order_by(Campaign.created_at.desc()).offset(offset).limit(limit).all()
    return _envelope(True, "OK", {
        "campaigns": [_campaign_to_dict(c) for c in campaigns],
        "total": total,
        "limit": limit,
        "offset": offset,
    })


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_campaign(
    payload: CampaignCreate,
    current_user: CompanyUser = Depends(get_current_user),
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Create a new campaign in DRAFT status."""
    campaign = Campaign(
        company_id=company.id,
        created_by=current_user.id,
        title=payload.title,
        role=payload.role,
        batch_year=payload.batch_year,
        openings=payload.openings,
        skills_required=payload.skills_required,
        skills_preferred=payload.skills_preferred,
        stipend=payload.stipend,
        location=payload.location,
        work_mode=payload.work_mode,
        status=CampaignStatus.draft,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return _envelope(True, "Campaign created", _campaign_to_dict(campaign))


@router.get("/{campaign_id}")
def get_campaign(
    campaign_id: UUID,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Get a single campaign by ID."""
    c = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.company_id == company.id,
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    data = _campaign_to_dict(c)
    # Include workflow config if exists
    if c.workflow_config:
        data["workflow_config"] = {
            "rounds_selected": c.workflow_config.rounds_selected,
            "approval_gates": c.workflow_config.approval_gates,
        }
    return _envelope(True, "OK", data)


@router.patch("/{campaign_id}")
def update_campaign(
    campaign_id: UUID,
    payload: CampaignUpdate,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Update a campaign (only allowed in DRAFT or PAUSED status)."""
    c = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.company_id == company.id,
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if c.status not in (CampaignStatus.draft, CampaignStatus.paused):
        raise HTTPException(status_code=400, detail="Can only edit campaigns in DRAFT or PAUSED status")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(c, field, value)
    db.commit()
    db.refresh(c)
    return _envelope(True, "Campaign updated", _campaign_to_dict(c))


@router.delete("/{campaign_id}", status_code=status.HTTP_200_OK)
def delete_campaign(
    campaign_id: UUID,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Delete a campaign (only DRAFT campaigns can be deleted)."""
    c = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.company_id == company.id,
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if c.status != CampaignStatus.draft:
        raise HTTPException(status_code=400, detail="Only DRAFT campaigns can be deleted. Cancel it first.")
    db.delete(c)
    db.commit()
    return _envelope(True, "Campaign deleted")


@router.post("/{campaign_id}/launch")
def launch_campaign(
    campaign_id: UUID,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Launch a draft campaign → sets status to ACTIVE."""
    c = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.company_id == company.id,
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if c.status != CampaignStatus.draft:
        raise HTTPException(status_code=400, detail=f"Cannot launch campaign in '{c.status.value}' status")
    c.status = CampaignStatus.active
    db.commit()
    db.refresh(c)
    return _envelope(True, "Campaign launched successfully", _campaign_to_dict(c))


@router.post("/{campaign_id}/pause")
def pause_campaign(
    campaign_id: UUID,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Pause an active campaign."""
    c = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.company_id == company.id,
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if c.status != CampaignStatus.active:
        raise HTTPException(status_code=400, detail="Only ACTIVE campaigns can be paused")
    c.status = CampaignStatus.paused
    db.commit()
    db.refresh(c)
    return _envelope(True, "Campaign paused", _campaign_to_dict(c))


@router.post("/{campaign_id}/resume")
def resume_campaign(
    campaign_id: UUID,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Resume a paused campaign."""
    c = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.company_id == company.id,
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if c.status != CampaignStatus.paused:
        raise HTTPException(status_code=400, detail="Only PAUSED campaigns can be resumed")
    c.status = CampaignStatus.active
    db.commit()
    db.refresh(c)
    return _envelope(True, "Campaign resumed", _campaign_to_dict(c))


@router.post("/{campaign_id}/cancel")
def cancel_campaign(
    campaign_id: UUID,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Cancel a campaign."""
    c = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.company_id == company.id,
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if c.status == CampaignStatus.completed:
        raise HTTPException(status_code=400, detail="Cannot cancel a completed campaign")
    c.status = CampaignStatus.cancelled
    db.commit()
    db.refresh(c)
    return _envelope(True, "Campaign cancelled", _campaign_to_dict(c))


@router.put("/{campaign_id}/workflow-config")
def upsert_workflow_config(
    campaign_id: UUID,
    payload: WorkflowConfigUpdate,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Save the AI workflow configuration for a campaign."""
    c = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.company_id == company.id,
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")

    config = db.query(CampaignWorkflowConfig).filter(
        CampaignWorkflowConfig.campaign_id == campaign_id
    ).first()

    if config:
        config.rounds_selected = payload.rounds_selected
        config.approval_gates = payload.approval_gates
    else:
        config = CampaignWorkflowConfig(
            campaign_id=campaign_id,
            rounds_selected=payload.rounds_selected,
            approval_gates=payload.approval_gates,
        )
        db.add(config)

    db.commit()
    db.refresh(config)
    return _envelope(True, "Workflow config saved", {
        "campaign_id": str(campaign_id),
        "rounds_selected": config.rounds_selected,
        "approval_gates": config.approval_gates,
    })
