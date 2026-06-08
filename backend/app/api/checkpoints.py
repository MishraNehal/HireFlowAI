from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.middleware import require_auth

router = APIRouter(prefix="/api/v1/checkpoints", tags=["checkpoints"])


@router.get("/")
def list_checkpoints(auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "data": [], "message": "Checkpoints endpoint — Milestone 2"}


@router.post("/{checkpoint_id}/approve")
def approve_checkpoint(checkpoint_id: str, auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "data": {"id": checkpoint_id, "status": "approved"}, "message": "Checkpoint approved"}


@router.post("/{checkpoint_id}/reject")
def reject_checkpoint(checkpoint_id: str, auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "data": {"id": checkpoint_id, "status": "rejected"}, "message": "Checkpoint rejected"}
