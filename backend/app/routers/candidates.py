import os
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from app.database.session import get_db
from app.models.models import Candidate, CandidateScore, JobDescription, InterviewPipeline
from app.schemas import schemas
from app.services.parser import parse_resume
from app.services.evaluator import evaluate_resume

logger = logging.getLogger("hireflow.candidates")

router = APIRouter(prefix="/api/candidates", tags=["Candidates"])

# Ensure uploads directory exists
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.get("", response_model=List[schemas.CandidateORM])
def list_candidates(db: Session = Depends(get_db)):
    return db.query(Candidate).all()

@router.get("/{candidate_id}", response_model=schemas.CandidateORM)
def get_candidate(candidate_id: int, db: Session = Depends(get_db)):
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate

@router.post("/upload", response_model=schemas.CandidateORM, status_code=status.HTTP_201_CREATED)
async def upload_resume(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    # 1. Save uploaded file to disk
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    try:
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
    except Exception as e:
        logger.error(f"Failed to save uploaded file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # 2. Parse PDF
    try:
        parsed = parse_resume(file_path)
    except Exception as e:
        logger.error(f"Failed to parse PDF: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to parse resume: {str(e)}")

    # 3. Create Candidate DB record
    db_candidate = Candidate(
        name=parsed.get("name", "Unknown Candidate"),
        email=parsed.get("email", "unknown@example.com"),
        phone=parsed.get("phone", ""),
        parsed_skills=parsed.get("parsed_skills", []),
        experience_years=float(parsed.get("experience_years", 0.0)),
        resume_path=file_path
    )
    
    db.add(db_candidate)
    db.commit()
    db.refresh(db_candidate)

    return db_candidate

@router.post("/{candidate_id}/evaluate/{job_id}", response_model=Dict[str, Any])
def evaluate_candidate_for_job(candidate_id: int, job_id: int, db: Session = Depends(get_db)):
    # 1. Fetch Candidate and JD
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    job = db.query(JobDescription).filter(JobDescription.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job description not found")

    # 2. Parse resume content to string
    if not candidate.resume_path or not os.path.exists(candidate.resume_path):
        raise HTTPException(status_code=400, detail="Candidate resume file not found on server.")

    try:
        parsed = parse_resume(candidate.resume_path)
        resume_text = parsed.get("resume_text", "")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read resume file: {str(e)}")

    # 3. Call LLM evaluator
    evaluation = evaluate_resume(
        resume_text=resume_text,
        jd_role=job.role_name,
        jd_skills=job.skills_required,
        jd_responsibilities=job.responsibilities or ""
    )

    # 4. Save Candidate Score
    db_score = CandidateScore(
        candidate_id=candidate.id,
        job_id=job.id,
        total_score=evaluation.get("total_score", 50.0),
        skills_score=evaluation.get("skills_score", 50.0),
        experience_score=evaluation.get("experience_score", 50.0),
        projects_score=evaluation.get("projects_score", 50.0),
        jd_match_score=evaluation.get("jd_match_score", 50.0),
        breakdown_notes=evaluation.get("breakdown_notes", "")
    )
    
    db.add(db_score)
    db.commit()
    db.refresh(db_score)

    # 5. Create or Update Interview Pipeline
    db_pipeline = db.query(InterviewPipeline).filter(
        InterviewPipeline.candidate_id == candidate.id,
        InterviewPipeline.job_id == job.id
    ).first()

    # Determine gate pass status (screening pass threshold: 60.0)
    screening_passed = db_score.total_score >= 60.0
    feedback = f"Total Score: {db_score.total_score:.1f}/100. " + db_score.breakdown_notes

    if not db_pipeline:
        db_pipeline = InterviewPipeline(
            candidate_id=candidate.id,
            job_id=job.id,
            status="Interviewing" if screening_passed else "Rejected",
            current_gate="Interview_AI" if screening_passed else "Screening_AI",
            screening_passed=screening_passed,
            screening_gate_feedback=feedback
        )
        db.add(db_pipeline)
    else:
        db_pipeline.screening_passed = screening_passed
        db_pipeline.screening_gate_feedback = feedback
        if screening_passed:
            db_pipeline.status = "Interviewing"
            db_pipeline.current_gate = "Interview_AI"
        else:
            db_pipeline.status = "Rejected"
            db_pipeline.current_gate = "Screening_AI"

    db.commit()
    db.refresh(db_pipeline)

    return {
        "score": db_score,
        "pipeline": {
            "id": db_pipeline.id,
            "status": db_pipeline.status,
            "current_gate": db_pipeline.current_gate,
            "screening_passed": db_pipeline.screening_passed,
            "screening_gate_feedback": db_pipeline.screening_gate_feedback
        }
    }

@router.get("/{candidate_id}/scores", response_model=List[schemas.CandidateScoreORM])
def get_candidate_scores(candidate_id: int, db: Session = Depends(get_db)):
    return db.query(CandidateScore).filter(CandidateScore.candidate_id == candidate_id).all()
