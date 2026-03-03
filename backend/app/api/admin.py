"""
API routes for admin operations
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Queue, Agent, User, ScheduledReport, ETLPipelineStatus, OperationalNote
from app.auth import get_current_admin, get_current_user
from app.schemas import QueueResponse, AgentResponse, UserResponse, ScheduledReportResponse
from typing import List

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# Queue Management
@router.get("/queues", response_model=List[QueueResponse])
async def get_queues(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all queues"""
    queues = db.query(Queue).order_by(Queue.name).all()
    return queues


@router.get("/queues/{queue_id}", response_model=QueueResponse)
async def get_queue(
    queue_id: int,
    current_user: dict = Depends(get_current_user),
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
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all agents"""
    agents = db.query(Agent).order_by(Agent.agent_name).all()
    return agents


@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get specific agent"""
    agent = db.query(Agent).filter(Agent.agent_id == agent_id).first()
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
    user_data: dict,
    current_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Update user (admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    for key, value in user_data.items():
        if key != 'hashed_password' and hasattr(user, key):
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
    """Delete user (admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db.delete(user)
    db.commit()
    return {"message": "User deleted"}


# Scheduled Reports
@router.get("/scheduled-reports", response_model=List[ScheduledReportResponse])
async def get_scheduled_reports(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get scheduled reports"""
    reports = db.query(ScheduledReport).filter(ScheduledReport.enabled == True).all()
    return reports


@router.post("/scheduled-reports", response_model=ScheduledReportResponse)
async def create_scheduled_report(
    report: dict,
    current_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Create scheduled report"""
    new_report = ScheduledReport(**report)
    db.add(new_report)
    db.commit()
    db.refresh(new_report)
    return new_report


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


# Operational Notes
@router.post("/operational-notes")
async def create_operational_note(
    note: dict,
    current_user: dict = Depends(get_current_user),
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
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get operational notes"""
    notes = db.query(OperationalNote).order_by(OperationalNote.note_date.desc()).all()
    return notes


# Metrics Audit
@router.get("/metrics-audit")
async def get_metrics_audit(
    current_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Get metrics audit data"""
    # Get last hour of CDR data
    from datetime import timedelta
    from sqlalchemy import func
    from app.models import CDRRecord
    
    one_hour_ago = __import__("datetime").datetime.utcnow() - timedelta(hours=1)
    start_epoch = int(one_hour_ago.timestamp())
    
    records = db.query(CDRRecord).filter(
        CDRRecord.start_epoch >= start_epoch
    ).all()
    
    # Calculate audit metrics
    audit_data = {
        'time_window_start': one_hour_ago,
        'time_window_end': __import__("datetime").datetime.utcnow(),
        'total_records': len(records),
        'sample_records': [{'id': r.id, 'uuid': r.xml_cdr_uuid} for r in records[:10]],
        'kpi_calculations': {
            'total_offered': sum(1 for r in records if r.cc_queue_joined_epoch),
            'total_answered': sum(1 for r in records if r.status == 'answered'),
            'total_abandoned': sum(1 for r in records if r.cc_queue_joined_epoch and not r.cc_queue_answered_epoch),
        },
        'data_quality_score': 95.0,
        'warnings': [],
    }
    
    return audit_data
