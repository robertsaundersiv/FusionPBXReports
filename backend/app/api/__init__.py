"""
API package - initialize routers
"""
from app.api import auth, cdr, dashboard, admin, agent_performance

__all__ = ["auth", "cdr", "dashboard", "admin", "agent_performance"]
