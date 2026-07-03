"""
Checkpoints API — HR approval gate management with real pipeline integration.

POST /{id}/respond — single unified endpoint for all decisions:
  - approved           → resumes LangGraph pipeline via Celery
  - rejected           → executes rollback via Celery
  - revision_requested → re-runs agent with hr_feedback via Celery
"""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
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


def _checkpoint_to_dict(cp: Checkpoint, include_stage_data: bool = False) -> dict:
    data = {
        "id": str(cp.id),
        "campaign_id": str(cp.campaign_id),
        "stage_name": cp.stage_name,
        "stage_order": cp.stage_order,
        "status": cp.status.value if cp.status else None,
        "hr_notes": cp.hr_notes,
        "decided_by": str(cp.decided_by) if cp.decided_by else None,
        "decided_at": cp.decided_at.isoformat() if cp.decided_at else None,
        "created_at": cp.created_at.isoformat() if cp.created_at else None,
    }

    # Include stage data for pending checkpoint so HR can review
    if include_stage_data and cp.state_snapshot:
        snapshot = cp.state_snapshot
        stage = cp.stage_name

        if stage == "checkpoint_jd":
            data["stage_data"] = {
                "type": "job_description",
                "content": snapshot.get("job_description", {}),
            }
        elif stage == "checkpoint_campus":
            data["stage_data"] = {
                "type": "selected_colleges",
                "content": snapshot.get("selected_colleges", []),
            }
        elif stage == "checkpoint_shortlist":
            data["stage_data"] = {
                "type": "shortlisted_candidates",
                "content": snapshot.get("shortlisted", []),
            }
        elif stage == "checkpoint_assessment":
            data["stage_data"] = {
                "type": "assessment_results",
                "content": snapshot.get("assessment_results", []),
            }
        elif stage == "checkpoint_schedule":
            data["stage_data"] = {
                "type": "interview_schedule",
                "content": snapshot.get("interview_sessions", []),
            }
        elif stage == "checkpoint_interview":
            data["stage_data"] = {
                "type": "interview_results",
                "content": snapshot.get("interview_sessions", []),
            }
        elif stage == "checkpoint_final":
            data["stage_data"] = {
                "type": "final_selected",
                "content": snapshot.get("final_selected", []),
            }
        elif stage == "checkpoint_offer":
            data["stage_data"] = {
                "type": "offers",
                "content": snapshot.get("offers", []),
            }
        else:
            data["stage_data"] = {"type": "unknown", "content": {}}

    return data


# ── Schemas ───────────────────────────────────────────────────────────────────

class CheckpointRespond(BaseModel):
    decision: str = Field(..., pattern="^(approved|rejected|revision_requested)$")
    notes: Optional[str] = None
    modifications: Optional[dict] = None   # HR can pass modified data (e.g. edited JD)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/")
def list_checkpoints(
    campaign_id: Optional[UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """List checkpoints for a campaign, optionally filtered by status."""
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

    # Include stage_data only for pending checkpoints
    return _envelope(True, "OK", {
        "checkpoints": [
            _checkpoint_to_dict(cp, include_stage_data=(cp.status == CheckpointStatus.pending))
            for cp in checkpoints
        ],
        "total": len(checkpoints),
    })


@router.get("/{checkpoint_id}")
def get_checkpoint(
    checkpoint_id: UUID,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """
    Get checkpoint detail with full stage data for HR review.
    Returns the JD / college list / shortlist etc based on stage.
    """
    cp = (
        db.query(Checkpoint)
        .join(Campaign, Checkpoint.campaign_id == Campaign.id)
        .filter(Checkpoint.id == checkpoint_id, Campaign.company_id == company.id)
        .first()
    )
    if not cp:
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    return _envelope(True, "OK", _checkpoint_to_dict(cp, include_stage_data=True))


@router.post("/{checkpoint_id}/respond")
def respond_to_checkpoint(
    checkpoint_id: UUID,
    payload: CheckpointRespond,
    current_user: CompanyUser = Depends(get_current_user),
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """
    Unified HR decision endpoint — approve / reject / revision_requested.

    - approved           → queues Celery resume_pipeline task
    - rejected           → queues Celery resume_pipeline task (with rollback)
    - revision_requested → queues Celery resume_pipeline task (re-run agent)

    Returns immediately — pipeline resumes asynchronously.
    WebSocket events will stream progress to HR dashboard.
    """
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
            detail=f"Checkpoint is already '{cp.status.value}' — cannot respond again",
        )

    # Validate notes required for rejection/revision
    if payload.decision in ("rejected", "revision_requested") and not payload.notes:
        raise HTTPException(
            status_code=400,
            detail=f"'notes' is required when decision is '{payload.decision}'",
        )

    # Get campaign for company_id
    campaign = db.query(Campaign).filter(Campaign.id == cp.campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Queue Celery task — pipeline resumes asynchronously
    from app.tasks.pipeline_tasks import resume_pipeline
    resume_pipeline.delay(
        campaign_id=str(cp.campaign_id),
        company_id=str(campaign.company_id),
        checkpoint_id=str(checkpoint_id),
        decision=payload.decision,
        hr_notes=payload.notes or "",
        decided_by=str(current_user.id),
    )

    # Immediately update checkpoint status so UI reflects decision
    cp.status = CheckpointStatus(payload.decision)
    cp.hr_notes = payload.notes
    cp.decided_by = current_user.id
    cp.decided_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(cp)

    messages = {
        "approved": "Checkpoint approved — pipeline resuming",
        "rejected": "Checkpoint rejected — rollback executing",
        "revision_requested": "Revision requested — re-running agent with your feedback",
    }

    return _envelope(
        True,
        messages[payload.decision],
        {
            **_checkpoint_to_dict(cp),
            "pipeline_status": "resuming",
            "message": "Connect to WebSocket for real-time pipeline updates",
        },
    )


@router.get("/campaigns/{campaign_id}/checkpoints")
def get_campaign_checkpoints(
    campaign_id: UUID,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """
    Get all checkpoints for a specific campaign.
    Convenience endpoint — same as GET /checkpoints?campaign_id=...
    """
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.company_id == company.id,
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    checkpoints = (
        db.query(Checkpoint)
        .filter(Checkpoint.campaign_id == campaign_id)
        .order_by(Checkpoint.stage_order.asc())
        .all()
    )

    # Find current pending checkpoint
    pending = next((cp for cp in checkpoints if cp.status == CheckpointStatus.pending), None)

    return _envelope(True, "OK", {
        "campaign_id": str(campaign_id),
        "checkpoints": [
            _checkpoint_to_dict(cp, include_stage_data=(cp.status == CheckpointStatus.pending))
            for cp in checkpoints
        ],
        "total": len(checkpoints),
        "current_pending": _checkpoint_to_dict(pending, include_stage_data=True) if pending else None,
    })