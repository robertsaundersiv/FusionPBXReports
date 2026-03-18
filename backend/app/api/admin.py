"""API routes for admin and operational settings."""
import json
import os
from datetime import datetime

from celery import Celery, chain, signature
import redis
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Queue, Agent, User, ETLPipelineStatus, OperationalNote, Extension
from app.auth import get_current_admin, get_current_super_admin, _validate_role
from app.schemas import QueueResponse, AgentResponse, UserResponse, UserUpdate
from typing import List

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


TASK_METADATA = {
    "app.tasks.sync_extensions": {
        "display_name": "Sync Extensions",
        "schedule": "Every 15 minutes",
    },
    "app.tasks.ingest_cdr_records": {
        "display_name": "Ingest CDR Records",
        "schedule": "Every 15 minutes",
    },
    "app.tasks.cleanup_old_cdr_records": {
        "display_name": "Cleanup Old CDR Records",
        "schedule": "Every 15 minutes",
    },
    "app.tasks.sync_metadata": {
        "display_name": "Sync Metadata",
        "schedule": "Every 4 hours",
    },
    "app.tasks.compute_hourly_aggregates": {
        "display_name": "Compute Hourly Aggregates",
        "schedule": "Every 15 minutes",
    },
    "app.tasks.compute_daily_aggregates": {
        "display_name": "Compute Daily Aggregates",
        "schedule": "Daily at 6:00 AM UTC",
    },
}


FORCE_RUN_TASK_SEQUENCE = [
    {"task": "app.tasks.sync_extensions", "kwargs": {}},
    {"task": "app.tasks.sync_metadata", "kwargs": {}},
    {"task": "app.tasks.ingest_cdr_records", "kwargs": {}},
    {"task": "app.tasks.compute_hourly_aggregates", "kwargs": {}},
    {"task": "app.tasks.compute_daily_aggregates", "kwargs": {}},
    {"task": "app.tasks.cleanup_old_cdr_records", "kwargs": {"retention_days": 1825}},
]


def _get_control_celery_app() -> Celery:
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return Celery("admin-control", broker=redis_url, backend=redis_url)


def _parse_result_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _infer_celery_task_name(result_payload: object) -> str | None:
    if not isinstance(result_payload, dict):
        return None

    keys = set(result_payload.keys())
    if {"created", "updated", "failed", "total"}.issubset(keys):
        return "app.tasks.sync_extensions"
    if {"records_synced", "records_skipped", "total_fetched"}.issubset(keys):
        return "app.tasks.ingest_cdr_records"
    if {"records_deleted", "retention_days"}.issubset(keys):
        return "app.tasks.cleanup_old_cdr_records"
    if "stats" in result_payload:
        stats = result_payload.get("stats")
        if isinstance(stats, dict) and {"queues", "agents"}.issubset(stats.keys()):
            return "app.tasks.sync_metadata"
    if "hours_processed" in result_payload:
        return "app.tasks.compute_hourly_aggregates"
    if "days_processed" in result_payload:
        return "app.tasks.compute_daily_aggregates"
    return None


def _load_celery_result_timestamps() -> dict[str, dict]:
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return {}

    try:
        client = redis.Redis.from_url(redis_url, decode_responses=True)
        latest_results: dict[str, dict] = {}

        for key in client.scan_iter(match="celery-task-meta-*", count=200):
            raw_value = client.get(key)
            if not raw_value:
                continue

            try:
                payload = json.loads(raw_value)
            except json.JSONDecodeError:
                continue

            task_name = _infer_celery_task_name(payload.get("result"))
            if not task_name:
                continue

            completed_at = _parse_result_timestamp(payload.get("date_done"))
            if not completed_at:
                continue

            existing = latest_results.get(task_name)
            if existing is None or completed_at > existing["last_executed_at"]:
                latest_results[task_name] = {
                    "last_executed_at": completed_at,
                    "status": payload.get("status", "UNKNOWN"),
                    "source": "celery_result_backend",
                }

        return latest_results
    except redis.RedisError:
        return {}


