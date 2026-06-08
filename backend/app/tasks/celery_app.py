from celery import Celery
from app.config import settings

celery_app = Celery(
    "hireflow",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.pipeline_tasks",
        "app.tasks.email_tasks",
        "app.tasks.evaluation_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_max_retries=3,
    task_default_retry_delay=30,
    broker_connection_retry_on_startup=True,
)
