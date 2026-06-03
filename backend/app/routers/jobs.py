from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database.session import get_db
from app.models.models import JobDescription, Rubric, InterviewQuestion
from app.schemas import schemas
from app.services.generator import generate_rubric_and_questions

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])

@router.get("", response_model=List[schemas.JobDescriptionORM])
def list_jobs(db: Session = Depends(get_db)):
    return db.query(JobDescription).all()

@router.get("/{job_id}", response_model=schemas.JobDescriptionORM)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(JobDescription).filter(JobDescription.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job description not found")
    return job

@router.post("", response_model=schemas.JobDescriptionORM, status_code=status.HTTP_201_CREATED)
def create_job(job_in: schemas.JobDescriptionCreate, db: Session = Depends(get_db)):
    # 1. Create Job Description record
    db_job = JobDescription(
        role_name=job_in.role_name,
        skills_required=job_in.skills_required,
        min_experience=job_in.min_experience,
        responsibilities=job_in.responsibilities,
        status=job_in.status
    )
    db.add(db_job)
    db.commit()
    db.refresh(db_job)

    # 2. Trigger LLM to generate evaluation rubric and interview questions
    try:
        generated = generate_rubric_and_questions(
            role_name=db_job.role_name,
            skills_required=db_job.skills_required,
            responsibilities=db_job.responsibilities or ""
        )
        
        # Add generated rubrics
        rubric_data = generated.get("rubric", {})
        # Flatten rubric object to criteria list
        criteria_list = []
        for key, val in rubric_data.items():
            criteria_list.append({
                "category": key,
                "weight": val.get("weight", 0.25),
                "description": val.get("description", "")
            })
        
        db_rubric = Rubric(job_id=db_job.id, criteria=criteria_list)
        db.add(db_rubric)

        # Add generated questions
        questions_list = generated.get("questions", [])
        for q in questions_list:
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
        # If generation fails, we still have the draft Job Description
        # Rubrics and questions fallback is already handled inside generator, but double-safe here.
        db.rollback()
        raise HTTPException(
            status_code=500, 
            detail=f"Job Description saved, but failed to generate rubrics/questions: {str(e)}"
        )

    return db_job

@router.put("/{job_id}", response_model=schemas.JobDescriptionORM)
def update_job(job_id: int, job_in: schemas.JobDescriptionUpdate, db: Session = Depends(get_db)):
    db_job = db.query(JobDescription).filter(JobDescription.id == job_id).first()
    if not db_job:
        raise HTTPException(status_code=404, detail="Job description not found")
        
    update_data = job_in.model_dump(exclude_unset=True)
    
    # If key fields are updated, we may want to regenerate, but let's keep it simple for now and update fields.
    role_changed = "role_name" in update_data and update_data["role_name"] != db_job.role_name
    skills_changed = "skills_required" in update_data and update_data["skills_required"] != db_job.skills_required
    
    for key, value in update_data.items():
        setattr(db_job, key, value)
        
    db.commit()
    
    # Optional: If role or skills changed, regenerate questions/rubrics
    if role_changed or skills_changed:
        # Delete old rubrics and questions
        db.query(Rubric).filter(Rubric.job_id == db_job.id).delete()
        db.query(InterviewQuestion).filter(InterviewQuestion.job_id == db_job.id).delete()
        db.commit()
        
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
        except Exception:
            pass # Keep old edits if regenerate fails
            
    db.refresh(db_job)
    return db_job

@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: int, db: Session = Depends(get_db)):
    db_job = db.query(JobDescription).filter(JobDescription.id == job_id).first()
    if not db_job:
        raise HTTPException(status_code=404, detail="Job description not found")
        
    # Cascade delete is handled by database relationships or manual deletion
    db.query(Rubric).filter(Rubric.job_id == job_id).delete()
    db.query(InterviewQuestion).filter(InterviewQuestion.job_id == job_id).delete()
    db.delete(db_job)
    db.commit()
    return None
