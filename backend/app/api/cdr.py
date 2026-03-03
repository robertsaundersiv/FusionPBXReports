"""
API routes for CDR data and drilldowns
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
from app.database import get_db
from app.models import CDRRecord
from app.auth import get_current_user
from app.schemas import CallRecordResponse
from typing import List, Optional
from datetime import datetime

router = APIRouter(prefix="/api/v1/cdr", tags=["cdr"])


@router.get("/calls", response_model=List[CallRecordResponse])
async def get_call_records(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    queue_id: Optional[str] = Query(None),
    agent_uuid: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    caller_number: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    sort_by: str = Query("start_epoch", regex="^(start_epoch|duration|billsec|rtp_audio_in_mos)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get call records with filtering and pagination
    
    Supports:
    - Date range filtering
    - Queue and agent filtering
    - Direction (inbound/outbound/local)
    - Caller number search
    - Call status filtering
    - Sorting and pagination
    """
    query = db.query(CDRRecord)
    
    # Date filtering
    if start_date:
        query = query.filter(CDRRecord.start_epoch >= int(start_date.timestamp()))
    if end_date:
        query = query.filter(CDRRecord.start_epoch <= int(end_date.timestamp()))
    
    # Queue filtering
    if queue_id:
        query = query.filter(CDRRecord.cc_queue == queue_id)
    
    # Agent filtering
    if agent_uuid:
        query = query.filter(CDRRecord.cc_member_uuid == agent_uuid)
    
    # Direction filtering
    if direction:
        query = query.filter(CDRRecord.direction == direction)
    
    # Caller number search
    if caller_number:
        query = query.filter(CDRRecord.caller_id_number.ilike(f"%{caller_number}%"))
    
    # Status filtering
    if status_filter:
        query = query.filter(CDRRecord.status == status_filter)
    
    # Sorting
    sort_column = getattr(CDRRecord, sort_by)
    if sort_order == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(sort_column)
    
    # Pagination
    skip = (page - 1) * limit
    query = query.offset(skip).limit(limit)
    
    records = query.all()
    return records


@router.get("/calls/{call_uuid}", response_model=CallRecordResponse)
async def get_call_detail(
    call_uuid: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get details for a specific call"""
    record = db.query(CDRRecord).filter(CDRRecord.xml_cdr_uuid == call_uuid).first()
    if not record:
        raise HTTPException(status_code=404, detail="Call not found")
    return record


@router.get("/calls/export/csv")
async def export_calls_csv(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    queue_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export filtered call records as CSV"""
    import csv
    from io import StringIO
    from fastapi.responses import StreamingResponse
    
    query = db.query(CDRRecord)
    
    if start_date:
        query = query.filter(CDRRecord.start_epoch >= int(start_date.timestamp()))
    if end_date:
        query = query.filter(CDRRecord.start_epoch <= int(end_date.timestamp()))
    if queue_id:
        query = query.filter(CDRRecord.cc_queue == queue_id)
    
    records = query.all()
    
    # Generate CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        'Call UUID', 'Start Time', 'Caller', 'Destination', 'Queue',
        'Duration', 'Status', 'Wait Time', 'MOS', 'Hangup Cause'
    ])
    
    # Rows
    for record in records:
        writer.writerow([
            record.xml_cdr_uuid,
            datetime.fromtimestamp(record.start_epoch),
            record.caller_id_number,
            record.destination_number,
            record.cc_queue,
            record.billsec,
            record.status,
            record.cc_queue_answered_epoch - record.cc_queue_joined_epoch if record.cc_queue_answered_epoch and record.cc_queue_joined_epoch else '',
            record.rtp_audio_in_mos,
            record.hangup_cause,
        ])
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=calls.csv"}
    )
