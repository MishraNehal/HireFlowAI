import uuid
import enum
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, DateTime, Enum as SAEnum,
    ForeignKey, Integer, Text, Float,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
from app.database import Base


class WorkMode(str, enum.Enum):
    remote = "remote"
    hybrid = "hybrid"
    onsite = "onsite"


class CampaignStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    paused = "paused"
    completed = "completed"
    cancelled = "cancelled"


class CheckpointStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    revision_requested = "revision_requested"
    rolled_back = "rolled_back"


class CollegeTier(str, enum.Enum):
    tier1 = "tier1"
    tier2 = "tier2"
    tier3 = "tier3"


class CampaignCollegeStatus(str, enum.Enum):
    recommended = "recommended"
    approved = "approved"
    contacted = "contacted"
    confirmed = "confirmed"
    declined = "declined"
    removed = "removed"


class RoundStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    completed = "completed"
    skipped = "skipped"


class EmailRecipientType(str, enum.Enum):
    college = "college"
    candidate = "candidate"


class EmailStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"
    bounced = "bounced"


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    role = Column(String(255), nullable=False)
    batch_year = Column(Integer, nullable=True)
    openings = Column(Integer, default=1, nullable=False)
    skills_required = Column(ARRAY(Text), default=list, nullable=False)
    skills_preferred = Column(ARRAY(Text), default=list, nullable=False)
    stipend = Column(String(100), nullable=True)
    location = Column(String(255), nullable=True)
    work_mode = Column(SAEnum(WorkMode, name="workmode"), default=WorkMode.onsite, nullable=False)
    status = Column(SAEnum(CampaignStatus, name="campaignstatus"), default=CampaignStatus.draft, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("company_users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    company = relationship("Company", back_populates="campaigns")
    workflow_config = relationship("CampaignWorkflowConfig", back_populates="campaign", uselist=False)
    rounds = relationship("CampaignRound", back_populates="campaign")
    checkpoints = relationship("Checkpoint", back_populates="campaign")
    campaign_colleges = relationship("CampaignCollege", back_populates="campaign")
    candidates = relationship("Candidate", back_populates="campaign")
    email_logs = relationship("EmailLog", back_populates="campaign")


class CampaignWorkflowConfig(Base):
    __tablename__ = "campaign_workflow_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False, unique=True, index=True)
    rounds_selected = Column(JSONB, default=dict, nullable=False)
    approval_gates = Column(JSONB, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    campaign = relationship("Campaign", back_populates="workflow_config")


class CampaignRound(Base):
    __tablename__ = "campaign_rounds"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False, index=True)
    round_order = Column(Integer, nullable=False)
    round_type = Column(String(50), nullable=False)
    round_name = Column(String(255), nullable=False)
    interview_mode = Column(String(50), nullable=True)
    status = Column(SAEnum(RoundStatus, name="roundstatus"), default=RoundStatus.pending, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    campaign = relationship("Campaign", back_populates="rounds")


class Checkpoint(Base):
    __tablename__ = "checkpoints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False, index=True)
    stage_name = Column(String(100), nullable=False)
    stage_order = Column(Integer, nullable=False)
    status = Column(SAEnum(CheckpointStatus, name="checkpointstatus"), default=CheckpointStatus.pending, nullable=False)
    state_snapshot = Column(JSONB, default=dict, nullable=False)
    hr_notes = Column(Text, nullable=True)
    decided_by = Column(UUID(as_uuid=True), ForeignKey("company_users.id"), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    campaign = relationship("Campaign", back_populates="checkpoints")
    approval_records = relationship("ApprovalRecord", back_populates="checkpoint")


class College(Base):
    __tablename__ = "colleges"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    tier = Column(SAEnum(CollegeTier, name="collegetier"), nullable=False, default=CollegeTier.tier2)
    placement_email = Column(String(255), nullable=True)
    tpo_name = Column(String(255), nullable=True)
    tpo_contact = Column(String(50), nullable=True)
    historical_rating = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    campaign_colleges = relationship("CampaignCollege", back_populates="college")
    candidates = relationship("Candidate", back_populates="college")


class CampaignCollege(Base):
    __tablename__ = "campaign_colleges"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False, index=True)
    college_id = Column(UUID(as_uuid=True), ForeignKey("colleges.id"), nullable=False, index=True)
    status = Column(SAEnum(CampaignCollegeStatus, name="campaigncollegestatus"), default=CampaignCollegeStatus.recommended, nullable=False)
    outreach_sent_at = Column(DateTime, nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    students_registered = Column(Integer, default=0, nullable=False)

    campaign = relationship("Campaign", back_populates="campaign_colleges")
    college = relationship("College", back_populates="campaign_colleges")


class EmailLog(Base):
    __tablename__ = "email_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=True, index=True)
    recipient_email = Column(String(255), nullable=False)
    recipient_type = Column(SAEnum(EmailRecipientType, name="emailrecipienttype"), nullable=False)
    email_type = Column(String(100), nullable=True)
    subject = Column(Text, nullable=True)
    body = Column(Text, nullable=True)
    status = Column(SAEnum(EmailStatus, name="emailstatus"), default=EmailStatus.pending, nullable=False)
    sent_at = Column(DateTime, nullable=True)

    campaign = relationship("Campaign", back_populates="email_logs")
