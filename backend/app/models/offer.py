import uuid
import enum
from datetime import datetime, date
from sqlalchemy import (
    Column, String, DateTime, Date, Enum as SAEnum, ForeignKey, Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class OfferStatus(str, enum.Enum):
    draft = "draft"
    approved = "approved"
    sent = "sent"
    accepted = "accepted"
    declined = "declined"
    expired = "expired"


class DocumentType(str, enum.Enum):
    aadhaar = "aadhaar"
    pan = "pan"
    marksheet = "marksheet"
    offer_signed = "offer_signed"
    bank_details = "bank_details"
    photo = "photo"
    other = "other"


class DocumentStatus(str, enum.Enum):
    pending = "pending"
    submitted = "submitted"
    verified = "verified"
    rejected = "rejected"


class Offer(Base):
    __tablename__ = "offers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False, unique=True, index=True)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False, index=True)
    offer_letter_url = Column(String(2048), nullable=True)
    stipend_offered = Column(String(100), nullable=True)
    joining_date = Column(Date, nullable=True)
    status = Column(SAEnum(OfferStatus, name="offerstatus"), default=OfferStatus.draft, nullable=False)
    sent_at = Column(DateTime, nullable=True)
    response_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    candidate = relationship("Candidate", back_populates="offer")


class OnboardingDocument(Base):
    __tablename__ = "onboarding_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False, index=True)
    doc_type = Column(SAEnum(DocumentType, name="documenttype"), nullable=False)
    file_url = Column(String(2048), nullable=True)
    status = Column(SAEnum(DocumentStatus, name="documentstatus"), default=DocumentStatus.pending, nullable=False)
    submitted_at = Column(DateTime, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    verified_by = Column(UUID(as_uuid=True), ForeignKey("company_users.id"), nullable=True)

    candidate = relationship("Candidate", back_populates="onboarding_documents")
