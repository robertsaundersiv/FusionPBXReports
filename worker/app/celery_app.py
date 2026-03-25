"""
Worker package - ETL and scheduled tasks
"""
from celery import Celery
from celery.signals import worker_ready
import os
import logging

logger = logging.getLogger(__name__)

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "phonereports",
    broker=redis_url,
    backend=redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    # Recycle worker child processes after 50 tasks to prevent gradual
    # heap fragmentation / memory growth in long-running workers.
    worker_max_tasks_per_child=50,
    # Expire stored task results after 1 hour to prevent Redis/backend
    # memory accumulation from result set growth.
    result_expires=3600,
)

# Auto-discover tasks
celery_app.autodiscover_tasks(["app.tasks"])


@worker_ready.connect
def on_worker_ready(sender, **kwargs):
    """
    Immediately dispatch critical startup tasks when the worker comes online.
    This ensures queues, agents, extensions, and CDR records are populated
    on a fresh start without waiting for the first beat schedule tick.
    """
    logger.info("Worker ready — dispatching startup tasks")
    # Run in order: metadata (queues+agents) first, then extensions, then CDR
    celery_app.send_task("app.tasks.sync_metadata")
    celery_app.send_task("app.tasks.sync_extensions")
    celery_app.send_task("app.tasks.ingest_cdr_records")
    logger.info("Startup tasks queued")
