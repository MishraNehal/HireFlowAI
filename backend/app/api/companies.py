from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware import get_current_company, get_current_user
from app.models.company import Company, CompanyUser

router = APIRouter(prefix="/api/v1/companies", tags=["companies"])


def _envelope(success: bool, message: str, data=None, error: str = None):
    return {
        "success": success,
        "message": message,
        "data": data,
        "error": error,
        "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
    }


@router.get("/me")
def get_my_company(
    company: Company = Depends(get_current_company),
):
    return _envelope(True, "OK", {
        "id": str(company.id),
        "name": company.name,
        "industry": company.industry,
        "location": company.location,
        "clerk_org_id": company.clerk_org_id,
        "is_active": company.is_active,
        "created_at": company.created_at.isoformat(),
    })


@router.patch("/me")
def update_my_company(
    payload: dict,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    allowed = {"name", "industry", "location"}
    for field in allowed:
        if field in payload:
            setattr(company, field, payload[field])
    db.commit()
    db.refresh(company)
    return _envelope(True, "Company updated", {"id": str(company.id), "name": company.name})


@router.get("/me/stats")
def get_company_stats(
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    from app.models.campaign import Campaign, CampaignStatus
    from app.models.candidate import Candidate

    total_campaigns = db.query(Campaign).filter(Campaign.company_id == company.id).count()
    active_campaigns = db.query(Campaign).filter(
        Campaign.company_id == company.id,
        Campaign.status == CampaignStatus.active,
    ).count()
    total_candidates = db.query(Candidate).filter(Candidate.company_id == company.id).count()

    return _envelope(True, "OK", {
        "total_campaigns": total_campaigns,
        "active_campaigns": active_campaigns,
        "total_candidates": total_candidates,
    })
