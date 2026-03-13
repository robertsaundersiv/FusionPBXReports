"""
Pydantic schemas for API requests and responses
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr


# CDR Schema
class CDRRecordBase(BaseModel):
    xml_cdr_uuid: str
    caller_id_name: Optional[str] = None
    caller_id_number: Optional[str] = None
    destination_number: Optional[str] = None
    direction: str
    start_epoch: int
    answer_epoch: Optional[int] = None
    end_epoch: int
    billsec: int
    cc_queue: Optional[str] = None
    cc_queue_joined_epoch: Optional[int] = None
    cc_queue_answered_epoch: Optional[int] = None
    status: str
    hangup_cause: Optional[str] = None
    rtp_audio_in_mos: Optional[float] = None
    billsec: int = Field(default=0)


class CDRRecordResponse(CDRRecordBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# Queue Schema
class QueueResponse(BaseModel):
    id: int
    queue_id: str
    name: str
    description: Optional[str] = None
    enabled: Optional[bool] = True
    queue_extension: Optional[str] = None
    queue_context: Optional[str] = None
    service_level_threshold: Optional[int] = 30
    timezone: Optional[str] = "America/Phoenix"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Agent Schema
class AgentResponse(BaseModel):
    agent_id: Optional[int] = None
    agent_uuid: Optional[str] = None
    agent_name: str
    agent_contact: Optional[str] = None
    agent_enabled: Optional[bool] = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# User Schema
class UserBase(BaseModel):
    username: str
    email: EmailStr
    role: str = "operator"  # super_admin, admin, operator
    branch_id: Optional[int] = None


class UserCreate(UserBase):
    password: str


class UserResponse(UserBase):
    id: int
    enabled: bool
    can_view_unmasked_numbers: bool
    created_at: datetime

    class Config:
        from_attributes = True


class BranchResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Dashboard KPI Schemas
class KPIMetric(BaseModel):
    name: str
    value: float
    unit: str
    threshold: Optional[Dict[str, float]] = None
    trend: Optional[float] = None  # % change
    definition: str


class DashboardFilter(BaseModel):
    date_range: str = "last_7_days"  # today, yesterday, last_7, last_30, custom
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    queue_ids: Optional[List[str]] = []
    agent_uuids: Optional[List[str]] = []
    direction: Optional[str] = None
    business_hours_only: bool = False
    timezone: str = "America/Phoenix"


class ExecutiveOverviewResponse(BaseModel):
    """Executive Overview Dashboard"""
    offered: KPIMetric
    answer_rate: KPIMetric
    abandon_rate: KPIMetric
    service_level: KPIMetric
    asa: KPIMetric
    aht: KPIMetric
    avg_mos: KPIMetric
    total_talk_time: KPIMetric
    
    offered_trend: List[Dict]
    answered_trend: List[Dict]
    abandoned_trend: List[Dict]
    service_level_trend: List[Dict]
    asa_trend: List[Dict]
    aht_trend: List[Dict]
    mos_trend: List[Dict]
    
    busiest_queues: List[Dict]
    worst_abandon_queues: List[Dict]
    worst_asa_queues: List[Dict]
    lowest_mos_providers: List[Dict]


class QueuePerformanceResponse(BaseModel):
    """Queue Performance Dashboard"""
    queue_id: str
    queue_name: str
    
    metrics: Dict[str, KPIMetric]
    
    hourly_offered: List[Dict]
    hourly_abandoned: List[Dict]
    hourly_asa: List[Dict]
    
    hangup_causes: List[Dict]
    call_outcomes: List[Dict]


class AgentPerformanceResponse(BaseModel):
    """Agent Performance & Coaching Dashboard"""
    agent_uuid: str
    agent_name: str
    
    leaderboard_position: int
    calls_handled: int
    avg_aht: float
    avg_hold: float
    avg_mos: float
    miss_count: int
    total_talk_time: int
    
    trends: List[Dict]
    outliers: List[Dict]


class CallRecordResponse(BaseModel):
    """Call detail record for drilldowns"""
    id: int
    xml_cdr_uuid: str
    start_time: datetime
    caller_id_number: str
    queue_name: Optional[str]
    agent_name: Optional[str]
    status: str
    wait_time: Optional[int]
    billsec: int
    hold_time: int
    mos: Optional[float]
    hangup_cause: Optional[str]


class ScheduledReportBase(BaseModel):
    name: str
    description: Optional[str] = None
    report_type: str
    frequency: str
    format: str = "pdf"


class ScheduledReportCreate(ScheduledReportBase):
    queue_ids: Optional[List[str]] = []
    recipients_email: Optional[List[EmailStr]] = []


class ScheduledReportResponse(ScheduledReportCreate):
    id: int
    enabled: bool
    last_generated: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class MetricsAuditResponse(BaseModel):
    """Metrics audit response for data verification"""
    time_window_start: datetime
    time_window_end: datetime
    
    total_records: int
    sample_records: List[Dict]
    
    kpi_calculations: Dict[str, Dict]
    
    data_quality_score: float
    warnings: List[str]


class RepeatCallerEntry(BaseModel):
    caller_id_number: str
    call_count: int
    answered_count: int
    abandoned_count: int
    queues: List[str]


class RepeatCallersResponse(BaseModel):
    start: datetime
    end: datetime
    repeat_callers: List[RepeatCallerEntry]
