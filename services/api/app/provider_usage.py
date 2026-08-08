from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from .config import get_settings
from .database import session_scope
from .models import ProviderUsageEvent, utcnow


FINAL_STATUSES = {"success", "failed", "outcome_unknown", "cancelled"}
COUNTED_STATUSES = {"reserved", "in_progress", "success", "failed", "outcome_unknown"}
FAILURE_STATUSES = {"failed", "outcome_unknown"}
MAX_REPORTED_UNITS = 1_000_000_000


@dataclass(frozen=True)
class ProviderCallSpec:
    operation: str
    model_version: str
    idempotency_key: str


def _hash_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _bounded_units(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_REPORTED_UNITS:
        return None
    return value


def cleanup_provider_usage_events(db: Session) -> int:
    cutoff = utcnow() - timedelta(days=get_settings().provider_usage_retention_days)
    result = db.execute(delete(ProviderUsageEvent).where(ProviderUsageEvent.created_at < cutoff))
    return int(result.rowcount or 0)


def _breaker_until(db: Session, owner: str, provider: str):
    settings = get_settings()
    recent = list(
        db.scalars(
            select(ProviderUsageEvent)
            .where(
                ProviderUsageEvent.owner_email == owner,
                ProviderUsageEvent.provider == provider,
                ProviderUsageEvent.status.in_(FINAL_STATUSES - {"cancelled"}),
            )
            .order_by(ProviderUsageEvent.completed_at.desc(), ProviderUsageEvent.created_at.desc())
            .limit(settings.provider_failure_breaker_threshold)
        )
    )
    if len(recent) < settings.provider_failure_breaker_threshold:
        return None
    if any(event.status not in FAILURE_STATUSES for event in recent):
        return None
    last_failure = recent[0].completed_at or recent[0].created_at
    until = last_failure + timedelta(seconds=settings.provider_breaker_seconds)
    return until if until > utcnow() else None


def reserve_provider_calls(owner: str, provider: str, specs: list[ProviderCallSpec]) -> dict[str, str]:
    """Atomically reserve a bounded set of paid calls before outbound traffic.

    Only hashes of caller-supplied idempotency values are persisted.
    """

    if not specs or len(specs) > 4:
        raise ValueError("Provider call reservations must contain between one and four stages")
    if len({spec.operation for spec in specs}) != len(specs):
        raise ValueError("Provider call reservation operation names must be unique")
    settings = get_settings()
    now = utcnow()
    one_hour_ago = now - timedelta(hours=1)
    one_day_ago = now - timedelta(days=1)
    duplicate_cutoff = now - timedelta(hours=24)
    retention_cutoff = now - timedelta(days=settings.provider_usage_retention_days)
    with session_scope() as db:
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            # Serialize the owner's short quota transaction across API workers so
            # two simultaneous requests cannot both pass the count/duplicate gate.
            lock_value = int.from_bytes(hashlib.sha256(owner.encode("utf-8")).digest()[:8], "big", signed=True)
            db.execute(text("SELECT pg_advisory_xact_lock(:lock_value)"), {"lock_value": lock_value})
        db.execute(delete(ProviderUsageEvent).where(ProviderUsageEvent.created_at < retention_cutoff))
        breaker_until = _breaker_until(db, owner, provider)
        if breaker_until:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Paid provider calls are temporarily paused after repeated failures",
            )
        if provider == "Pangram":
            active_cutoff = now - timedelta(seconds=settings.pangram_reservation_ttl_seconds)
            active_count = int(
                db.scalar(
                    select(func.count(ProviderUsageEvent.id)).where(
                        ProviderUsageEvent.owner_email == owner,
                        ProviderUsageEvent.provider == "Pangram",
                        ProviderUsageEvent.operation == "detection",
                        ProviderUsageEvent.status.in_({"reserved", "in_progress"}),
                        ProviderUsageEvent.created_at >= active_cutoff,
                    )
                )
                or 0
            )
            if active_count + len(specs) > settings.pangram_max_concurrent_calls:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A Pangram detection is already in progress",
                )
            pangram_hourly_count = int(
                db.scalar(
                    select(func.count(ProviderUsageEvent.id)).where(
                        ProviderUsageEvent.owner_email == owner,
                        ProviderUsageEvent.provider == "Pangram",
                        ProviderUsageEvent.operation == "detection",
                        ProviderUsageEvent.status.in_(COUNTED_STATUSES),
                        ProviderUsageEvent.created_at >= one_hour_ago,
                    )
                )
                or 0
            )
            if pangram_hourly_count + len(specs) > settings.pangram_hourly_hard_limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Hourly Pangram detection limit reached",
                )
            pangram_daily_count = int(
                db.scalar(
                    select(func.count(ProviderUsageEvent.id)).where(
                        ProviderUsageEvent.owner_email == owner,
                        ProviderUsageEvent.provider == "Pangram",
                        ProviderUsageEvent.operation == "detection",
                        ProviderUsageEvent.status.in_(COUNTED_STATUSES),
                        ProviderUsageEvent.created_at >= one_day_ago,
                    )
                )
                or 0
            )
            if pangram_daily_count + len(specs) > settings.pangram_daily_hard_limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Daily Pangram detection limit reached",
                )
        hourly_count = int(
            db.scalar(
                select(func.count(ProviderUsageEvent.id)).where(
                    ProviderUsageEvent.owner_email == owner,
                    ProviderUsageEvent.is_paid.is_(True),
                    ProviderUsageEvent.status.in_(COUNTED_STATUSES),
                    ProviderUsageEvent.created_at >= one_hour_ago,
                )
            )
            or 0
        )
        if hourly_count + len(specs) > settings.paid_call_hourly_hard_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Hourly paid-provider call limit reached",
            )
        reservations: dict[str, str] = {}
        for spec in specs:
            key_hash = _hash_key(f"{owner}:{provider}:{spec.operation}:{spec.idempotency_key}")
            duplicate_statuses = {"reserved", "in_progress", "success", "outcome_unknown"}
            if provider == "Pangram" and spec.operation == "detection":
                # A Pangram task can complete and still fail local response/range
                # validation. Treat that as already submitted for cost protection.
                duplicate_statuses.add("failed")
            duplicate = db.scalar(
                select(ProviderUsageEvent.id).where(
                    ProviderUsageEvent.owner_email == owner,
                    ProviderUsageEvent.provider == provider,
                    ProviderUsageEvent.operation == spec.operation,
                    ProviderUsageEvent.idempotency_hash == key_hash,
                    ProviderUsageEvent.status.in_(duplicate_statuses),
                    ProviderUsageEvent.created_at >= duplicate_cutoff,
                )
            )
            if duplicate:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "The same content was already submitted to Pangram within 24 hours"
                        if provider == "Pangram" and spec.operation == "detection"
                        else "A matching paid provider call is already recorded"
                    ),
                )
            event = ProviderUsageEvent(
                id=f"usage_{secrets.token_hex(12)}",
                owner_email=owner,
                provider=provider,
                operation=spec.operation,
                model_version=spec.model_version[:128],
                idempotency_hash=key_hash,
                is_paid=True,
                status="reserved",
            )
            db.add(event)
            reservations[spec.operation] = event.id
        return reservations


