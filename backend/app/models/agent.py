"""
Agent model
"""
from sqlalchemy import Column, String, Integer, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base


class Agent(Base):
    __tablename__ = "agents"
    
    agent_id = Column(Integer, primary_key=True)
    agent_name = Column(String, nullable=False, unique=True)
    agent_extension = Column(String)
    agent_contact = Column(String)
    agent_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())