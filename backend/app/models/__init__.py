"""
Database models for FusionPBX analytics
"""
from sqlalchemy import Column, String, Integer, BigInteger, Float, DateTime, Boolean, Text, ARRAY, JSON, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

# Export all models
__all__ = [
    'Queue', 
    'Agent', 
    'CDRRecord',
    "Base",
    "AgentQueueTier",
    "HourlyAggregate",
    "DailyAggregate",
    "User",
    "ScheduledReport",
    "ETLPipelineStatus",
    "OperationalNote",
    "Extension",
]


class CDRRecord(Base):
    """Call Detail Records - primary call data"""
    __tablename__ = "cdr_records"

    id = Column(Integer, primary_key=True)
    
    # Core identifiers
    key = Column(String)
    xml_cdr_uuid = Column(String, unique=True, nullable=False, index=True)
    domain_uuid = Column(String, index=True)
    extension_uuid = Column(String)
    
    # Domain and account
    domain_name = Column(String)
    accountcode = Column(String)
    
    # Call direction and language
    direction = Column(String, index=True)
    default_language = Column(String)
    context = Column(String)
    
    # Caller information
    caller_id_name = Column(String)
    caller_id_number = Column(String, index=True)
    caller_destination = Column(String)
    source_number = Column(String)
    destination_number = Column(String)
    
    # Timestamps
    start_epoch = Column(BigInteger, index=True)
    start_stamp = Column(DateTime)
    answer_stamp = Column(DateTime)
    answer_epoch = Column(BigInteger)
    end_epoch = Column(BigInteger)
    end_stamp = Column(DateTime)
    
    # Duration fields
    duration = Column(Integer)
    mduration = Column(Integer)
    billsec = Column(Integer)
    billmsec = Column(Integer)
    
    # Bridge and codec
    bridge_uuid = Column(String)
    read_codec = Column(String)
    read_rate = Column(String)
    write_codec = Column(String)
    write_rate = Column(String)
    
    # Network
    remote_media_ip = Column(String)
    network_addr = Column(String)
    
    # Recording
    record_path = Column(Text)
    record_name = Column(String)
    record_length = Column(Integer)
    record_transcription = Column(Text)
    
    # Call leg
    leg = Column(String)
    pdd_ms = Column(Integer)
    rtp_audio_in_mos = Column(Float)
    
    # Last application
    last_app = Column(String)
    last_arg = Column(String)
    
    # Missed call
    missed_call = Column(Boolean)
    
    # Call Center fields
    cc_side = Column(String)
    cc_member_uuid = Column(String)
    cc_queue_joined_epoch = Column(BigInteger)
    cc_queue = Column(String, index=True)
    cc_member_session_uuid = Column(String)
    cc_agent_uuid = Column(String)
    cc_agent = Column(String)
    cc_agent_type = Column(String)
    cc_agent_bridged = Column(String)
    cc_queue_answered_epoch = Column(BigInteger)
    cc_queue_terminated_epoch = Column(BigInteger)
    cc_queue_canceled_epoch = Column(BigInteger)
    cc_cancel_reason = Column(String)
    cc_cause = Column(String)
    waitsec = Column(Integer)
    call_center_queue_uuid = Column(String)
    
    # Conference
    conference_name = Column(String)
    conference_uuid = Column(String)
    conference_member_id = Column(String)
    
    # Dialing
    digits_dialed = Column(String)
    pin_number = Column(String)
    
    # Hangup
    hangup_cause = Column(String, index=True)
    hangup_cause_q850 = Column(String)
    sip_hangup_disposition = Column(String)
    
    # Raw data
    xml = Column(Text)
    json = Column(Text)
    
    # SIP
    sip_call_id = Column(String)
    originating_leg_uuid = Column(String)
    
    # Additional fields
    voicemail_message = Column(String)
    provider_uuid = Column(String)
    hold_accum_seconds = Column(Integer)
    status = Column(String, index=True)
    call_flow = Column(Text)
    call_disposition = Column(String)
    ring_group_uuid = Column(String)
    ivr_menu_uuid = Column(String)
    
    # Metadata
    insert_date = Column(DateTime)
    insert_user = Column(String)
    update_date = Column(DateTime)
    update_user = Column(String)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('ix_cdr_start_epoch_cc_queue', 'start_epoch', 'cc_queue'),
        Index('ix_cdr_answer_epoch', 'answer_epoch'),
    )


