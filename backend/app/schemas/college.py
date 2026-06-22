"""
Pydantic schemas for Colleges (the campus/TPO partner directory).
Mirrors app/models/campaign.py (College).
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.campaign import CollegeTier


class CollegeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    tier: CollegeTier = CollegeTier.tier2
    placement_email: Optional[EmailStr] = None
    tpo_name: Optional[str] = Field(None, max_length=255)
    tpo_contact: Optional[str] = Field(None, max_length=50)
    historical_rating: Optional[float] = Field(None, ge=0, le=5)


class CollegeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    city: Optional[str] = None
    state: Optional[str] = None
    tier: Optional[CollegeTier] = None
    placement_email: Optional[EmailStr] = None
    tpo_name: Optional[str] = None
    tpo_contact: Optional[str] = None
    historical_rating: Optional[float] = Field(None, ge=0, le=5)


class CollegeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    city: Optional[str] = None
    state: Optional[str] = None
    tier: CollegeTier
    placement_email: Optional[str] = None
    tpo_name: Optional[str] = None
    tpo_contact: Optional[str] = None
    historical_rating: Optional[float] = None
    created_at: datetime