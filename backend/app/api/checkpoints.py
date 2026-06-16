"""
Checkpoints API — Approval gate management for campaigns.
Milestone 1: HR can view, approve, reject, or request revision on checkpoints.
"""
from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware import get_current_user, get_current_company
from app.models.company import CompanyUser, Company
from app.models.campaign import Campaign, Checkpoint, CheckpointStatus

router = APIRouter(prefix="/api/v1/checkpoints", tags=["checkpoints"])


def _envelope(success: bool, message: str, data=None, error: str = None):
    return {
        "success": success,
        "message": message,
        "data": data,
        "error": error,
        "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
    }


def _checkpoint_to_dict(cp: Checkpoint) -> dict:
    return {
        "id": str(cp.id),
        "campaign_id": str(cp.campaign_id),
        "stage_name": cp.stage_name,
        "stage_order": cp.stage_order,
        "status": cp.status.value if cp.status else None,
        "state_snapshot": cp.state_snapshot or {},
        "hr_notes": cp.hr_notes,
        "decided_by": str(cp.decided_by) if cp.decided_by else None,
        "decided_at": cp.decided_at.isoformat() if cp.decided_at else None,
        "created_at": cp.created_at.isoformat() if cp.created_at else None,
    }


# ── Schemas ───────────────────────────────────────────────────────────────────

class CheckpointDecision(BaseModel):
    hr_notes: Optional[str] = None


class RevisionRequest(BaseModel):
    hr_notes: str  # required — must explain what needs to change


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/")
def list_checkpoints(
    campaign_id: Optional[UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """List checkpoints, optionally filtered by campaign or status."""
    # Validate access: only show checkpoints for campaigns belonging to this company
    q = (
        db.query(Checkpoint)
        .join(Campaign, Checkpoint.campaign_id == Campaign.id)
        .filter(Campaign.company_id == company.id)
    )

    if campaign_id:
        q = q.filter(Checkpoint.campaign_id == campaign_id)

    if status_filter:
        try:
            st = CheckpointStatus(status_filter)
            q = q.filter(Checkpoint.status == st)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")

    checkpoints = q.order_by(Checkpoint.stage_order.asc()).all()
    return _envelope(True, "OK", {
        "checkpoints": [_checkpoint_to_dict(cp) for cp in checkpoints],
        "total": len(checkpoints),
    })


@router.get("/{checkpoint_id}")
def get_checkpoint(
    checkpoint_id: UUID,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Get a single checkpoint by ID."""
    cp = (
        db.query(Checkpoint)
        .join(Campaign, Checkpoint.campaign_id == Campaign.id)
        .filter(Checkpoint.id == checkpoint_id, Campaign.company_id == company.id)
        .first()
    )
    if not cp:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    return _envelope(True, "OK", _checkpoint_to_dict(cp))


@router.post("/{checkpoint_id}/approve")
def approve_checkpoint(
    checkpoint_id: UUID,
    payload: CheckpointDecision = CheckpointDecision(),
    current_user: CompanyUser = Depends(get_current_user),
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Approve a pending checkpoint — moves the campaign stage forward."""
    cp = (
        db.query(Checkpoint)
        .join(Campaign, Checkpoint.campaign_id == Campaign.id)
        .filter(Checkpoint.id == checkpoint_id, Campaign.company_id == company.id)
        .first()
    )
    if not cp:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    if cp.status not in (CheckpointStatus.pending, CheckpointStatus.revision_requested):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve checkpoint in '{cp.status.value}' status"
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cp.status = CheckpointStatus.approved
    cp.decided_by = current_user.id
    cp.decided_at = now
    if payload.hr_notes:
        cp.hr_notes = payload.hr_notes

    db.commit()
    db.refresh(cp)
    return _envelope(True, "Checkpoint approved", _checkpoint_to_dict(cp))


@router.post("/{checkpoint_id}/reject")
def reject_checkpoint(
    checkpoint_id: UUID,
    payload: CheckpointDecision = CheckpointDecision(),
    current_user: CompanyUser = Depends(get_current_user),
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Reject a checkpoint — halts the current campaign stage."""
    cp = (
        db.query(Checkpoint)
        .join(Campaign, Checkpoint.campaign_id == Campaign.id)
        .filter(Checkpoint.id == checkpoint_id, Campaign.company_id == company.id)
        .first()
    )
    if not cp:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    if cp.status not in (CheckpointStatus.pending, CheckpointStatus.revision_requested):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reject checkpoint in '{cp.status.value}' status"
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cp.status = CheckpointStatus.rejected
    cp.decided_by = current_user.id
    cp.decided_at = now
    if payload.hr_notes:
        cp.hr_notes = payload.hr_notes

    db.commit()
    db.refresh(cp)
    return _envelope(True, "Checkpoint rejected", _checkpoint_to_dict(cp))


@router.post("/{checkpoint_id}/request-revision")
def request_revision(
    checkpoint_id: UUID,
    payload: RevisionRequest,
    current_user: CompanyUser = Depends(get_current_user),
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Request a revision on a pending checkpoint — sends it back for rework."""
    cp = (
        db.query(Checkpoint)
        .join(Campaign, Checkpoint.campaign_id == Campaign.id)
        .filter(Checkpoint.id == checkpoint_id, Campaign.company_id == company.id)
        .first()
    )
    if not cp:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    if cp.status != CheckpointStatus.pending:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot request revision on checkpoint in '{cp.status.value}' status"
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cp.status = CheckpointStatus.revision_requested
    cp.decided_by = current_user.id
    cp.decided_at = now
    cp.hr_notes = payload.hr_notes

    db.commit()
    db.refresh(cp)
    return _envelope(True, "Revision requested", _checkpoint_to_dict(cp))


@router.post("/{checkpoint_id}/rollback")
def rollback_checkpoint(
    checkpoint_id: UUID,
    payload: CheckpointDecision = CheckpointDecision(),
    current_user: CompanyUser = Depends(get_current_user),
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Roll back an approved checkpoint."""
    cp = (
        db.query(Checkpoint)
        .join(Campaign, Checkpoint.campaign_id == Campaign.id)
        .filter(Checkpoint.id == checkpoint_id, Campaign.company_id == company.id)
        .first()
    )
    if not cp:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    if cp.status != CheckpointStatus.approved:
        raise HTTPException(
            status_code=400,
            detail=f"Can only roll back APPROVED checkpoints, not '{cp.status.value}'"
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cp.status = CheckpointStatus.rolled_back
    cp.decided_by = current_user.id
    cp.decided_at = now
    if payload.hr_notes:
        cp.hr_notes = payload.hr_notes

    db.commit()
    db.refresh(cp)
    return _envelope(True, "Checkpoint rolled back", _checkpoint_to_dict(cp))
