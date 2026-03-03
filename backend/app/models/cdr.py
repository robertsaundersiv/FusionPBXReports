"""
CDR (Call Detail Record) model
"""
from sqlalchemy import Column, String, Integer, DateTime, Text, Float, BigInteger, Boolean
from sqlalchemy.sql import func
from app.database import Base


class CDRRecord(Base):
    __tablename__ = "cdr_records"
    
    # Primary key - use a simple integer ID
    id = Column(Integer, primary_key=True)
    
    # Core call identifiers
    xml_cdr_uuid = Column(String, unique=True, nullable=False, index=True)
    domain_uuid = Column(String, index=True)
    extension_uuid = Column(String)
    
    # Domain and extension info
    domain_name = Column(String)
    accountcode = Column(String)
    
    # Call direction and settings
    direction = Column(String)
    default_language = Column(String)
    context = Column(String)
    
    # Caller information
    caller_id_name = Column(String)
    caller_id_number = Column(String)
    caller_destination = Column(String)
    source_number = Column(String)
    destination_number = Column(String)
    
    # Timestamps
    start_epoch = Column(BigInteger, index=True)
    start_stamp = Column(DateTime(timezone=True))
    answer_stamp = Column(DateTime(timezone=True))
    answer_epoch = Column(BigInteger)
    end_epoch = Column(BigInteger)
    end_stamp = Column(DateTime(timezone=True))
    
    # Duration fields
    duration = Column(Integer)
    mduration = Column(Integer)
    billsec = Column(Integer)
    billmsec = Column(Integer)
    
    # Bridge and codec info
    bridge_uuid = Column(String)
    read_codec = Column(String)
    read_rate = Column(String)
    write_codec = Column(String)
    write_rate = Column(String)
    
    # Network info
    remote_media_ip = Column(String)
    network_addr = Column(String)
    
    # Recording info
    record_path = Column(String)
    record_name = Column(String)
    record_length = Column(Integer)
    record_transcription = Column(Text)
    
    # Call leg info
    leg = Column(String)
    pdd_ms = Column(Integer)
    rtp_audio_in_mos = Column(Float)
    
    # Last application
    last_app = Column(String)
    last_arg = Column(String)
    
    # Missed call flag
    missed_call = Column(Boolean)
    
    # Call Center fields
    cc_side = Column(String)
    cc_member_uuid = Column(String)
    cc_queue_joined_epoch = Column(BigInteger)
    cc_queue = Column(String)
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
    
    # Conference fields
    conference_name = Column(String)
    conference_uuid = Column(String)
    conference_member_id = Column(String)
    
    # Dialing info
    digits_dialed = Column(String)
    pin_number = Column(String)
    
    # Hangup info
    hangup_cause = Column(String)
    hangup_cause_q850 = Column(String)
    sip_hangup_disposition = Column(String)
    
    # Raw data
    xml = Column(Text)
    json = Column(Text)
    
    # SIP info
    sip_call_id = Column(String)
    originating_leg_uuid = Column(String)
    
    # Additional fields
    voicemail_message = Column(String)
    provider_uuid = Column(String)
    hold_accum_seconds = Column(Integer)
    status = Column(String)
    call_flow = Column(Text)
    call_disposition = Column(String)
    ring_group_uuid = Column(String)
    ivr_menu_uuid = Column(String)
    
    # Metadata
    insert_date = Column(DateTime(timezone=True))
    insert_user = Column(String)
    update_date = Column(DateTime(timezone=True))
    update_user = Column(String)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())