def _load_quality_health_task_status(db: Session) -> list[dict]:
    celery_results = _load_celery_result_timestamps()
    etl_status = db.query(ETLPipelineStatus).first()

    extension_sync_at = db.query(func.max(Extension.last_synced)).scalar()
    queue_sync_at = db.query(func.max(Queue.last_synced)).scalar()
    agent_sync_at = db.query(func.max(Agent.last_synced)).scalar()

    fallback_timestamps = {
        "app.tasks.sync_extensions": extension_sync_at,
        "app.tasks.ingest_cdr_records": etl_status.last_successful_run if etl_status else None,
        "app.tasks.cleanup_old_cdr_records": None,
        "app.tasks.sync_metadata": max(
            [value for value in (queue_sync_at, agent_sync_at) if value is not None],
            default=None,
        ),
        "app.tasks.compute_hourly_aggregates": etl_status.last_hourly_agg if etl_status else None,
        "app.tasks.compute_daily_aggregates": etl_status.last_daily_agg if etl_status else None,
    }

    task_status = []
    for task_name, metadata in TASK_METADATA.items():
        celery_result = celery_results.get(task_name)
        fallback_timestamp = fallback_timestamps.get(task_name)
        task_status.append(
            {
                "task_name": task_name,
                "display_name": metadata["display_name"],
                "schedule": metadata["schedule"],
                "last_executed_at": celery_result["last_executed_at"] if celery_result else fallback_timestamp,
                "status": celery_result["status"] if celery_result else ("UNAVAILABLE" if fallback_timestamp is None else "SUCCESS"),
                "source": celery_result["source"] if celery_result else ("database_metadata" if fallback_timestamp else "untracked"),
            }
        )

    return task_status


@router.get("/queues", response_model=List[QueueResponse])
async def get_queues(
    current_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Get all queues"""
    queues = db.query(Queue).order_by(Queue.name).all()
    return queues


@router.get("/queues/{queue_id}", response_model=QueueResponse)
async def get_queue(
    queue_id: int,
    current_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Get specific queue"""
    queue = db.query(Queue).filter(Queue.id == queue_id).first()
    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")
    return queue


@router.put("/queues/{queue_id}", response_model=QueueResponse)
async def update_queue(
    queue_id: str,
    queue_data: dict,
    current_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Update queue configuration"""
    queue = db.query(Queue).filter(Queue.queue_id == queue_id).first()
    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")
    
    for key, value in queue_data.items():
        if hasattr(queue, key):
            setattr(queue, key, value)
    
    db.commit()
    db.refresh(queue)
    return queue


# Agent Management
@router.get("/agents", response_model=List[AgentResponse])
async def get_agents(
    current_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Get all agents"""
    agents = db.query(Agent).order_by(Agent.agent_name).all()
    return agents


@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    current_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Get specific agent"""
    numeric_id = None
    try:
        numeric_id = int(agent_id)
    except ValueError:
        numeric_id = None

    if numeric_id is not None:
        agent = db.query(Agent).filter(
            or_(Agent.agent_uuid == agent_id, Agent.id == numeric_id)
        ).first()
    else:
        agent = db.query(Agent).filter(Agent.agent_uuid == agent_id).first()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


# User Management
@router.get("/users", response_model=List[UserResponse])
async def get_users(
    current_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Get all users (admin only)"""
    users = db.query(User).all()
    return users


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Update user (admin/super_admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    current_role = current_user.get("role")
    update_data = user_data.model_dump(exclude_unset=True)

    if current_role == "admin" and user.role == "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin cannot update Super Admin",
        )

    if current_role == "admin" and user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin can only manage operators",
        )

    requested_role = update_data.get("role")
    if requested_role is not None:
        _validate_role(requested_role)

    if current_role == "admin" and requested_role == "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin cannot assign super_admin role",
        )

    if current_role == "admin" and requested_role not in {None, "admin", "operator"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin can only set operator or admin roles",
        )

    # Prevent removing the final enabled super admin via disable or role change.
    if user.role == "super_admin":
        will_disable = update_data.get("enabled") is False
        will_demote = requested_role is not None and requested_role != "super_admin"
        if will_disable or will_demote:
            remaining_enabled_super_admins = (
                db.query(User)
                .filter(User.role == "super_admin", User.enabled == True, User.id != user.id)
                .count()
            )
            if remaining_enabled_super_admins == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot disable or demote the last enabled super admin",
                )

    for key, value in update_data.items():
        if hasattr(user, key):
            setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Delete user (admin/super_admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    current_role = current_user.get("role")
    current_user_id = current_user.get("user_id")

    if current_user_id == user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own account",
        )

    if current_role == "admin" and user.role == "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin cannot delete Super Admin",
        )

    if current_role == "admin" and user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin can only delete operators",
        )

    if user.role == "super_admin":
        remaining_super_admins = db.query(User).filter(User.role == "super_admin", User.id != user.id).count()
        if remaining_super_admins == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete the last super admin",
            )

    db.delete(user)
    db.commit()
    return {"message": "User deleted"}

