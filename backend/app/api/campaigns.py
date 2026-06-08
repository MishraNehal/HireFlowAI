from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.middleware import require_auth

router = APIRouter(prefix="/api/v1/campaigns", tags=["campaigns"])


@router.get("/")
def list_campaigns(auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "data": [], "message": "Campaigns endpoint — Milestone 2"}


@router.post("/")
def create_campaign(auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "data": {}, "message": "Create campaign — Milestone 2"}


@router.get("/{campaign_id}")
def get_campaign(campaign_id: str, auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "data": {"id": campaign_id}, "message": "Get campaign — Milestone 2"}


@router.put("/{campaign_id}")
def update_campaign(campaign_id: str, auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "data": {"id": campaign_id}, "message": "Update campaign — Milestone 2"}


@router.delete("/{campaign_id}")
def delete_campaign(campaign_id: str, auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "message": "Campaign deleted — Milestone 2"}