class Queue(Base):
    """Call center queue metadata"""
    __tablename__ = "queues"
    
    id = Column(Integer, primary_key=True)
    queue_id = Column(String(36), unique=True, nullable=False, index=True)
    name = Column(String(256), nullable=False)
    description = Column(Text)
    enabled = Column(Boolean, default=True)
    
    # Queue extension and domain for matching with CDR records
    queue_extension = Column(String(50))  # e.g., "38334"
    queue_context = Column(String(256))  # e.g., "mypbx.fusionpbx.company.com"
    
    # Business hours
    business_hours_start = Column(Integer)  # minutes since midnight
    business_hours_end = Column(Integer)
    
    # Service level threshold (seconds)
    service_level_threshold = Column(Integer, default=30)
    
    # Timezone
    timezone = Column(String(64), default="America/Phoenix")
    
    extra_metadata = Column(JSON)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_synced = Column(DateTime)


class Agent(Base):
    """Call center agent metadata"""
    __tablename__ = "agents"
    
    id = Column(Integer, primary_key=True)
    agent_uuid = Column(String(36), unique=True, nullable=False, index=True)
    agent_name = Column(String(256), nullable=False)
    agent_contact = Column(String(256))
    agent_status = Column(String(50), default="available")
    
    # User mapping
    user_uuid = Column(String(36))
    extension = Column(String(50))
    
    enabled = Column(Boolean, default=True)
    
    extra_metadata = Column(JSON)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_synced = Column(DateTime)


class AgentQueueTier(Base):
    """Agent-Queue membership and priority"""
    __tablename__ = "agent_queue_tiers"
    
    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey('agents.id'))
    queue_id = Column(Integer, ForeignKey('queues.id'))
    tier = Column(Integer)  # priority level
    level = Column(Integer, default=1)
    
    enabled = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('agent_id', 'queue_id', name='uq_agent_queue'),
    )


class HourlyAggregate(Base):
    """Hourly aggregated metrics per queue"""
    __tablename__ = "hourly_aggregates"
    
    id = Column(Integer, primary_key=True)
    hour = Column(DateTime, nullable=False, index=True)
    queue_id = Column(String(36), index=True)
    
    # Volume
    total_offered = Column(Integer, default=0)
    total_answered = Column(Integer, default=0)
    total_abandoned = Column(Integer, default=0)
    
    # Service level
    sum_wait_time = Column(Integer, default=0)  # sum of wait times
    count_wait_records = Column(Integer, default=0)
    sum_asa = Column(Integer, default=0)
    
    # Handle time
    sum_billsec = Column(Integer, default=0)
    sum_hold_time = Column(Integer, default=0)
    
    # Quality
    sum_mos = Column(Float, default=0)
    count_mos_records = Column(Integer, default=0)
    bad_call_count = Column(Integer, default=0)
    
    # Callbacks
    callbacks_offered = Column(Integer, default=0)
    callbacks_answered = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('hour', 'queue_id', name='uq_hourly_hour_queue'),
        Index('ix_hourly_hour', 'hour'),
    )


