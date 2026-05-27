"""
API routes for authentication
"""
from datetime import datetime, timedelta, timezone
import logging
import os
import ssl
import threading
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, status
import redis
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.schemas import PasswordChangeRequest, UserCreate, UserResponse
from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    get_current_admin,
    _validate_role,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("AUTH_LOGIN_RATE_LIMIT_WINDOW_SECONDS", "60"))
LOGIN_RATE_LIMIT_MAX_ATTEMPTS = int(os.getenv("AUTH_LOGIN_RATE_LIMIT_MAX_ATTEMPTS", "120"))
LOGIN_LOCKOUT_THRESHOLD = int(os.getenv("AUTH_LOGIN_LOCKOUT_THRESHOLD", "5"))
LOGIN_LOCKOUT_SECONDS = int(os.getenv("AUTH_LOGIN_LOCKOUT_SECONDS", "300"))

_redis_client = None

EXEC_WARMUP_BASE_URL = os.getenv("AUTH_EXEC_WARMUP_BASE_URL", "https://localhost")
EXEC_WARMUP_TIMEZONE = os.getenv("AUTH_EXEC_WARMUP_TIMEZONE", "America/Phoenix")
EXEC_WARMUP_TIMEOUT_SECONDS = int(os.getenv("AUTH_EXEC_WARMUP_TIMEOUT_SECONDS", "45"))


def _build_exec_preset_range_utc(preset: str, timezone_name: str) -> tuple[str, str]:
    tzinfo = ZoneInfo(timezone_name)
    now_local = datetime.now(tzinfo)
    current_day = now_local.date()

    if preset == "last_7":
        start_day = current_day - timedelta(days=6)
    elif preset == "last_30":
        start_day = current_day - timedelta(days=29)
    else:
        start_day = current_day

    start_local = datetime(start_day.year, start_day.month, start_day.day, 0, 0, 0, 0, tzinfo=tzinfo)
    end_local = datetime(current_day.year, current_day.month, current_day.day, 23, 59, 59, 999000, tzinfo=tzinfo)

    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    return start_utc.isoformat().replace("+00:00", "Z"), end_utc.isoformat().replace("+00:00", "Z")


def _warm_executive_overview_cache(access_token: str) -> None:
    # Use an unverified local TLS context because production calls localhost behind nginx.
    ssl_context = ssl._create_unverified_context()

    for preset in ("last_7", "last_30"):
        try:
            start_date, end_date = _build_exec_preset_range_utc(preset, EXEC_WARMUP_TIMEZONE)
            query = urlencode(
                {
                    "start_date": start_date,
                    "end_date": end_date,
                    "direction": "inbound",
                    "timezone": EXEC_WARMUP_TIMEZONE,
                }
            )
            url = f"{EXEC_WARMUP_BASE_URL}/api/v1/dashboard/executive-overview?{query}"
            request = Request(url, headers={"Authorization": f"Bearer {access_token}"})
            with urlopen(request, timeout=EXEC_WARMUP_TIMEOUT_SECONDS, context=ssl_context):
                pass
        except Exception as exc:
            logger.warning("Executive warmup for %s skipped due to error: %s", preset, exc)


def _get_redis_client():
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
    return _redis_client


def _normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def _get_client_ip(request: Request) -> str:
    forwarded_for = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    if request.client and request.client.host:
        return request.client.host

    return "unknown"


def _check_rate_limit(client_ip: str, normalized_username: str) -> bool:
    key = f"auth:login:ratelimit:{client_ip}:{normalized_username}"
    try:
        count = _get_redis_client().incr(key)
        if count == 1:
            _get_redis_client().expire(key, LOGIN_RATE_LIMIT_WINDOW_SECONDS)
        return count > LOGIN_RATE_LIMIT_MAX_ATTEMPTS
    except Exception as exc:
        logger.warning("Login rate-limit check skipped due to Redis error: %s", exc)
        return False


def _is_user_locked(normalized_username: str) -> bool:
    key = f"auth:login:lock:{normalized_username}"
    try:
        return bool(_get_redis_client().exists(key))
    except Exception as exc:
        logger.warning("Login lockout check skipped due to Redis error: %s", exc)
        return False


def _record_failed_login(normalized_username: str) -> None:
    fail_key = f"auth:login:fail:{normalized_username}"
    lock_key = f"auth:login:lock:{normalized_username}"
    try:
        failed_count = _get_redis_client().incr(fail_key)
        if failed_count == 1:
            _get_redis_client().expire(fail_key, LOGIN_LOCKOUT_SECONDS)
        if failed_count >= LOGIN_LOCKOUT_THRESHOLD:
            _get_redis_client().setex(lock_key, LOGIN_LOCKOUT_SECONDS, "1")
    except Exception as exc:
        logger.warning("Failed-login tracking skipped due to Redis error: %s", exc)


def _clear_failed_login_state(normalized_username: str) -> None:
    fail_key = f"auth:login:fail:{normalized_username}"
    lock_key = f"auth:login:lock:{normalized_username}"
    try:
        _get_redis_client().delete(fail_key, lock_key)
    except Exception as exc:
        logger.warning("Failed-login reset skipped due to Redis error: %s", exc)


@router.post("/register", response_model=UserResponse)
def register(
    user: UserCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin),
):
    """Register new user (admin/super_admin only)"""
    # Check if user exists
    existing_user = db.query(User).filter(User.username == user.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    # Role checks
    requested_role = user.role or "operator"
    _validate_role(requested_role)

    if current_user.get("role") == "admin" and requested_role == "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin cannot create Super Admin",
        )

    if requested_role not in ["super_admin", "admin", "operator"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be one of super_admin, admin, operator",
        )

    new_user = User(
        username=user.username,
        email=user.email,
        hashed_password=hash_password(user.password),
        role=requested_role,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


@router.post("/change-password")
def change_password(
    payload: PasswordChangeRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change own password for any signed-in user (operator can only this action)"""
    user = db.query(User).filter(User.id == current_user.get("user_id")).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid current password")

    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    db.refresh(user)

    return {"message": "Password changed successfully"}


@router.post("/login")
def login(username: str, password: str, request: Request, db: Session = Depends(get_db)):
    """Login and get JWT token"""
    normalized_username = _normalize_username(username)
    client_ip = _get_client_ip(request)

    if _check_rate_limit(client_ip, normalized_username):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please wait and try again.",
        )

    if _is_user_locked(normalized_username):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account temporarily locked due to failed login attempts.",
        )

    user = db.query(User).filter(User.username == username).first()
    
    if not user or not verify_password(password, user.hashed_password):
        _record_failed_login(normalized_username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    
    if not user.enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account disabled",
        )

    _clear_failed_login_state(normalized_username)
    
    # Create token
    access_token = create_access_token(
        data={
            "sub": user.username,
            "user_id": user.id,
            "role": user.role,
        }
    )
    
    # Reduce write contention under concurrent logins by throttling this update.
    now_utc = datetime.utcnow()
    if user.last_login is None or (now_utc - user.last_login) >= timedelta(minutes=1):
        user.last_login = now_utc
        db.commit()

    # Prime key executive ranges server-side so the first dashboard load is less likely to be cold.
    threading.Thread(target=_warm_executive_overview_cache, args=(access_token,), daemon=True).start()
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role,
        },
    }


@router.get("/me", response_model=UserResponse)
def get_current_user_info(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current user info"""
    user = db.query(User).filter(User.id == current_user.get("user_id")).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user
