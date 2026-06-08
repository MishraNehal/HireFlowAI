from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.middleware import require_auth

router = APIRouter(prefix="/api/v1/resumes", tags=["resumes"])


@router.post("/upload")
def upload_resume(auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "data": {}, "message": "Resume upload — Milestone 2"}


@router.get("/{resume_id}")
def get_resume(resume_id: str, auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "data": {"id": resume_id}, "message": "Get resume — Milestone 2"}


@router.post("/{resume_id}/parse")
def trigger_parse(resume_id: str, auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "message": "Resume parse triggered — Milestone 2"}
