from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.middleware import require_auth

router = APIRouter(prefix="/api/v1/decisions", tags=["decisions"])


@router.get("/")
def list_decisions(auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "data": [], "message": "Decisions endpoint — Milestone 5"}


@router.post("/{candidate_id}/shortlist")
def shortlist_candidate(candidate_id: str, auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "message": "Candidate shortlisted — Milestone 5"}


@router.post("/{candidate_id}/reject")
def reject_candidate(candidate_id: str, auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "message": "Candidate rejected — Milestone 5"}
