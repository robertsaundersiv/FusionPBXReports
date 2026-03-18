"""
Database configuration and session management
"""
from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
import os
import logging
import time

logger = logging.getLogger(__name__)

# Build DATABASE_URL from environment variables
db_user = os.getenv("DB_USER", "phonereports_user")
db_password = os.getenv("DB_PASSWORD")
db_host = os.getenv("DB_HOST", "localhost")
db_name = os.getenv("DB_NAME", "phonereports")

if not db_password:
    raise ValueError("DB_PASSWORD environment variable not set in .env file")

DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}/{db_name}"

# Add retry logic for initial connection
max_retries = 5
retry_delay = 2

for attempt in range(max_retries):
    try:
        engine = create_engine(
            DATABASE_URL,
            pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
            pool_pre_ping=True,
            pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "1800")),
            echo=False,
        )
        # Test connection - use text() for SQLAlchemy 2.0+
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection successful")
        break
    except Exception as e:
        if attempt < max_retries - 1:
            logger.warning(f"Database connection attempt {attempt + 1} failed: {e}. Retrying in {retry_delay}s...")
            time.sleep(retry_delay)
        else:
            logger.error(f"Database connection failed after {max_retries} attempts: {e}")
            raise

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Session:
    """Get database session for dependency injection"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context():
    """Context manager for database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