def claim_provider_call(reservation_id: str) -> bool:
    """Claim a queued-worker reservation exactly once before outbound traffic."""

    with session_scope() as db:
        event = db.get(ProviderUsageEvent, reservation_id)
        if not event or event.status != "reserved":
            return False
        event.status = "in_progress"
        return True


def finalize_provider_call(
    reservation_id: str,
    *,
    final_status: str,
    error_code: str | None = None,
    latency_ms: int | None = None,
    input_units: int | None = None,
    output_units: int | None = None,
    model_version: str | None = None,
) -> None:
    if final_status not in FINAL_STATUSES:
        raise ValueError("Invalid provider usage status")
    with session_scope() as db:
        event = db.get(ProviderUsageEvent, reservation_id)
        if not event or event.status not in {"reserved", "in_progress"}:
            return
        event.status = final_status
        event.error_code = error_code[:80] if error_code else None
        event.latency_ms = _bounded_units(latency_ms)
        event.input_units = _bounded_units(input_units)
        event.output_units = _bounded_units(output_units)
        if model_version:
            event.model_version = model_version[:128]
        event.completed_at = utcnow()


def cancel_unused_reservations(reservation_ids: list[str]) -> None:
    for reservation_id in reservation_ids:
        finalize_provider_call(reservation_id, final_status="cancelled", error_code="not_submitted")


