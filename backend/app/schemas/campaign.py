"""
Pydantic schemas for Campaigns and their workflow configuration.
Mirrors app/models/campaign.py (Campaign, CampaignWorkflowConfig).

Enums are imported directly from the SQLAlchemy models so there is a
single source of truth for valid values between the DB layer and the API.
"""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.campaign import WorkMode, CampaignStatus


class CampaignCreate(BaseModel):
    """Payload for creating a new campaign.
    company_id and created_by are derived server-side from the authenticated
    session — they are intentionally NOT accepted in the request body."""
    title: str = Field(..., min_length=1, max_length=255)
    role: str = Field(..., min_length=1, max_length=255)
    batch_year: Optional[int] = Field(None, ge=2000, le=2100)
    openings: int = Field(1, ge=1)
    skills_required: list[str] = Field(default_factory=list)
    skills_preferred: list[str] = Field(default_factory=list)
    stipend: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=255)
    work_mode: WorkMode = WorkMode.onsite


class CampaignUpdate(BaseModel):
    """Partial update — every field optional, only set fields are applied."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    role: Optional[str] = Field(None, min_length=1, max_length=255)
    batch_year: Optional[int] = Field(None, ge=2000, le=2100)
    openings: Optional[int] = Field(None, ge=1)
    skills_required: Optional[list[str]] = None
    skills_preferred: Optional[list[str]] = None
    stipend: Optional[str] = None
    location: Optional[str] = None
    work_mode: Optional[WorkMode] = None
    status: Optional[CampaignStatus] = None


class CampaignResponse(BaseModel):
    """Read model — built directly from the Campaign ORM object via
    `CampaignResponse.model_validate(campaign_orm_instance)`."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    title: str
    role: str
    batch_year: Optional[int] = None
    openings: int
    skills_required: list[str]
    skills_preferred: list[str]
    stipend: Optional[str] = None
    location: Optional[str] = None
    work_mode: WorkMode
    status: CampaignStatus
    created_by: Optional[UUID] = None
    created_at: datetime


class WorkflowConfigCreate(BaseModel):
    """Payload for setting a campaign's pipeline configuration (which of the
    18 stages run, and which of those 8 require human approval).
    campaign_id comes from the URL path, not the body."""
    rounds_selected: dict[str, Any] = Field(default_factory=dict)
    # Typed as dict[str, Any] (not dict[str, bool]) deliberately — pydantic's
    # lax bool coercion would silently turn strings like "yes"/"1" into True
    # before a validator ever ran. We enforce strict bool ourselves instead.
    approval_gates: dict[str, Any] = Field(default_factory=dict)

    @field_validator("approval_gates")
    @classmethod
    def gates_must_be_boolean(cls, v: dict[str, Any]) -> dict[str, bool]:
        for stage, enabled in v.items():
            if not isinstance(enabled, bool):
                raise ValueError(
                    f"approval_gates['{stage}'] must be true/false, got {type(enabled).__name__}"
                )
        return v


class WorkflowConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    rounds_selected: dict[str, Any]
    approval_gates: dict[str, bool]
    created_at: datetime