# ETL Status
@router.get("/etl-status")
async def get_etl_status(
    current_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Get ETL pipeline status"""
    status = db.query(ETLPipelineStatus).first()
    if not status:
        return {
            "status": "idle",
            "last_successful_run": None,
            "error_message": None,
        }
    
    return {
        "status": status.status,
        "last_successful_run": status.last_successful_run,
        "last_ingested_insert_date": status.last_ingested_insert_date,
        "last_queue_sync": status.last_queue_sync,
        "last_agent_sync": status.last_agent_sync,
        "last_hourly_agg": status.last_hourly_agg,
        "last_daily_agg": status.last_daily_agg,
        "error_message": status.error_message,
        "error_count": status.error_count,
    }


@router.get("/quality-health")
async def get_quality_health(
    current_user: dict = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    """Get super-admin quality and worker task health details."""
    etl_status = db.query(ETLPipelineStatus).first()
    task_status = _load_quality_health_task_status(db)
    task_last_executed = {
        task["task_name"]: task.get("last_executed_at")
        for task in task_status
    }

    last_successful_run = etl_status.last_successful_run if etl_status else None
    if last_successful_run is None:
        last_successful_run = task_last_executed.get("app.tasks.ingest_cdr_records")

    last_queue_sync = etl_status.last_queue_sync if etl_status else None
    if last_queue_sync is None:
        last_queue_sync = task_last_executed.get("app.tasks.sync_metadata")

    last_agent_sync = etl_status.last_agent_sync if etl_status else None
    if last_agent_sync is None:
        last_agent_sync = task_last_executed.get("app.tasks.sync_metadata")

    return {
        "pipeline_status": {
            "status": etl_status.status if etl_status else "idle",
            "last_successful_run": last_successful_run,
            "last_ingested_insert_date": etl_status.last_ingested_insert_date if etl_status else None,
            "last_queue_sync": last_queue_sync,
            "last_agent_sync": last_agent_sync,
            "last_hourly_agg": etl_status.last_hourly_agg if etl_status else None,
            "last_daily_agg": etl_status.last_daily_agg if etl_status else None,
            "error_message": etl_status.error_message if etl_status else None,
            "error_count": etl_status.error_count if etl_status else 0,
        },
        "tasks": task_status,
    }


@router.post("/quality-health/run-all")
async def run_all_quality_health_tasks(
    current_user: dict = Depends(get_current_super_admin),
):
    """Enqueue all scheduled Celery tasks in operational dependency order."""
    control_app = _get_control_celery_app()
    task_signatures = [
        signature(task_config["task"], kwargs=task_config["kwargs"], app=control_app)
        for task_config in FORCE_RUN_TASK_SEQUENCE
    ]
    result = chain(*task_signatures).apply_async()

    return {
        "message": "Queued full Celery task run.",
        "chain_id": result.id,
        "tasks": [task_config["task"] for task_config in FORCE_RUN_TASK_SEQUENCE],
    }


# Operational Notes
@router.post("/operational-notes")
async def create_operational_note(
    note: dict,
    current_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Create operational note"""
    new_note = OperationalNote(
        author=current_user.get("sub"),
        **note
    )
    db.add(new_note)
    db.commit()
    db.refresh(new_note)
    return new_note


@router.get("/operational-notes")
async def get_operational_notes(
    current_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Get operational notes"""
    notes = db.query(OperationalNote).order_by(OperationalNote.note_date.desc()).all()
    return notes
