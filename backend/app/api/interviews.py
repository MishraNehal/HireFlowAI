from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.middleware import require_auth

router = APIRouter(prefix="/api/v1/interviews", tags=["interviews"])


@router.get("/")
def list_interviews(auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "data": [], "message": "Interviews endpoint — Milestone 4"}


@router.post("/")
def schedule_interview(auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "data": {}, "message": "Schedule interview — Milestone 4"}


@router.get("/{session_id}")
def get_interview(session_id: str, auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "data": {"id": session_id}, "message": "Get interview — Milestone 4"}


@router.post("/{session_id}/start")
def start_interview(session_id: str, auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "message": "Interview started — Milestone 4"}


@router.post("/{session_id}/end")
def end_interview(session_id: str, auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "message": "Interview ended — Milestone 4"}