def provider_usage_summary(db: Session, owner: str) -> dict:
    settings = get_settings()
    now = utcnow()
    buckets = {"hour": timedelta(hours=1), "day": timedelta(days=1), "week": timedelta(days=7), "month": timedelta(days=30)}
    providers = list(
        db.scalars(
            select(ProviderUsageEvent.provider)
            .where(ProviderUsageEvent.owner_email == owner)
            .distinct()
            .order_by(ProviderUsageEvent.provider)
        )
    )

    def aggregate(cutoff):
        rows = list(
            db.scalars(
                select(ProviderUsageEvent).where(
                    ProviderUsageEvent.owner_email == owner,
                    ProviderUsageEvent.created_at >= cutoff,
                )
            )
        )
        counted = [row for row in rows if row.status in COUNTED_STATUSES]
        return {
            "calls": len(counted),
            "successes": sum(row.status == "success" for row in counted),
            "failures": sum(row.status in FAILURE_STATUSES for row in counted),
            "reserved": sum(row.status in {"reserved", "in_progress"} for row in counted),
            "inputUnits": sum(row.input_units or 0 for row in counted),
            "outputUnits": sum(row.output_units or 0 for row in counted),
        }

    periods = {name: aggregate(now - duration) for name, duration in buckets.items()}
    warnings: list[str] = []
    if periods["hour"]["calls"] >= settings.paid_call_hourly_warning:
        warnings.append("Hourly paid-provider usage has reached the configured warning threshold.")
    pangram_hourly_calls = int(
        db.scalar(
            select(func.count(ProviderUsageEvent.id)).where(
                ProviderUsageEvent.owner_email == owner,
                ProviderUsageEvent.provider == "Pangram",
                ProviderUsageEvent.operation == "detection",
                ProviderUsageEvent.status.in_(COUNTED_STATUSES),
                ProviderUsageEvent.created_at >= now - timedelta(hours=1),
            )
        )
        or 0
    )
    if pangram_hourly_calls >= settings.pangram_hourly_warning:
        warnings.append("Hourly Pangram detection usage has reached the configured warning threshold.")
    breaker_state = []
    for provider in providers:
        until = _breaker_until(db, owner, provider)
        breaker_state.append(
            {"provider": provider, "open": until is not None, "reopensAt": until.isoformat() + "Z" if until else None}
        )
        if until:
            warnings.append(f"{provider} paid calls are temporarily paused after repeated failures.")
    return {
        "periods": periods,
        "limits": {
            "hourlyWarning": settings.paid_call_hourly_warning,
            "hourlyHardLimit": settings.paid_call_hourly_hard_limit,
            "pangramHourlyWarning": settings.pangram_hourly_warning,
            "pangramHourlyHardLimit": settings.pangram_hourly_hard_limit,
            "pangramDailyHardLimit": settings.pangram_daily_hard_limit,
            "pangramMaxConcurrentCalls": settings.pangram_max_concurrent_calls,
            "failureBreakerThreshold": settings.provider_failure_breaker_threshold,
            "breakerSeconds": settings.provider_breaker_seconds,
            "retentionDays": settings.provider_usage_retention_days,
        },
        "breakers": breaker_state,
        "warnings": warnings,
        "generatedAt": now.isoformat() + "Z",
        "disclaimer": "Call counts are operational safeguards, not a currency-denominated bill. Confirm charges in each provider dashboard.",
    }
