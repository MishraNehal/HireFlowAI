"""
Pydantic schemas for Checkpoints — the human-approval gates in the
18-stage hiring pipeline (8 of which are mandatory).
Mirrors app/models/campaign.py (Checkpoint).
"""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.campaign import CheckpointStatus

# Decisions a human can actually submit. 'pending' is the initial state and
# 'rolled_back' is set by the system during checkpoint-based rollback —
# neither should ever arrive in a request body.
_HUMAN_DECISIONS = {
    CheckpointStatus.approved,
    CheckpointStatus.rejected,
    CheckpointStatus.revision_requested,
}


class CheckpointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    stage_name: str
    stage_order: int
    status: CheckpointStatus
    state_snapshot: dict[str, Any]
    hr_notes: Optional[str] = None
    decided_by: Optional[UUID] = None
    decided_at: Optional[datetime] = None
    created_at: datetime


class CheckpointRespondRequest(BaseModel):
    """HR's decision on a pending checkpoint.
    decided_by/decided_at are set server-side, not accepted in the body."""
    decision: CheckpointStatus = Field(
        ..., description="One of: approved | rejected | revision_requested"
    )
    hr_notes: Optional[str] = Field(None, max_length=5000)

    @field_validator("decision")
    @classmethod
    def decision_must_be_a_human_action(cls, v: CheckpointStatus) -> CheckpointStatus:
        if v not in _HUMAN_DECISIONS:
            allowed = ", ".join(s.value for s in _HUMAN_DECISIONS)
            raise ValueError(f"decision must be one of [{allowed}], got '{v.value}'")
        return v