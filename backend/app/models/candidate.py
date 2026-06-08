import uuid
import enum
from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, Enum as SAEnum, ForeignKey,
    Integer, Text, Float, Boolean,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from app.database import Base


class CandidateStatus(str, enum.Enum):
    registered = "registered"
    screened = "screened"
    shortlisted = "shortlisted"
    assessment_pending = "assessment_pending"
    assessment_done = "assessment_done"
    interview_scheduled = "interview_scheduled"
    interview_done = "interview_done"
    selected = "selected"
    rejected = "rejected"
    on_hold = "on_hold"
    offer_sent = "offer_sent"
    offer_accepted = "offer_accepted"
    offer_declined = "offer_declined"
    onboarding = "onboarding"


class ParseStatus(str, enum.Enum):
    pending = "pending"
    parsed = "parsed"
    failed = "failed"


class Recommendation(str, enum.Enum):
    strong_match = "strong_match"
    moderate_match = "moderate_match"
    weak_match = "weak_match"


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False, index=True)
    college_id = Column(UUID(as_uuid=True), ForeignKey("colleges.id"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, index=True)
    phone = Column(String(20), nullable=True)
    batch_year = Column(Integer, nullable=True)
    current_cgpa = Column(Float, nullable=True)
    status = Column(SAEnum(CandidateStatus, name="candidatestatus"), default=CandidateStatus.registered, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    campaign = relationship("Campaign", back_populates="candidates")
    college = relationship("College", back_populates="candidates")
    resume = relationship("Resume", back_populates="candidate", uselist=False)
    profile = relationship("CandidateProfile", back_populates="candidate", uselist=False)
    score = relationship("Score", back_populates="candidate", uselist=False)
    assessment_results = relationship("AssessmentResult", back_populates="candidate")
    interview_sessions = relationship("InterviewSession", back_populates="candidate")
    offer = relationship("Offer", back_populates="candidate", uselist=False)
    onboarding_documents = relationship("OnboardingDocument", back_populates="candidate")


class Resume(Base):
    __tablename__ = "resumes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False, unique=True, index=True)
    file_url = Column(String(2048), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_size_kb = Column(Integer, nullable=True)
    parse_status = Column(SAEnum(ParseStatus, name="parsestatus"), default=ParseStatus.pending, nullable=False)
    raw_text = Column(Text, nullable=True)
    parsed_at = Column(DateTime, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    candidate = relationship("Candidate", back_populates="resume")


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False, unique=True, index=True)
    skills = Column(ARRAY(Text), default=list, nullable=False)
    projects = Column(JSONB, default=list, nullable=False)
    experience = Column(JSONB, default=list, nullable=False)
    education = Column(JSONB, default=list, nullable=False)
    certifications = Column(ARRAY(Text), default=list, nullable=False)
    summary = Column(Text, nullable=True)
    embedding = Column(Vector(384), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    candidate = relationship("Candidate", back_populates="profile")


class Score(Base):
    __tablename__ = "scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False, unique=True, index=True)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False, index=True)
    skills_score = Column(Float, default=0.0, nullable=False)
    project_score = Column(Float, default=0.0, nullable=False)
    experience_score = Column(Float, default=0.0, nullable=False)
    education_score = Column(Float, default=0.0, nullable=False)
    total_score = Column(Float, default=0.0, nullable=False)
    strengths = Column(ARRAY(Text), default=list, nullable=False)
    gaps = Column(ARRAY(Text), default=list, nullable=False)
    recommendation = Column(SAEnum(Recommendation, name="recommendation"), nullable=True)
    is_overridden = Column(Boolean, default=False, nullable=False)
    override_by = Column(UUID(as_uuid=True), ForeignKey("company_users.id"), nullable=True)
    override_notes = Column(Text, nullable=True)
    scored_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    candidate = relationship("Candidate", back_populates="score")


class AssessmentResult(Base):
    __tablename__ = "assessment_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False, index=True)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False, index=True)
    round_id = Column(UUID(as_uuid=True), ForeignKey("campaign_rounds.id"), nullable=True, index=True)
    mcq_score = Column(Float, nullable=True)
    coding_score = Column(Float, nullable=True)
    written_score = Column(Float, nullable=True)
    total_score = Column(Float, nullable=True)
    time_taken_mins = Column(Integer, nullable=True)
    submission_at = Column(DateTime, nullable=True)
    auto_evaluated = Column(Boolean, default=True, nullable=False)
    evaluation_notes = Column(Text, nullable=True)

    candidate = relationship("Candidate", back_populates="assessment_results")
