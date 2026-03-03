"""
Queue model
"""
from sqlalchemy import Column, String, Integer, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base


class Queue(Base):
    __tablename__ = "queues"
    
    queue_id = Column(Integer, primary_key=True)
    queue_name = Column(String, nullable=False)
    queue_extension = Column(String)
    queue_description = Column(String)
    queue_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())