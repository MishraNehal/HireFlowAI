from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.middleware import require_auth

router = APIRouter(prefix="/api/v1/colleges", tags=["colleges"])


@router.get("/")
def list_colleges(auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "data": [], "message": "Colleges endpoint — Milestone 2"}


@router.post("/")
def add_college(auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "data": {}, "message": "Add college — Milestone 2"}
