"""
Email service — SendGrid integration for HireFlow.

All outgoing emails go through this service:
  - send_email()      : single email to one recipient
  - send_bulk_email() : batch email to multiple recipients

Every send attempt is logged to the email_logs table regardless of
success/failure, so we have a full audit trail.

If SENDGRID_API_KEY is not set, the service logs the email to console
and marks it as 'sent' (dev mode) — pipeline never blocks on email.
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from app.models.campaign import EmailLog, EmailRecipientType, EmailStatus

logger = logging.getLogger(__name__)


def _get_sendgrid_client():
    """Lazily import SendGrid to avoid hard crash if not installed."""
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail
        return SendGridAPIClient, Mail
    except ImportError:
        raise RuntimeError(
            "sendgrid package not installed. Run: pip install sendgrid"
        )


def send_email(
    db: Session,
    to_email: str,
    subject: str,
    body: str,
    company_id: str,
    campaign_id: Optional[str] = None,
    recipient_type: EmailRecipientType = EmailRecipientType.college,
    email_type: str = "outreach",
) -> EmailLog:
    """
    Send a single email via SendGrid and log it to email_logs table.

    If SENDGRID_API_KEY is empty, logs to console and marks as sent (dev mode).
    Never raises — on failure, logs the error and marks status=failed.

    Returns the EmailLog row (always, even on failure).
    """
    log = EmailLog(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_email=to_email,
        recipient_type=recipient_type,
        email_type=email_type,
        subject=subject,
        body=body,
        status=EmailStatus.pending,
    )
    db.add(log)
    db.flush()  # get log.id without committing

    # ── Dev mode — no API key ─────────────────────────────────────────────────
    if not settings.SENDGRID_API_KEY:
        logger.info(
            f"[Email:DEV] Would send to={to_email} | subject='{subject}' "
            f"(SENDGRID_API_KEY not set — skipping real send)"
        )
        log.status = EmailStatus.sent
        log.sent_at = datetime.utcnow()
        db.commit()
        return log

    # ── Real send via SendGrid ────────────────────────────────────────────────
    try:
        SendGridAPIClient, Mail = _get_sendgrid_client()

        message = Mail(
            from_email=settings.SENDGRID_FROM_EMAIL,
            to_emails=to_email,
            subject=subject,
            html_content=body.replace("\n", "<br>"),
        )

        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sg.send(message)

        if response.status_code in (200, 202):
            log.status = EmailStatus.sent
            log.sent_at = datetime.utcnow()
            logger.info(f"[Email] Sent to {to_email} | status={response.status_code}")
        else:
            log.status = EmailStatus.failed
            logger.error(
                f"[Email] SendGrid returned {response.status_code} for {to_email}"
            )

    except Exception as e:
        log.status = EmailStatus.failed
        logger.error(f"[Email] Failed to send to {to_email}: {e}", exc_info=True)

    db.commit()
    return log


def send_bulk_email(
    db: Session,
    recipients: list[dict],  # [{"email": str, "name": str, "college_id": str (optional)}]
    subject: str,
    body_template: str,       # use {name}, {college} placeholders
    company_id: str,
    campaign_id: Optional[str] = None,
    recipient_type: EmailRecipientType = EmailRecipientType.college,
    email_type: str = "outreach",
) -> list[EmailLog]:
    """
    Send personalised emails to multiple recipients.

    body_template can contain {name} and {college} placeholders that are
    replaced per recipient. All sends are logged individually.

    Returns list of EmailLog rows.
    """
    logs = []
    success_count = 0
    fail_count = 0

    for recipient in recipients:
        email = recipient.get("email", "")
        name = recipient.get("name", "Placement Officer")
        college = recipient.get("college", "your institution")

        if not email:
            logger.warning(f"[Email:Bulk] Skipping recipient with no email: {recipient}")
            continue

        # Personalise body
        personalised_body = (
            body_template
            .replace("{name}", name)
            .replace("{college}", college)
        )

        log = send_email(
            db=db,
            to_email=email,
            subject=subject,
            body=personalised_body,
            company_id=company_id,
            campaign_id=campaign_id,
            recipient_type=recipient_type,
            email_type=email_type,
        )
        logs.append(log)

        if log.status == EmailStatus.sent:
            success_count += 1
        else:
            fail_count += 1

    logger.info(
        f"[Email:Bulk] Sent {success_count} emails, {fail_count} failed "
        f"out of {len(recipients)} recipients"
    )
    return logs
