from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Dict, Any, List
from app.database.session import get_db
from app.models.models import (
    HiringRequest, JobDescription, Candidate, CandidateScore,
    InterviewPipeline, InterviewQuestion
)

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("", response_model=Dict[str, Any])
def get_dashboard(db: Session = Depends(get_db)):
    """
    Returns aggregated data for the recruiter dashboard.
    Provides a full overview of the hiring pipeline state.
    """
    # --- Hiring Requests ---
    hiring_requests = db.query(HiringRequest).order_by(HiringRequest.created_at.desc()).all()

    # --- Job Descriptions ---
    jobs = db.query(JobDescription).order_by(JobDescription.created_at.desc()).all()

    # --- Candidates ---
    candidates = db.query(Candidate).all()

    # --- Scores (most recent per candidate) ---
    scores = db.query(CandidateScore).all()
    score_map: Dict[int, Dict] = {}
    for s in scores:
        # Keep the highest score per candidate
        if s.candidate_id not in score_map or s.total_score > score_map[s.candidate_id]["total_score"]:
            score_map[s.candidate_id] = {
                "candidate_id": s.candidate_id,
                "job_id": s.job_id,
                "total_score": s.total_score,
                "skills_score": s.skills_score,
                "experience_score": s.experience_score,
                "projects_score": s.projects_score,
                "jd_match_score": s.jd_match_score,
                "breakdown_notes": s.breakdown_notes,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }

    # --- Pipelines ---
    pipelines = db.query(InterviewPipeline).all()
    pipeline_status_counts = {
        "Screening": 0, "Interviewing": 0, "HR": 0,
        "Offered": 0, "Rejected": 0
    }
    for p in pipelines:
        if p.status in pipeline_status_counts:
            pipeline_status_counts[p.status] += 1

    # --- Approval Timeline ---
    timeline = []
    for p in sorted(pipelines, key=lambda x: x.last_updated):
        candidate = db.query(Candidate).filter(Candidate.id == p.candidate_id).first()
        cname = candidate.name if candidate else f"Candidate #{p.candidate_id}"

        if p.screening_passed is not None:
            timeline.append({
                "timestamp": p.last_updated.isoformat() if p.last_updated else None,
                "event": f"{'✅ Screening Passed' if p.screening_passed else '❌ Screening Failed'}",
                "candidate": cname,
                "stage": "Screening"
            })
        if p.interview_passed is not None:
            timeline.append({
                "timestamp": p.last_updated.isoformat() if p.last_updated else None,
                "event": f"{'✅ Interview Passed' if p.interview_passed else '❌ Interview Failed'}",
                "candidate": cname,
                "stage": "Interview"
            })
        if p.hr_passed is not None:
            timeline.append({
                "timestamp": p.last_updated.isoformat() if p.last_updated else None,
                "event": f"{'✅ HR Approved – Offer Extended' if p.hr_passed else '❌ HR Rejected'}",
                "candidate": cname,
                "stage": "HR"
            })

    # --- Candidate Rankings (sorted by score) ---
    ranked_candidates = []
    for c in candidates:
        score_data = score_map.get(c.id, {})
        ranked_candidates.append({
            "id": c.id,
            "name": c.name,
            "email": c.email,
            "experience_years": c.experience_years,
            "parsed_skills": c.parsed_skills,
            "total_score": score_data.get("total_score", 0),
            "skills_score": score_data.get("skills_score", 0),
            "experience_score": score_data.get("experience_score", 0),
            "projects_score": score_data.get("projects_score", 0),
            "jd_match_score": score_data.get("jd_match_score", 0),
            "breakdown_notes": score_data.get("breakdown_notes", ""),
            "pipeline_status": next(
                (p.status for p in pipelines if p.candidate_id == c.id), "Not Evaluated"
            )
        })
    ranked_candidates.sort(key=lambda x: x["total_score"], reverse=True)

    return {
        "summary": {
            "total_hiring_requests": len(hiring_requests),
            "total_jobs": len(jobs),
            "total_candidates": len(candidates),
            "total_evaluated": len(score_map),
            "pipeline_status_counts": pipeline_status_counts,
        },
        "hiring_requests": [
            {
                "id": r.id, "company_name": r.company_name, "role_name": r.role_name,
                "experience_level": r.experience_level, "num_openings": r.num_openings,
                "status": r.status, "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in hiring_requests
        ],
        "jobs": [
            {
                "id": j.id, "role_name": j.role_name, "status": j.status,
                "skills_required": j.skills_required, "min_experience": j.min_experience,
                "created_at": j.created_at.isoformat() if j.created_at else None
            }
            for j in jobs
        ],
        "candidate_rankings": ranked_candidates,
        "approval_timeline": sorted(timeline, key=lambda x: x["timestamp"] or ""),
        "offered_candidates": [
            {
                "id": c.id, "name": c.name, "email": c.email,
                "total_score": score_map.get(c.id, {}).get("total_score", 0)
            }
            for c in candidates
            if any(p.status == "Offered" and p.candidate_id == c.id for p in pipelines)
        ]
    }