class DailyAggregate(Base):
    """Daily aggregated metrics per queue/agent"""
    __tablename__ = "daily_aggregates"
    
    id = Column(Integer, primary_key=True)
    date = Column(DateTime, nullable=False, index=True)
    queue_id = Column(String(36), index=True)
    agent_uuid = Column(String(36))
    
    # Volume
    total_offered = Column(Integer, default=0)
    total_answered = Column(Integer, default=0)
    total_abandoned = Column(Integer, default=0)
    
    # Service level
    avg_asa = Column(Float)
    answer_rate = Column(Float)
    abandon_rate = Column(Float)
    service_level_pct = Column(Float)
    
    # Handle time
    avg_aht = Column(Float)
    
    # Quality
    avg_mos = Column(Float)
    bad_call_count = Column(Integer, default=0)
    
    # Repeat callers
    repeat_caller_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('date', 'queue_id', 'agent_uuid', name='uq_daily_date_queue_agent'),
    )


class Branch(Base):
    """Branch locations for users"""
    __tablename__ = "branches"

    id = Column(Integer, primary_key=True)
    name = Column(String(256), unique=True, nullable=False)
    description = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class User(Base):
    """Users (super_admin, admin, operator)"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    username = Column(String(256), unique=True, nullable=False, index=True)
    email = Column(String(256), unique=True, nullable=False)
    hashed_password = Column(String(256), nullable=False)
    
    # Role-based access
    role = Column(String(50), default="operator")  # super_admin, admin, operator
    
    enabled = Column(Boolean, default=True)

    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    branch = relationship("Branch", backref="users")
    
    # Permissions
    can_view_unmasked_numbers = Column(Boolean, default=False)
    assigned_queues = Column(ARRAY(String), default=[])  # which queues user can see
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime)


class ScheduledReport(Base):
    """Scheduled report configuration"""
    __tablename__ = "scheduled_reports"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(256), nullable=False)
    description = Column(Text)
    
    # Report type
    report_type = Column(String(50))  # daily_ops, weekly_pack, monthly_summary, sla_compliance
    
    # Schedule
    schedule = Column(String(50))  # cron expression
    frequency = Column(String(50))  # daily, weekly, monthly
    
    # Filters
    queue_ids = Column(ARRAY(String))
    include_all_queues = Column(Boolean, default=False)
    
    # Output
    format = Column(String(50), default="pdf")  # pdf, csv, json
    recipients_email = Column(ARRAY(String), default=[])
    slack_webhook = Column(String(512))
    
    # Status
    enabled = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_generated = Column(DateTime)


class ETLPipelineStatus(Base):
    """Track ETL pipeline execution"""
    __tablename__ = "etl_pipeline_status"
    
    id = Column(Integer, primary_key=True)
    
    # Watermarks
    last_successful_run = Column(DateTime)
    last_ingested_insert_date = Column(DateTime)
    last_ingested_start_epoch = Column(Integer)
    
    # Queue/Agent sync
    last_queue_sync = Column(DateTime)
    last_agent_sync = Column(DateTime)
    
    # Status
    status = Column(String(50), default="idle")  # idle, running, error
    error_message = Column(Text)
    error_count = Column(Integer, default=0)
    
    # Aggregation status
    last_hourly_agg = Column(DateTime)
    last_daily_agg = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OperationalNote(Base):
    """Timestamped operational notes for managers"""
    __tablename__ = "operational_notes"
    
    id = Column(Integer, primary_key=True)
    
    # Content
    note_text = Column(Text, nullable=False)
    note_date = Column(DateTime, nullable=False, index=True)
    
    # Author and scope
    author = Column(String(256))
    queue_ids = Column(ARRAY(String), default=[])  # tagged to queues
    
    # Visibility
    is_public = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Extension(Base):
    """Extension mapping for employee/agent names"""
    __tablename__ = "extensions"
    
    id = Column(Integer, primary_key=True)
    extension_uuid = Column(String(36), unique=True, index=True)
    extension = Column(String(50), unique=True, nullable=False)
    user_name = Column(String(256))
    user_uuid = Column(String(36))
    department = Column(String(256))
    
    enabled = Column(Boolean, default=True)
    
    extra_metadata = Column(JSON)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_synced = Column(DateTime)
