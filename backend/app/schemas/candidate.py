"""
Pydantic schemas for Candidates and their Scores.
Mirrors app/models/candidate.py (Candidate, Score).
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.candidate import CandidateStatus, Recommendation


class CandidateCreate(BaseModel):
    """Payload for registering a candidate against a campaign.
    company_id is derived server-side from the authenticated company."""
    campaign_id: UUID
    college_id: Optional[UUID] = None
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=20)
    batch_year: Optional[int] = Field(None, ge=2000, le=2100)
    current_cgpa: Optional[float] = Field(None, ge=0, le=10)


class CandidateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    current_cgpa: Optional[float] = Field(None, ge=0, le=10)
    status: Optional[CandidateStatus] = None


class CandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    campaign_id: UUID
    college_id: Optional[UUID] = None
    name: str
    email: EmailStr
    phone: Optional[str] = None
    batch_year: Optional[int] = None
    current_cgpa: Optional[float] = None
    status: CandidateStatus
    created_at: datetime


class ScoreResponse(BaseModel):
    """Read model for the auto-generated (and possibly HR-overridden) score
    attached to a candidate."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    campaign_id: UUID
    skills_score: float
    project_score: float
    experience_score: float
    education_score: float
    total_score: float
    strengths: list[str]
    gaps: list[str]
    recommendation: Optional[Recommendation] = None
    is_overridden: bool
    override_by: Optional[UUID] = None
    override_notes: Optional[str] = None
    scored_at: datetime


class ScoreOverrideRequest(BaseModel):
    """HR manually overriding an auto-generated score.
    override_by is derived server-side from the authenticated session."""
    total_score: float = Field(..., ge=0, le=100)
    override_notes: str = Field(..., min_length=1, max_length=5000)