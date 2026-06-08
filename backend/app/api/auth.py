"""
Clerk webhook handler.
Listens for organization.created events and provisions a Company record.
"""
import logging
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from svix.webhooks import Webhook, WebhookVerificationError

from app.database import get_db
from app.models.company import Company, CompanyUser, UserRole
from app.config import settings

logger = logging.getLogger("hireflow.auth")
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _envelope(success: bool, message: str, data=None, error: str = None):
    from datetime import datetime, timezone
    return {
        "success": success,
        "message": message,
        "data": data,
        "error": error,
        "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
    }


@router.post("/webhook")
async def clerk_webhook(request: Request, db: Session = Depends(get_db)):
    """Verify Clerk webhook signature and handle organisation events."""
    payload = await request.body()
    headers = dict(request.headers)

    try:
        wh = Webhook(settings.CLERK_WEBHOOK_SECRET)
        event = wh.verify(payload, headers)
    except WebhookVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event.get("type", "")
    data = event.get("data", {})

    if event_type == "organization.created":
        clerk_org_id = data.get("id")
        org_name = data.get("name", "My Company")

        existing = db.query(Company).filter(Company.clerk_org_id == clerk_org_id).first()
        if not existing:
            company = Company(
                name=org_name,
                clerk_org_id=clerk_org_id,
                is_active=True,
            )
            db.add(company)
            db.commit()
            db.refresh(company)
            logger.info(f"Created company: {company.id} for org {clerk_org_id}")

    elif event_type == "organizationMembership.created":
        clerk_org_id = data.get("organization", {}).get("id")
        clerk_user_id = data.get("public_user_data", {}).get("user_id")
        role_str = data.get("role", "org:member")
        role = UserRole.admin if "admin" in role_str else UserRole.hr

        company = db.query(Company).filter(Company.clerk_org_id == clerk_org_id).first()
        if company and clerk_user_id:
            exists = db.query(CompanyUser).filter(
                CompanyUser.company_id == company.id,
                CompanyUser.clerk_user_id == clerk_user_id,
            ).first()
            if not exists:
                user = CompanyUser(
                    company_id=company.id,
                    clerk_user_id=clerk_user_id,
                    role=role,
                )
                db.add(user)
                db.commit()
                logger.info(f"Added user {clerk_user_id} to company {company.id}")

    return _envelope(True, "Webhook processed")
