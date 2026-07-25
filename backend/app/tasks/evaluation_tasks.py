"""
Evaluation Tasks — Celery tasks for the candidate resume pipeline.

process_resume_task is the bridge between the synchronous Celery worker
and the async resume_intelligence_agent: it opens a DB session, runs the
agent via asyncio.run(), and closes the session — mirroring the pattern
established in pipeline_tasks.py for LangGraph invocation.

process_assessment_task (MCQ/coding/written evaluation) is deferred until
Judge0 is wired up (Task 4.9) — it isn't needed for the resume upload flow.
"""
import asyncio
import logging

from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.agents.resume_intelligence import resume_intelligence_agent

logger = logging.getLogger("hireflow.tasks.evaluation")


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="tasks.process_resume",
)
def process_resume_task(self, candidate_id: str, campaign_id: str, company_id: str):
    """Parses and scores one candidate's resume.

    Queued once per candidate right after upload (see api/resumes.py).
    resume_intelligence_agent already marks the resume "failed" and
    commits that state before raising on error -- this task's job is just
    to run it and hand transient failures to Celery's retry mechanism.
    """
    logger.info(f"[Tasks:ProcessResume] Starting - candidate={candidate_id}")
    db = SessionLocal()

    try:
        result = asyncio.run(
            resume_intelligence_agent(
                candidate_id=candidate_id,
                campaign_id=campaign_id,
                company_id=company_id,
                db=db,
            )
        )
        logger.info(f"[Tasks:ProcessResume] Completed - candidate={candidate_id}: {result}")

        # NOTE: Once Task 4.4 (evaluation_agent) exists, this is where we'd
        # check "are all of this campaign's resumes parsed yet?" and, if so,
        # trigger the shortlist checkpoint via resume_pipeline. Left as a
        # follow-up since evaluation_agent doesn't exist yet -- process_resume_task
        # currently ends after scoring a single candidate.

        return {"status": "ok", **result}

    except ValueError as e:
        # Candidate/resume/campaign not found -- not a transient error,
        # retrying won't help, so fail the task outright.
        logger.error(f"[Tasks:ProcessResume] Non-retryable error - candidate={candidate_id}: {e}")
        return {"status": "error", "candidate_id": candidate_id, "reason": str(e)}

    except Exception as e:
        logger.error(
            f"[Tasks:ProcessResume] Error - candidate={candidate_id}: {e}", exc_info=True
        )
        raise self.retry(exc=e, countdown=30)

    finally:
        db.close()