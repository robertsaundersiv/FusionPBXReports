"""
Worker package - ETL and scheduled tasks
"""
from celery import Celery
from celery.schedules import schedule
import os
from datetime import timedelta

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
    beat_schedule={
        "sync-extensions": {
            "task": "app.tasks.sync_extensions",
            "schedule": timedelta(minutes=15),  # Run every 15 minutes
        },
        "ingest-cdr-records": {
            "task": "app.tasks.ingest_cdr_records",
            "schedule": timedelta(minutes=15),  # Run every 15 minutes
        },
    },
)

# Auto-discover tasks
celery_app.autodiscover_tasks(["app.tasks"])
