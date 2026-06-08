import uuid
import enum
from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, Enum as SAEnum, ForeignKey,
    Integer, Text, Float, Boolean,
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from app.database import Base


class InterviewMode(str, enum.Enum):
    ai_only = "ai_only"
    human_only = "human_only"
    ai_and_human = "ai_and_human"


class InterviewStatus(str, enum.Enum):
    scheduled = "scheduled"
    started = "started"
    completed = "completed"
    no_show = "no_show"
    cancelled = "cancelled"


class EvaluatedBy(str, enum.Enum):
    ai = "ai"
    human = "human"
    both = "both"


class InterviewRecommendation(str, enum.Enum):
    hire = "hire"
    hold = "hold"
    reject = "reject"


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False, index=True)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False, index=True)
    round_id = Column(UUID(as_uuid=True), ForeignKey("campaign_rounds.id"), nullable=True, index=True)
    interview_mode = Column(SAEnum(InterviewMode, name="interviewmode"), default=InterviewMode.ai_only, nullable=False)
    scheduled_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    duration_mins = Column(Integer, nullable=True)
    daily_room_url = Column(String(2048), nullable=True)
    recording_url = Column(String(2048), nullable=True)
    transcript = Column(Text, nullable=True)
    status = Column(SAEnum(InterviewStatus, name="interviewstatus"), default=InterviewStatus.scheduled, nullable=False)

    candidate = relationship("Candidate", back_populates="interview_sessions")
    evaluation = relationship("InterviewEvaluation", back_populates="session", uselist=False)
    emotion_snapshots = relationship("EmotionSnapshot", back_populates="session")


class InterviewEvaluation(Base):
    __tablename__ = "interview_evaluations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("interview_sessions.id"), nullable=False, unique=True, index=True)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False, index=True)
    technical_score = Column(Float, nullable=True)
    communication_score = Column(Float, nullable=True)
    problem_solving = Column(Float, nullable=True)
    confidence_score = Column(Float, nullable=True)
    behavioral_score = Column(Float, nullable=True)
    overall_score = Column(Float, nullable=True)
    strengths = Column(ARRAY(Text), default=list, nullable=False)
    concerns = Column(ARRAY(Text), default=list, nullable=False)
    recommendation = Column(SAEnum(InterviewRecommendation, name="interviewrecommendation"), nullable=True)
    evaluated_by = Column(SAEnum(EvaluatedBy, name="evaluatedby"), default=EvaluatedBy.ai, nullable=False)
    ai_reasoning = Column(Text, nullable=True)
    hr_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("InterviewSession", back_populates="evaluation")


class EmotionSnapshot(Base):
    __tablename__ = "emotion_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("interview_sessions.id"), nullable=False, index=True)
    timestamp_ms = Column(Integer, nullable=False)
    happy = Column(Float, nullable=True)
    neutral = Column(Float, nullable=True)
    surprised = Column(Float, nullable=True)
    sad = Column(Float, nullable=True)
    angry = Column(Float, nullable=True)
    fearful = Column(Float, nullable=True)
    disgusted = Column(Float, nullable=True)
    attention = Column(Float, nullable=True)
    valence = Column(Float, nullable=True)
    arousal = Column(Float, nullable=True)
    eye_contact = Column(Boolean, nullable=True)
    face_present = Column(Boolean, nullable=True)
    multiple_faces = Column(Boolean, nullable=True)

    session = relationship("InterviewSession", back_populates="emotion_snapshots")
