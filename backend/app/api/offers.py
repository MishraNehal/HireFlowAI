"""
Offers API — Generate, send, and track job/internship offers.
Milestone 1: Core offer lifecycle (draft → approve → send → accepted/declined).
"""
from datetime import datetime, timezone, date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware import get_current_user, get_current_company
from app.models.company import CompanyUser, Company
from app.models.campaign import Campaign
from app.models.candidate import Candidate
from app.models.offer import Offer, OfferStatus, OnboardingDocument, DocumentStatus

router = APIRouter(prefix="/api/v1/offers", tags=["offers"])


def _envelope(success: bool, message: str, data=None, error: str = None):
    return {
        "success": success,
        "message": message,
        "data": data,
        "error": error,
        "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
    }


def _offer_to_dict(o: Offer) -> dict:
    return {
        "id": str(o.id),
        "candidate_id": str(o.candidate_id),
        "campaign_id": str(o.campaign_id),
        "offer_letter_url": o.offer_letter_url,
        "stipend_offered": o.stipend_offered,
        "joining_date": o.joining_date.isoformat() if o.joining_date else None,
        "status": o.status.value if o.status else None,
        "sent_at": o.sent_at.isoformat() if o.sent_at else None,
        "response_at": o.response_at.isoformat() if o.response_at else None,
        "expires_at": o.expires_at.isoformat() if o.expires_at else None,
    }


def _doc_to_dict(d: OnboardingDocument) -> dict:
    return {
        "id": str(d.id),
        "candidate_id": str(d.candidate_id),
        "doc_type": d.doc_type.value if d.doc_type else None,
        "file_url": d.file_url,
        "status": d.status.value if d.status else None,
        "submitted_at": d.submitted_at.isoformat() if d.submitted_at else None,
        "verified_at": d.verified_at.isoformat() if d.verified_at else None,
    }


# ── Schemas ───────────────────────────────────────────────────────────────────

class OfferCreate(BaseModel):
    candidate_id: UUID
    campaign_id: UUID
    offer_letter_url: Optional[str] = None
    stipend_offered: Optional[str] = None
    joining_date: Optional[date] = None
    expires_at: Optional[datetime] = None


class OfferUpdate(BaseModel):
    offer_letter_url: Optional[str] = None
    stipend_offered: Optional[str] = None
    joining_date: Optional[date] = None
    expires_at: Optional[datetime] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/")
