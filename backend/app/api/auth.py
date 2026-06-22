"""
Clerk webhook handler.

Listens for organization and membership events and auto-provisions the
matching Company / CompanyUser rows, so no one ever needs to manually
insert these via SQL (as we had to before this was wired up).

Handled events:
- organization.created          -> creates a Company, then triggers a RAG
                                    bootstrap (colleges + synthetic knowledge
                                    base) for it
- organizationMembership.created -> creates a CompanyUser linking a Clerk
                                    user to their company
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from svix.webhooks import Webhook, WebhookVerificationError

from app.database import get_db
from app.models.company import Company, CompanyUser, UserRole
from app.config import settings

logger = logging.getLogger("hireflow.auth")
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _envelope(success: bool, message: str, data=None, error: str = None):
    return {
        "success": success,
        "message": message,
        "data": data,
        "error": error,
        "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
    }


def _handle_organization_created(db: Session, data: dict) -> None:
    clerk_org_id = data.get("id")
    org_name = data.get("name", "My Company")

    existing = db.query(Company).filter(Company.clerk_org_id == clerk_org_id).first()
    if existing:
        logger.info(f"organization.created: company already exists for org {clerk_org_id}, skipping")
        return

    company = Company(name=org_name, clerk_org_id=clerk_org_id, is_active=True)
    db.add(company)
    db.commit()
    db.refresh(company)
    logger.info(f"Created company: {company.id} for org {clerk_org_id}")

    # Trigger the RAG bootstrap (colleges + synthetic knowledge base) so a
    # new company isn't left with an empty knowledge base. Imported lazily
    # to avoid loading the embedding model on every app startup.
    try:
        from data.seed import seed_all
        seed_all(db, company_id=company.id)
        logger.info(f"Bootstrapped RAG knowledge base for company {company.id}")
    except Exception:
        # A bootstrap failure shouldn't fail the whole webhook — the company
        # still got created successfully, and /rag/bootstrap can be called
        # manually later to retry seeding.
        logger.exception(f"RAG bootstrap failed for company {company.id}, continuing anyway")


def _handle_membership_created(db: Session, data: dict) -> None:
    clerk_org_id = data.get("organization", {}).get("id")
    clerk_user_id = data.get("public_user_data", {}).get("user_id")
    role_str = data.get("role", "org:member")
    role = UserRole.admin if "admin" in role_str else UserRole.hr

    if not clerk_org_id or not clerk_user_id:
        logger.warning(f"organizationMembership.created event missing org or user id: {data}")
        return

    company = db.query(Company).filter(Company.clerk_org_id == clerk_org_id).first()
    if not company:
        # Can happen if Clerk delivers events out of order. Not fatal —
        # Clerk retries failed webhooks, but this one already returned 200,
        # so log loudly enough to notice and fix manually if it recurs.
        logger.warning(
            f"organizationMembership.created for org {clerk_org_id} but no matching "
            f"Company exists yet. User {clerk_user_id} was NOT added."
        )
        return

    exists = db.query(CompanyUser).filter(
        CompanyUser.company_id == company.id,
        CompanyUser.clerk_user_id == clerk_user_id,
    ).first()
    if exists:
        logger.info(f"organizationMembership.created: user {clerk_user_id} already in company {company.id}, skipping")
        return

    user = CompanyUser(company_id=company.id, clerk_user_id=clerk_user_id, role=role, is_active=True)
    db.add(user)
    db.commit()
    logger.info(f"Added user {clerk_user_id} to company {company.id} as {role.value}")


@router.post("/webhook")
async def clerk_webhook(request: Request, db: Session = Depends(get_db)):
    """Verify Clerk webhook signature and handle organization events."""
    payload = await request.body()
    headers = dict(request.headers)

    try:
        wh = Webhook(settings.CLERK_WEBHOOK_SECRET)
        event = wh.verify(payload, headers)
    except WebhookVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event.get("type", "")
    data = event.get("data", {})

    try:
        if event_type == "organization.created":
            _handle_organization_created(db, data)
        elif event_type == "organizationMembership.created":
            _handle_membership_created(db, data)
        else:
            logger.info(f"Ignoring unhandled webhook event type: {event_type}")
    except Exception as e:
        db.rollback()
        logger.exception(f"Error handling webhook event {event_type}")
        raise HTTPException(status_code=500, detail=f"Webhook handler failed: {e}")

    return _envelope(True, "Webhook processed")