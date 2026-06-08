from app.tasks.celery_app import celery_app
import logging

logger = logging.getLogger("hireflow.tasks.email")


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30, name="tasks.send_email")
def send_email_task(self, to_email: str, subject: str, body: str, campaign_id: str = None):
    """Send email via SendGrid. Full implementation in Milestone 3."""
    logger.info(f"Email task: to={to_email} subject={subject}")
    return {"status": "queued", "to": to_email}