def list_offers(
    campaign_id: Optional[UUID] = Query(None),
    candidate_id: Optional[UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """List offers for the authenticated company."""
    q = (
        db.query(Offer)
        .join(Campaign, Offer.campaign_id == Campaign.id)
        .filter(Campaign.company_id == company.id)
    )
    if campaign_id:
        q = q.filter(Offer.campaign_id == campaign_id)
    if candidate_id:
        q = q.filter(Offer.candidate_id == candidate_id)
    if status_filter:
        try:
            st = OfferStatus(status_filter)
            q = q.filter(Offer.status == st)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")

    total = q.count()
    offers = q.offset(offset).limit(limit).all()
    return _envelope(True, "OK", {
        "offers": [_offer_to_dict(o) for o in offers],
        "total": total,
        "limit": limit,
        "offset": offset,
    })


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_offer(
    payload: OfferCreate,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Create a draft offer for a candidate."""
    campaign = db.query(Campaign).filter(
        Campaign.id == payload.campaign_id,
        Campaign.company_id == company.id,
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    candidate = db.query(Candidate).filter(
        Candidate.id == payload.candidate_id,
        Candidate.campaign_id == payload.campaign_id,
    ).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found in this campaign")

    # One offer per candidate
    existing = db.query(Offer).filter(Offer.candidate_id == payload.candidate_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="An offer already exists for this candidate")

    offer = Offer(
        candidate_id=payload.candidate_id,
        campaign_id=payload.campaign_id,
        offer_letter_url=payload.offer_letter_url,
        stipend_offered=payload.stipend_offered,
        joining_date=payload.joining_date,
        expires_at=payload.expires_at,
        status=OfferStatus.draft,
    )
    db.add(offer)
    db.commit()
    db.refresh(offer)
    return _envelope(True, "Offer created", _offer_to_dict(offer))


@router.get("/{offer_id}")
def get_offer(
    offer_id: UUID,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Get a single offer by ID."""
    o = (
        db.query(Offer)
        .join(Campaign, Offer.campaign_id == Campaign.id)
        .filter(Offer.id == offer_id, Campaign.company_id == company.id)
        .first()
    )
    if not o:
        raise HTTPException(status_code=404, detail="Offer not found")

    data = _offer_to_dict(o)
    # Include onboarding documents
    docs = db.query(OnboardingDocument).filter(
        OnboardingDocument.candidate_id == o.candidate_id
    ).all()
    data["onboarding_documents"] = [_doc_to_dict(d) for d in docs]
    return _envelope(True, "OK", data)


@router.patch("/{offer_id}")
def update_offer(
    offer_id: UUID,
    payload: OfferUpdate,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Update a draft offer."""
    o = (
        db.query(Offer)
        .join(Campaign, Offer.campaign_id == Campaign.id)
        .filter(Offer.id == offer_id, Campaign.company_id == company.id)
        .first()
    )
    if not o:
        raise HTTPException(status_code=404, detail="Offer not found")
    if o.status not in (OfferStatus.draft, OfferStatus.approved):
        raise HTTPException(status_code=400, detail=f"Cannot edit offer in '{o.status.value}' status")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(o, field, value)
    db.commit()
    db.refresh(o)
    return _envelope(True, "Offer updated", _offer_to_dict(o))


@router.post("/{offer_id}/approve")
def approve_offer(
    offer_id: UUID,
    current_user: CompanyUser = Depends(get_current_user),
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Approve a draft offer — allows it to be sent."""
    o = (
        db.query(Offer)
        .join(Campaign, Offer.campaign_id == Campaign.id)
        .filter(Offer.id == offer_id, Campaign.company_id == company.id)
        .first()
    )
    if not o:
        raise HTTPException(status_code=404, detail="Offer not found")
    if o.status != OfferStatus.draft:
        raise HTTPException(status_code=400, detail=f"Can only approve DRAFT offers, not '{o.status.value}'")

    o.status = OfferStatus.approved
    db.commit()
    db.refresh(o)
    return _envelope(True, "Offer approved", _offer_to_dict(o))


@router.post("/{offer_id}/send")
def send_offer(
    offer_id: UUID,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Send an approved offer to the candidate."""
    o = (
        db.query(Offer)
        .join(Campaign, Offer.campaign_id == Campaign.id)
        .filter(Offer.id == offer_id, Campaign.company_id == company.id)
        .first()
    )
    if not o:
        raise HTTPException(status_code=404, detail="Offer not found")
    if o.status != OfferStatus.approved:
        raise HTTPException(status_code=400, detail=f"Can only send APPROVED offers, not '{o.status.value}'")

    o.status = OfferStatus.sent
    o.sent_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(o)
    return _envelope(True, "Offer sent to candidate", _offer_to_dict(o))


@router.post("/{offer_id}/accept")
def accept_offer(
    offer_id: UUID,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Record that the candidate accepted the offer."""
    o = (
        db.query(Offer)
        .join(Campaign, Offer.campaign_id == Campaign.id)
        .filter(Offer.id == offer_id, Campaign.company_id == company.id)
        .first()
    )
    if not o:
        raise HTTPException(status_code=404, detail="Offer not found")
    if o.status != OfferStatus.sent:
        raise HTTPException(status_code=400, detail=f"Can only accept SENT offers, not '{o.status.value}'")

    o.status = OfferStatus.accepted
    o.response_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(o)
    return _envelope(True, "Offer accepted", _offer_to_dict(o))


@router.post("/{offer_id}/decline")
def decline_offer(
    offer_id: UUID,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Record that the candidate declined the offer."""
    o = (
        db.query(Offer)
        .join(Campaign, Offer.campaign_id == Campaign.id)
        .filter(Offer.id == offer_id, Campaign.company_id == company.id)
        .first()
    )
    if not o:
        raise HTTPException(status_code=404, detail="Offer not found")
    if o.status != OfferStatus.sent:
        raise HTTPException(status_code=400, detail=f"Can only decline SENT offers, not '{o.status.value}'")

    o.status = OfferStatus.declined
    o.response_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(o)
    return _envelope(True, "Offer declined", _offer_to_dict(o))
