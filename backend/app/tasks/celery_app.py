from celery import Celery
from app.config import settings

# Upstash Redis (rediss://) requires ssl_cert_reqs parameter
redis_url = settings.REDIS_URL
if redis_url.startswith("rediss://") and "ssl_cert_reqs" not in redis_url:
    redis_url = redis_url + ("&" if "?" in redis_url else "?") + "ssl_cert_reqs=CERT_NONE"

celery_app = Celery(
    "hireflow",
    broker=redis_url,
    backend=redis_url,
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
    broker_use_ssl={"ssl_cert_reqs": "CERT_NONE"},
    redis_backend_use_ssl={"ssl_cert_reqs": "CERT_NONE"},
)