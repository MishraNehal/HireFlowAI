"""
CheckpointManager — pauses the LangGraph pipeline at human-approval gates,
saves full HireFlowState to the checkpoints table, and resumes / rolls back
based on HR's decision.

Flow:
  Agent completes → reach_checkpoint() called
    → serialises state to JSONB
    → saves Checkpoint row (status=pending)
    → sends WebSocket event: checkpoint.pending
    → raises NodeInterrupt  ← LangGraph pauses here

  HR responds via POST /checkpoints/{id}/respond
    → approved           : resume_after_checkpoint() → continues pipeline
    → revision_requested : reenter_current_node()   → re-runs same agent
    → rejected           : handled by rollback.py   → restores earlier state
"""

import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from langgraph.errors import NodeInterrupt
from sqlalchemy.orm import Session

from app.models.campaign import Checkpoint, CheckpointStatus, Campaign, CampaignStatus
from app.agents.state import HireFlowState

logger = logging.getLogger(__name__)

# Ordered list of all checkpoint stage names — used to calculate stage_order
CHECKPOINT_STAGES = [
    "checkpoint_jd",           # CP1  — JD Approval
    "checkpoint_campus",       # CP2  — Campus Selection
    "checkpoint_shortlist",    # CP3  — Shortlist Approval
    "checkpoint_assessment",   # CP4  — Assessment Results
    "checkpoint_schedule",     # CP5  — Interview Schedule
    "checkpoint_interview",    # CP6  — Interview Results
    "checkpoint_final",        # CP7  — Final Selection
    "checkpoint_offer",        # CP8  — Offer Approval
]


def _stage_order(stage_name: str) -> int:
    """Return 1-based position of a checkpoint stage; 99 if unknown."""
    try:
        return CHECKPOINT_STAGES.index(stage_name) + 1
    except ValueError:
        return 99


def _serialise_state(state: HireFlowState) -> dict:
    """
    Convert HireFlowState to a plain dict safe for JSONB storage.
    UUIDs and datetimes are stringified.
    """
    def _convert(obj: Any) -> Any:
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {k: _convert(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_convert(i) for i in obj]
        return obj

    return _convert(dict(state))


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def reach_checkpoint(
    state: HireFlowState,
    stage_name: str,
    db: Session,
    websocket_manager=None,   # injected at runtime to avoid circular imports
) -> HireFlowState:
    """
    Called by a checkpoint node in the LangGraph graph.

    1. Saves full state snapshot to checkpoints table (status=pending).
    2. Fires WebSocket event so the HR dashboard updates instantly.
    3. Raises NodeInterrupt → LangGraph pauses and persists thread.

    The graph will not advance until resume_after_checkpoint() or
    reenter_current_node() is called from the API layer.
    """
    logger.info(f"[checkpoint] Reached {stage_name} for campaign {state['campaign_id']}")

    snapshot = _serialise_state(state)

    checkpoint = Checkpoint(
        campaign_id=state["campaign_id"],
        stage_name=stage_name,
        stage_order=_stage_order(stage_name),
        status=CheckpointStatus.pending,
        state_snapshot=snapshot,
    )
    db.add(checkpoint)
    db.commit()
    db.refresh(checkpoint)

    # Notify HR dashboard via WebSocket (non-blocking — log and continue if fails)
    if websocket_manager:
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                websocket_manager.send_event(
                    company_id=state["company_id"],
                    campaign_id=state["campaign_id"],
                    event="checkpoint.pending",
                    payload={
                        "checkpoint_id": str(checkpoint.id),
                        "stage_name": stage_name,
                        "stage_order": checkpoint.stage_order,
                        "campaign_id": state["campaign_id"],
                    },
                )
            )
        except Exception as ws_err:
            logger.warning(f"[checkpoint] WebSocket notify failed (non-fatal): {ws_err}")

    # Update state before pausing
    updated_state: HireFlowState = {
        **state,
        "current_stage": stage_name,
        "checkpoint_status": "pending",
    }

    # This raises NodeInterrupt — LangGraph catches it and persists the thread.
    # Execution stops here until the graph is resumed externally.
    raise NodeInterrupt(
        f"Checkpoint {stage_name} reached — awaiting HR approval "
        f"(checkpoint_id={checkpoint.id})"
    )


def resume_after_checkpoint(
    checkpoint_id: str,
    decision: str,
    hr_notes: str | None,
    decided_by_user_id: str | None,
    db: Session,
) -> dict:
    """
    Called from POST /checkpoints/{id}/respond.

    Updates the checkpoint row and returns the restored state so the
    pipeline task can resume the LangGraph thread.

    Returns:
        {
          "state_snapshot": dict,   # full HireFlowState to inject
          "resume_node":    str,    # node to resume from
          "campaign_id":    str,
        }
    """
    checkpoint = db.query(Checkpoint).filter(Checkpoint.id == checkpoint_id).first()
    if not checkpoint:
        raise ValueError(f"Checkpoint {checkpoint_id} not found")

    if checkpoint.status != CheckpointStatus.pending:
        raise ValueError(
            f"Checkpoint {checkpoint_id} is already {checkpoint.status.value} — cannot respond again"
        )

    # Persist HR decision
    checkpoint.status = CheckpointStatus(decision)
    checkpoint.hr_notes = hr_notes
    checkpoint.decided_by = decided_by_user_id
    checkpoint.decided_at = datetime.utcnow()
    db.commit()
    db.refresh(checkpoint)

    restored_state = dict(checkpoint.state_snapshot)
    restored_state["checkpoint_status"] = decision
    restored_state["hr_feedback"] = hr_notes

    return {
        "state_snapshot": restored_state,
        "resume_node": checkpoint.stage_name,
        "campaign_id": str(checkpoint.campaign_id),
        "checkpoint": checkpoint,
    }


def reenter_current_node(
    checkpoint_id: str,
    hr_notes: str | None,
    decided_by_user_id: str | None,
    db: Session,
) -> dict:
    """
    Called when decision == 'revision_requested'.
    Same as resume but sets checkpoint_status = revision_requested
    so the agent node re-runs with hr_feedback injected.
    """
    return resume_after_checkpoint(
        checkpoint_id=checkpoint_id,
        decision="revision_requested",
        hr_notes=hr_notes,
        decided_by_user_id=decided_by_user_id,
        db=db,
    )


def get_pending_checkpoint(campaign_id: str, db: Session) -> Checkpoint | None:
    """Return the current pending checkpoint for a campaign, if any."""
    return (
        db.query(Checkpoint)
        .filter(
            Checkpoint.campaign_id == campaign_id,
            Checkpoint.status == CheckpointStatus.pending,
        )
        .order_by(Checkpoint.stage_order.desc())
        .first()
    )


def get_all_checkpoints(campaign_id: str, db: Session) -> list[Checkpoint]:
    """Return all checkpoints for a campaign ordered by stage."""
    return (
        db.query(Checkpoint)
        .filter(Checkpoint.campaign_id == campaign_id)
        .order_by(Checkpoint.stage_order.asc())
        .all()
    )
