from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database.session import get_db
from app.models.models import HiringRequest
from app.schemas import schemas

router = APIRouter(prefix="/api/hiring-requests", tags=["Hiring Requests"])


@router.get("", response_model=List[schemas.HiringRequestORM])
def list_hiring_requests(db: Session = Depends(get_db)):
    return db.query(HiringRequest).order_by(HiringRequest.created_at.desc()).all()


@router.get("/{request_id}", response_model=schemas.HiringRequestORM)
def get_hiring_request(request_id: int, db: Session = Depends(get_db)):
    req = db.query(HiringRequest).filter(HiringRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Hiring request not found")
    return req


@router.post("", response_model=schemas.HiringRequestORM, status_code=status.HTTP_201_CREATED)
def create_hiring_request(payload: schemas.HiringRequestCreate, db: Session = Depends(get_db)):
    db_req = HiringRequest(
        company_name=payload.company_name,
        role_name=payload.role_name,
        skills_required=payload.skills_required,
        experience_level=payload.experience_level,
        num_openings=payload.num_openings,
        additional_context=payload.additional_context,
        status="Pending"
    )
    db.add(db_req)
    db.commit()
    db.refresh(db_req)
    return db_req


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_hiring_request(request_id: int, db: Session = Depends(get_db)):
    req = db.query(HiringRequest).filter(HiringRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Hiring request not found")
    db.delete(req)
    db.commit()
    return None
