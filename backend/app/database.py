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

engine = create_engine(
    DATABASE_URL,
    pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
    pool_pre_ping=True,
    pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "1800")),
    echo=False,
)


def _should_validate_startup_connection() -> bool:
    return os.getenv("DB_VALIDATE_ON_STARTUP", "true").lower() in {"1", "true", "yes", "on"}


def _validate_startup_connection() -> None:
    max_retries = int(os.getenv("DB_CONNECT_MAX_RETRIES", "5"))
    retry_delay = int(os.getenv("DB_CONNECT_RETRY_DELAY_SECONDS", "2"))

    for attempt in range(max_retries):
        try:
            # Test connection - use text() for SQLAlchemy 2.0+
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database connection successful")
            return
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(
                    f"Database connection attempt {attempt + 1} failed: {e}. Retrying in {retry_delay}s..."
                )
                time.sleep(retry_delay)
            else:
                logger.error(f"Database connection failed after {max_retries} attempts: {e}")
                raise


if _should_validate_startup_connection():
    _validate_startup_connection()

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
