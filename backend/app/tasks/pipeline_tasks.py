from app.tasks.celery_app import celery_app
from app.database import SessionLocal
import logging

logger = logging.getLogger("hireflow.tasks.pipeline")


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30, name="tasks.run_pipeline")
def run_pipeline(self, campaign_id: str, company_id: str):
    """Launch the LangGraph pipeline for a campaign. Built in Milestone 3."""
    logger.info(f"Pipeline task started: campaign={campaign_id}")
    # Full LangGraph orchestration added in Milestone 3
    return {"status": "queued", "campaign_id": campaign_id}
