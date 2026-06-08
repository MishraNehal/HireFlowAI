from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.middleware import require_auth

router = APIRouter(prefix="/api/v1/offers", tags=["offers"])


@router.get("/")
def list_offers(auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "data": [], "message": "Offers endpoint — Milestone 6"}


@router.post("/")
def create_offer(auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "data": {}, "message": "Create offer — Milestone 6"}


@router.get("/{offer_id}")
def get_offer(offer_id: str, auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "data": {"id": offer_id}, "message": "Get offer — Milestone 6"}


@router.post("/{offer_id}/send")
def send_offer(offer_id: str, auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "message": "Offer sent — Milestone 6"}
