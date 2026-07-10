from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import AuditEvent, SessionRecord


password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SlidingWindowLimiter:
    def __init__(self, limit: int, seconds: int) -> None:
        self.limit = limit
        self.window = timedelta(seconds=seconds)
        self._events: dict[str, deque[datetime]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = utcnow()
        with self._lock:
            events = self._events[key]
            while events and now - events[0] > self.window:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            if len(self._events) > 5000:
                self._events = defaultdict(deque, {k: v for k, v in self._events.items() if v})
            return True


login_limiter = SlidingWindowLimiter(limit=8, seconds=15 * 60)
api_limiter = SlidingWindowLimiter(limit=240, seconds=60)


def client_key(request: Request) -> str:
    settings = get_settings()
    if settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        if forwarded:
            return forwarded
    return request.client.host if request.client else "unknown"


def audit(db: Session, actor: str, action: str, resource_id: str = "", **details) -> None:
    safe_details = {key: value for key, value in details.items() if key not in {"text", "token", "password", "content"}}
    db.add(AuditEvent(id=f"audit_{secrets.token_hex(12)}", actor=actor, action=action, resource_id=resource_id, details=safe_details))


def create_session(db: Session, owner_email: str) -> tuple[str, datetime]:
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    expires_at = utcnow() + timedelta(hours=settings.session_ttl_hours)
    record = SessionRecord(
        id=f"session_{secrets.token_hex(12)}",
        token_hash=token_hash(token),
        owner_email=owner_email,
        expires_at=expires_at,
    )
    db.add(record)
    return token, expires_at


def validate_owner_credentials(email: str, password: str, totp_code: str) -> bool:
    settings = get_settings()
    normalized_email = email.strip().lower()
    if not settings.owner_password_hash:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Owner access is not configured")
    email_ok = hmac.compare_digest(normalized_email, settings.owner_email)
    password_ok = verify_password(settings.owner_password_hash, password)
    totp_ok = True
    if settings.require_totp:
        if not settings.owner_totp_secret:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Owner access is not configured")
        totp_ok = pyotp.TOTP(settings.owner_totp_secret).verify(totp_code, valid_window=1)
    return email_ok and password_ok and totp_ok


def delete_expired_sessions(db: Session) -> None:
    db.execute(delete(SessionRecord).where(SessionRecord.expires_at <= utcnow()))


def current_owner(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> str:
    if not api_limiter.allow(client_key(request)):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    raw_token = authorization.removeprefix("Bearer ").strip()
    if len(raw_token) < 32 or len(raw_token) > 256:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    session = db.scalar(select(SessionRecord).where(SessionRecord.token_hash == token_hash(raw_token)))
    if not session or session.expires_at <= utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    if session.owner_email != get_settings().owner_email:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    session.last_seen_at = utcnow()
    db.commit()
    return session.owner_email
