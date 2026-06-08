from app.tasks.celery_app import celery_app
import logging

logger = logging.getLogger("hireflow.tasks.evaluation")


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30, name="tasks.evaluate_resume")
def evaluate_resume(self, candidate_id: str, campaign_id: str):
    """Parse and score resume. Full implementation in Milestone 4."""
    logger.info(f"Evaluation task: candidate={candidate_id}")
    return {"status": "queued", "candidate_id": candidate_id}
