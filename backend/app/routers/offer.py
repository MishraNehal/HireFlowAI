from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from typing import Dict, Any, List
from app.database.session import get_db
from app.models.models import Candidate, JobDescription, InterviewPipeline
from app.schemas import schemas
from app.services.offer_service import generate_offer_letter, generate_onboarding_checklist

router = APIRouter(prefix="/api/offer", tags=["Offer & Onboarding"])


@router.get("/candidates", response_model=List[schemas.InterviewPipelineORM])
def get_offer_candidates(
    job_id: int = Query(None, description="Optional job_id filter"),
    db: Session = Depends(get_db),
):
    """Return all pipeline entries with 'Offered' or 'Shortlisted' status,
    eagerly loading candidate and job relationships for the onboarding list view."""
    query = (
        db.query(InterviewPipeline)
        .options(joinedload(InterviewPipeline.candidate), joinedload(InterviewPipeline.job))
        .filter(InterviewPipeline.status.in_(["Offered", "Shortlisted"]))
    )
    if job_id:
        query = query.filter(InterviewPipeline.job_id == job_id)
    return query.all()


@router.post("/generate", response_model=Dict[str, Any])
def create_offer_letter(payload: schemas.OfferLetterRequest, db: Session = Depends(get_db)):
    """Generates a professional offer letter draft for a selected candidate."""
    # Use payload fields directly — candidate_id is now optional
    candidate_name = payload.candidate_name
    job_title = payload.job_title
    company_name = payload.company_name
    salary = payload.salary or payload.salary_range or None
    start_date = payload.start_date or None
    additional_notes = payload.additional_notes or ""

    # If candidate_id is given, override name from DB
    if payload.candidate_id:
        candidate = db.query(Candidate).filter(Candidate.id == payload.candidate_id).first()
        if candidate:
            candidate_name = candidate.name

    letter = generate_offer_letter(
        candidate_name=candidate_name,
        job_role=job_title,
        company_name=company_name,
        start_date=start_date,
        salary_range=salary,
        additional_notes=additional_notes,
    )

    return {
        "candidate_id": payload.candidate_id,
        "candidate_name": candidate_name,
        "company_name": company_name,
        "offer_letter": letter
    }


@router.post("/onboarding", response_model=Dict[str, Any])
def create_onboarding_checklist(payload: schemas.OnboardingRequest, db: Session = Depends(get_db)):
    """Generates a structured onboarding checklist for a newly hired candidate."""
    candidate_name = payload.candidate_name
    job_title = payload.job_title or "the assigned role"
    company_name = payload.company_name

    # If candidate_id is given, override name from DB
    if payload.candidate_id:
        candidate = db.query(Candidate).filter(Candidate.id == payload.candidate_id).first()
        if candidate:
            candidate_name = candidate.name

    checklist = generate_onboarding_checklist(
        candidate_name=candidate_name,
        job_role=job_title,
        company_name=company_name
    )

    return {
        "candidate_id": payload.candidate_id,
        "candidate_name": candidate_name,
        "company_name": company_name,
        "checklist": checklist
    }
