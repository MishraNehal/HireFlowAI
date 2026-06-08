from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.middleware import require_auth

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/stats")
def get_stats(auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {
        "success": True,
        "data": {
            "totalCampaigns": 0,
            "activeCampaigns": 0,
            "totalCandidates": 0,
            "interviewsScheduled": 0,
            "offersIssued": 0,
            "pendingCheckpoints": 0,
        },
        "message": "Dashboard stats — live data in Milestone 2",
    }


@router.get("/activity")
def get_activity(auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "data": [], "message": "Activity feed — Milestone 2"}
