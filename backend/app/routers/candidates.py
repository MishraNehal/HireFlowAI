import os
import re
import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
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

@router.get("/scores", response_model=List[schemas.CandidateScoreORM])
def get_scores_by_job(job_id: int = Query(..., description="Job ID to fetch scores for"), db: Session = Depends(get_db)):
    """Return all candidate scores for a given job_id (used by the ranking page)."""
    scores = db.query(CandidateScore).filter(CandidateScore.job_id == job_id).all()
    results = []
    for s in scores:
        candidate = s.candidate
        pipeline = db.query(InterviewPipeline).filter(
            InterviewPipeline.candidate_id == s.candidate_id,
            InterviewPipeline.job_id == s.job_id
        ).first()
        pipeline_status = pipeline.status if pipeline else "Not Evaluated"
        results.append({
            "id": s.id,
            "candidate_id": s.candidate_id,
            "job_id": s.job_id,
            "total_score": s.total_score,
            "skills_score": s.skills_score,
            "experience_score": s.experience_score,
            "projects_score": s.projects_score,
            "jd_match_score": s.jd_match_score,
            "breakdown_notes": s.breakdown_notes,
            "created_at": s.created_at,
            "name": candidate.name if candidate else "Unknown Candidate",
            "email": candidate.email if candidate else "",
            "parsed_skills": candidate.parsed_skills if candidate else [],
            "pipeline_status": pipeline_status
        })
    return results

@router.get("/{candidate_id}", response_model=schemas.CandidateORM)
def get_candidate(candidate_id: int, db: Session = Depends(get_db)):
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate

@router.post("/upload", response_model=schemas.CandidateORM, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    file: UploadFile = File(...),
    job_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    # 1. Sanitize filename (replace spaces & special chars)
    safe_name = re.sub(r"[^\w\.\-]", "_", file.filename)
    file_path = os.path.join(UPLOAD_DIR, safe_name)

    # 2. Save file to disk
    try:
        content = await file.read()
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="File exceeds 5MB limit.")
        with open(file_path, "wb") as f:
            f.write(content)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save uploaded file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # 3. Parse PDF in a thread so it doesn't block the async event loop
    try:
        parsed = await asyncio.to_thread(parse_resume, file_path)
    except Exception as e:
        logger.warning(f"PDF parse failed for {safe_name}, using minimal fallback. Error: {str(e)}")
        # Still create the candidate with minimal data — don't return 500
        parsed = {
            "name": safe_name.replace(".pdf", "").replace("_", " ").title(),
            "email": "",
            "phone": None,
            "parsed_skills": [],
            "experience_years": 0.0,
            "resume_text": "",
        }

    # 4. Upsert Candidate — avoid IntegrityError on duplicate email
    existing = None
    candidate_email = parsed.get("email", "") or ""
    if candidate_email:
        existing = db.query(Candidate).filter(Candidate.email == candidate_email).first()

    if existing:
        # Update existing candidate with fresh data
        existing.name = parsed.get("name", existing.name) or existing.name
        existing.phone = parsed.get("phone", existing.phone) or existing.phone
        existing.parsed_skills = parsed.get("parsed_skills", existing.parsed_skills) or existing.parsed_skills
        existing.experience_years = float(parsed.get("experience_years", existing.experience_years) or 0.0)
        existing.resume_path = file_path
        db.commit()
        db.refresh(existing)
        return existing
    else:
        db_candidate = Candidate(
            name=parsed.get("name", "Unknown Candidate"),
            email=candidate_email,
            phone=parsed.get("phone", "") or "",
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

    # 4. Create or Update Candidate Score
    db_score = db.query(CandidateScore).filter(
        CandidateScore.candidate_id == candidate.id,
        CandidateScore.job_id == job.id
    ).first()

    if not db_score:
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
    else:
        db_score.total_score = evaluation.get("total_score", 50.0)
        db_score.skills_score = evaluation.get("skills_score", 50.0)
        db_score.experience_score = evaluation.get("experience_score", 50.0)
        db_score.projects_score = evaluation.get("projects_score", 50.0)
        db_score.jd_match_score = evaluation.get("jd_match_score", 50.0)
        db_score.breakdown_notes = evaluation.get("breakdown_notes", "")

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
        "score": {
            "id": db_score.id,
            "candidate_id": db_score.candidate_id,
            "job_id": db_score.job_id,
            "total_score": db_score.total_score,
            "skills_score": db_score.skills_score,
            "experience_score": db_score.experience_score,
            "projects_score": db_score.projects_score,
            "jd_match_score": db_score.jd_match_score,
            "breakdown_notes": db_score.breakdown_notes,
        },
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
    scores = db.query(CandidateScore).filter(CandidateScore.candidate_id == candidate_id).all()
    results = []
    for s in scores:
        candidate = s.candidate
        pipeline = db.query(InterviewPipeline).filter(
            InterviewPipeline.candidate_id == s.candidate_id,
            InterviewPipeline.job_id == s.job_id
        ).first()
        pipeline_status = pipeline.status if pipeline else "Not Evaluated"
        results.append({
            "id": s.id,
            "candidate_id": s.candidate_id,
            "job_id": s.job_id,
            "total_score": s.total_score,
            "skills_score": s.skills_score,
            "experience_score": s.experience_score,
            "projects_score": s.projects_score,
            "jd_match_score": s.jd_match_score,
            "breakdown_notes": s.breakdown_notes,
            "created_at": s.created_at,
            "name": candidate.name if candidate else "Unknown Candidate",
            "email": candidate.email if candidate else "",
            "parsed_skills": candidate.parsed_skills if candidate else [],
            "pipeline_status": pipeline_status
        })
    return results
