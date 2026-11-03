from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "portalis",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.ingest_tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1800,
    task_soft_time_limit=1500,
    worker_prefetch_multiplier=1,
)
