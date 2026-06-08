from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.middleware import require_auth

router = APIRouter(prefix="/api/v1/candidates", tags=["candidates"])


@router.get("/")
def list_candidates(auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "data": [], "message": "Candidates endpoint — Milestone 2"}


@router.get("/{candidate_id}")
def get_candidate(candidate_id: str, auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "data": {"id": candidate_id}, "message": "Get candidate — Milestone 2"}


@router.put("/{candidate_id}/status")
def update_candidate_status(candidate_id: str, auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "data": {"id": candidate_id}, "message": "Update status — Milestone 2"}
