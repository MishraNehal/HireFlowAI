from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.middleware import require_auth

router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding"])


@router.get("/")
def list_onboarding(auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "data": [], "message": "Onboarding endpoint — Milestone 7"}


@router.post("/{candidate_id}/initiate")
def initiate_onboarding(candidate_id: str, auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "message": "Onboarding initiated — Milestone 7"}
