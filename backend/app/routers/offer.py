from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any
from app.database.session import get_db
from app.models.models import Candidate, JobDescription, InterviewPipeline
from app.schemas import schemas
from app.services.offer_service import generate_offer_letter, generate_onboarding_checklist

router = APIRouter(prefix="/api/offer", tags=["Offer & Onboarding"])


@router.post("/generate", response_model=Dict[str, Any])
def create_offer_letter(payload: schemas.OfferLetterRequest, db: Session = Depends(get_db)):
    """Generates a professional offer letter draft for a selected candidate."""
    candidate = db.query(Candidate).filter(Candidate.id == payload.candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    letter = generate_offer_letter(
        candidate_name=candidate.name,
        job_role="the offered position",
        company_name=payload.company_name,
        start_date=payload.start_date,
        salary_range=payload.salary_range,
    )

    return {
        "candidate_id": candidate.id,
        "candidate_name": candidate.name,
        "company_name": payload.company_name,
        "offer_letter": letter
    }


@router.post("/onboarding", response_model=Dict[str, Any])
def create_onboarding_checklist(payload: schemas.OnboardingRequest, db: Session = Depends(get_db)):
    """Generates a structured onboarding checklist for a newly hired candidate."""
    candidate = db.query(Candidate).filter(Candidate.id == payload.candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    checklist = generate_onboarding_checklist(
        candidate_name=candidate.name,
        job_role="the assigned role",
        company_name=payload.company_name
    )

    return {
        "candidate_id": candidate.id,
        "candidate_name": candidate.name,
        "company_name": payload.company_name,
        "checklist": checklist
    }
