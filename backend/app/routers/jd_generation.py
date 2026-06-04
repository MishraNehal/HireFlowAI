from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any
from app.database.session import get_db
from app.models.models import HiringRequest, JobDescription
from app.schemas import schemas
from app.services.jd_generator import generate_job_description

router = APIRouter(prefix="/api/jd", tags=["Job Description Generation"])


@router.post("/generate", response_model=Dict[str, Any])
def generate_jd_from_request(payload: schemas.GenerateJDRequest, db: Session = Depends(get_db)):
    """
    Generates a Job Description text from a HiringRequest using the LLM.
    The generated JD text is returned but NOT persisted as a JobDescription yet —
    the recruiter must first approve it, then POST to /api/jd/approve to persist it.
    """
    req = db.query(HiringRequest).filter(HiringRequest.id == payload.hiring_request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Hiring request not found")

    generated = generate_job_description(
        company_name=req.company_name,
        role_name=req.role_name,
        skills_required=req.skills_required,
        experience_level=req.experience_level or "0-2 Years",
        num_openings=req.num_openings,
        additional_context=req.additional_context or ""
    )

    return {
        "hiring_request_id": req.id,
        "generated_jd": generated
    }


@router.post("/approve", response_model=schemas.JobDescriptionORM)
def approve_and_save_jd(
    payload: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """
    Saves the approved JD as a JobDescription record and triggers
    automatic rubric + interview question generation.
    """
    hiring_request_id = payload.get("hiring_request_id")
    jd_data = payload.get("generated_jd", {})

    req = db.query(HiringRequest).filter(HiringRequest.id == hiring_request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Hiring request not found")

    from app.models.models import Rubric, InterviewQuestion
    from app.services.generator import generate_rubric_and_questions

    responsibilities_text = "\n".join(jd_data.get("responsibilities", []))
    skills = jd_data.get("required_skills", req.skills_required)

    # Persist the approved JD
    db_job = JobDescription(
        role_name=jd_data.get("job_title", req.role_name),
        skills_required=skills,
        min_experience=0,
        responsibilities=responsibilities_text,
        status="Approved"
    )
    db.add(db_job)
    db.commit()
    db.refresh(db_job)

    # Update hiring request status
    req.status = "Approved"
    db.commit()

    # Trigger rubric + question generation
    try:
        generated = generate_rubric_and_questions(
            role_name=db_job.role_name,
            skills_required=db_job.skills_required,
            responsibilities=db_job.responsibilities or ""
        )

        criteria_list = []
        for key, val in generated.get("rubric", {}).items():
            criteria_list.append({
                "category": key,
                "weight": val.get("weight", 0.25),
                "description": val.get("description", "")
            })

        db_rubric = Rubric(job_id=db_job.id, criteria=criteria_list)
        db.add(db_rubric)

        for q in generated.get("questions", []):
            db_question = InterviewQuestion(
                job_id=db_job.id,
                question_text=q.get("question_text", ""),
                expected_answer=q.get("expected_answer", ""),
                eval_rubric=q.get("eval_rubric", [])
            )
            db.add(db_question)

        db.commit()
        db.refresh(db_job)
    except Exception as e:
        # JD is saved; rubric/question generation failure is non-fatal
        pass

    return db_job
