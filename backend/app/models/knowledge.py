import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Enum as SAEnum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from app.database import Base


class KnowledgeDocType(str, enum.Enum):
    past_jd = "past_jd"
    interview_question = "interview_question"
    rubric = "rubric"
    model_answer = "model_answer"
    hiring_policy = "hiring_policy"
    salary_data = "salary_data"
    college_performance = "college_performance"


class KnowledgeSource(str, enum.Enum):
    synthetic = "synthetic"
    real = "real"


class ApprovalDecision(str, enum.Enum):
    approved = "approved"
    rejected = "rejected"
    revision_requested = "revision_requested"


class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    doc_type = Column(SAEnum(KnowledgeDocType, name="knowledgedoctype"), nullable=False)
    role_tag = Column(String(255), nullable=True, index=True)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(384), nullable=True)
    source = Column(SAEnum(KnowledgeSource, name="knowledgesource"), default=KnowledgeSource.synthetic, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    company = relationship("Company", back_populates="knowledge_base")


class ApprovalRecord(Base):
    __tablename__ = "approval_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    checkpoint_id = Column(UUID(as_uuid=True), ForeignKey("checkpoints.id"), nullable=False, index=True)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False, index=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    stage = Column(String(100), nullable=False)
    decision = Column(SAEnum(ApprovalDecision, name="approvaldecision"), nullable=False)
    previous_checkpoint_id = Column(UUID(as_uuid=True), nullable=True)
    hr_notes = Column(Text, nullable=True)
    decided_by = Column(UUID(as_uuid=True), ForeignKey("company_users.id"), nullable=True)
    decided_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    checkpoint = relationship("Checkpoint", back_populates="approval_records")
