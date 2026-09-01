from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .billing_catalog import (
    METER_DETECTION,
    METER_DOCUMENTS,
    METER_LABELS,
    METER_REWRITE,
    METER_STORAGE,
    get_plan,
    plan_catalog,
)
from .config import Settings, get_settings
from .database import session_scope
from .models import (
    BillingAccount,
    BillingCheckoutAttempt,
    BillingProductEvent,
    BillingWebhookEvent,
    Document,
    DocumentQuotaRecord,
    DocumentVersion,
    ProductUsageReservation,
    utcnow,
)


STRIPE_API_VERSION = "2026-02-25.clover"
ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing"}
REPLACEABLE_SUBSCRIPTION_STATUSES = {"none", "canceled", "incomplete", "incomplete_expired", "paused", "unpaid"}
PRODUCT_EVENT_NAMES = {
    "billing_conflict",
    "limit_hit",
    "pro_page_viewed",
    "upgrade_clicked",
    "checkout_started",
    "portal_opened",
    "plan_changed",
}


def _id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


def _period_start(now: datetime | None = None) -> datetime:
    current = now or utcnow()
    return current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _from_unix(value: Any) -> datetime | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None)


def _content_bytes(paragraphs: list[dict]) -> int:
    return len(json.dumps(paragraphs, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def estimate_document_bytes(paragraphs: list[dict]) -> int:
    return _content_bytes(paragraphs)


def ensure_billing_account(db: Session, owner_email: str) -> BillingAccount:
    normalized = owner_email.strip().lower()
    account = db.scalar(select(BillingAccount).where(BillingAccount.owner_email == normalized))
    if account:
        settings = get_settings()
        if settings.billing_mode != "disabled" and account.plan_source == "disabled":
            account.plan_key = "free"
            account.plan_source = "default"
            account.updated_at = utcnow()
        _expire_grace_if_needed(account)
        return account
    settings = get_settings()
    initial_plan = settings.billing_disabled_plan if settings.billing_mode == "disabled" else "free"
    account = BillingAccount(
        id=_id("billing_account"),
        owner_email=normalized,
        plan_key=initial_plan,
        plan_source="disabled" if settings.billing_mode == "disabled" else "default",
    )
    db.add(account)
    db.flush()
    return account


def _locked_billing_account(db: Session, owner_email: str) -> BillingAccount:
    account = ensure_billing_account(db, owner_email)
    return db.scalar(select(BillingAccount).where(BillingAccount.id == account.id).with_for_update()) or account


def _expire_grace_if_needed(account: BillingAccount) -> None:
    if account.subscription_status == "past_due" and account.grace_until and account.grace_until <= utcnow():
        account.plan_key = "free"
        account.plan_source = "stripe"
        account.updated_at = utcnow()


def record_product_event(
    db: Session,
    owner_email: str,
    event_name: str,
    trigger: str = "",
    **details: str | int | bool,
) -> None:
    if event_name not in PRODUCT_EVENT_NAMES:
        raise ValueError("Unsupported billing product event")
    account = ensure_billing_account(db, owner_email)
    safe_details = {
        key: value
        for key, value in details.items()
        if key in {"meter", "feature", "limit", "used", "mode", "targetPlan"} and isinstance(value, (str, int, bool))
    }
    db.add(
        BillingProductEvent(
            id=_id("billing_event"),
            owner_email=owner_email,
            event_name=event_name,
            trigger=trigger[:80],
            plan_key=account.plan_key,
            details=safe_details,
        )
    )


def sync_document_quota(
    db: Session,
    document: Document,
    paragraphs: list[dict],
    *,
    original_bytes: int | None = None,
) -> DocumentQuotaRecord:
    record = db.get(DocumentQuotaRecord, document.id)
    if not record:
        record = DocumentQuotaRecord(document_id=document.id, owner_email=document.owner_email)
        db.add(record)
    record.content_bytes = _content_bytes(paragraphs)
    if original_bytes is not None:
        record.original_bytes = max(0, original_bytes)
    record.updated_at = utcnow()
    return record


def backfill_document_quotas(db: Session) -> int:
    """Backfill current text bytes for documents created before billing tables existed.

    Historical original DOCX byte sizes are intentionally not guessed. New uploads
    record exact original bytes at creation time.
    """
    missing = list(
        db.scalars(
            select(Document)
            .outerjoin(DocumentQuotaRecord, DocumentQuotaRecord.document_id == Document.id)
            .where(DocumentQuotaRecord.document_id.is_(None), Document.expires_at > utcnow())
        )
    )
    created = 0
    for document in missing:
        version = db.scalar(
            select(DocumentVersion).where(
                DocumentVersion.id == document.current_version_id,
                DocumentVersion.document_id == document.id,
            )
        )
        if version:
            sync_document_quota(db, document, version.paragraphs, original_bytes=0)
            created += 1
    return created


def _capacity_usage(db: Session, owner_email: str) -> tuple[int, int]:
    document_count = int(
        db.scalar(select(func.count(Document.id)).where(Document.owner_email == owner_email, Document.expires_at > utcnow()))
        or 0
    )
    storage_bytes = int(
        db.scalar(
            select(func.coalesce(func.sum(DocumentQuotaRecord.content_bytes + DocumentQuotaRecord.original_bytes), 0))
            .join(Document, Document.id == DocumentQuotaRecord.document_id)
            .where(Document.owner_email == owner_email, Document.expires_at > utcnow())
        )
        or 0
    )
    return document_count, storage_bytes


def _meter_usage(db: Session, owner_email: str, meter: str) -> int:
    stale_before = utcnow() - timedelta(minutes=30)
    stale = list(
        db.scalars(
            select(ProductUsageReservation).where(
                ProductUsageReservation.owner_email == owner_email,
                ProductUsageReservation.status == "reserved",
                ProductUsageReservation.created_at < stale_before,
            )
        )
    )
    for reservation in stale:
        reservation.status = "released"
        reservation.finalized_at = utcnow()
    return int(
        db.scalar(
            select(func.coalesce(func.sum(ProductUsageReservation.quantity), 0)).where(
                ProductUsageReservation.owner_email == owner_email,
                ProductUsageReservation.meter == meter,
                ProductUsageReservation.period_start == _period_start(),
                ProductUsageReservation.status.in_({"reserved", "queued", "running", "consumed"}),
            )
        )
        or 0
    )


def _quota_error(db: Session, owner_email: str, meter: str, used: int, limit: int) -> None:
    record_product_event(db, owner_email, "limit_hit", meter, meter=meter, used=used, limit=limit)
    db.commit()
    label = METER_LABELS.get(meter, meter)
    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail={
            "code": "quota_exceeded",
            "message": f"{label}额度已用完。你仍可使用未达到额度的其他核心功能。",
            "meter": meter,
            "used": used,
            "limit": limit,
        },
    )


def product_request_key(supplied: str | None, fallback: str) -> str:
    candidate = (supplied or "").strip()
    if candidate:
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", candidate):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Idempotency-Key")
        return candidate
    if get_settings().billing_mode == "disabled":
        return fallback
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Idempotency-Key is required")


def enforce_document_capacity(
    db: Session,
    owner_email: str,
    *,
    additional_documents: int = 0,
    additional_storage_bytes: int = 0,
) -> None:
    account = _locked_billing_account(db, owner_email)
    if get_settings().billing_mode == "disabled":
        return
    plan = get_plan(account.plan_key)
    documents, storage = _capacity_usage(db, owner_email)
    if documents + additional_documents > plan.quotas[METER_DOCUMENTS]:
        _quota_error(db, owner_email, METER_DOCUMENTS, documents, plan.quotas[METER_DOCUMENTS])
    if storage + max(0, additional_storage_bytes) > plan.quotas[METER_STORAGE]:
        _quota_error(db, owner_email, METER_STORAGE, storage, plan.quotas[METER_STORAGE])


def require_entitlement(db: Session, owner_email: str, feature: str) -> None:
    account = ensure_billing_account(db, owner_email)
    plan_key = get_settings().billing_disabled_plan if get_settings().billing_mode == "disabled" else account.plan_key
    plan = get_plan(plan_key)
    if plan.entitlements.get(feature) is True:
        return
    record_product_event(db, owner_email, "limit_hit", feature, feature=feature)
    db.commit()
    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail={
            "code": "entitlement_required",
            "message": "当前套餐不包含此功能。其他核心功能仍可继续使用。",
            "feature": feature,
        },
    )


def enforce_document_storage_replacement(
    db: Session,
    document: Document,
    paragraphs: list[dict],
) -> None:
    record = db.get(DocumentQuotaRecord, document.id)
    previous = record.content_bytes if record else 0
    additional = max(0, _content_bytes(paragraphs) - previous)
    enforce_document_capacity(db, document.owner_email, additional_storage_bytes=additional)


def reserve_product_usage(owner_email: str, meter: str, idempotency_key: str, quantity: int = 1) -> str:
    if meter not in {METER_DETECTION, METER_REWRITE} or quantity < 1:
        raise ValueError("Invalid product usage reservation")
    digest = hashlib.sha256(f"{_period_start().isoformat()}:{idempotency_key}".encode("utf-8")).hexdigest()
    with session_scope() as db:
        account = _locked_billing_account(db, owner_email)
        existing = db.scalar(
            select(ProductUsageReservation).where(
                ProductUsageReservation.owner_email == owner_email,
                ProductUsageReservation.meter == meter,
                ProductUsageReservation.idempotency_hash == digest,
            )
        )
        if existing:
            if existing.status != "released":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "duplicate_request",
                        "message": "This paid request was already accepted; refresh its result before retrying.",
                    },
                )
            plan = get_plan(account.plan_key)
            used = _meter_usage(db, owner_email, meter)
            if get_settings().billing_mode != "disabled" and used + quantity > plan.quotas[meter]:
                _quota_error(db, owner_email, meter, used, plan.quotas[meter])
            existing.status = "reserved"
            existing.quantity = quantity
            existing.period_start = _period_start()
            existing.finalized_at = None
            existing.created_at = utcnow()
            return existing.id
        plan = get_plan(account.plan_key)
        used = _meter_usage(db, owner_email, meter)
        if get_settings().billing_mode != "disabled" and used + quantity > plan.quotas[meter]:
            _quota_error(db, owner_email, meter, used, plan.quotas[meter])
        reservation = ProductUsageReservation(
            id=_id("quota"),
            owner_email=owner_email,
            meter=meter,
            quantity=quantity,
            idempotency_hash=digest,
            period_start=_period_start(),
        )
        db.add(reservation)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            duplicate = db.scalar(
                select(ProductUsageReservation).where(
                    ProductUsageReservation.owner_email == owner_email,
                    ProductUsageReservation.meter == meter,
                    ProductUsageReservation.idempotency_hash == digest,
                )
            )
            if not duplicate:
                raise
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "duplicate_request",
                    "message": "This paid request is already in progress.",
                },
            )
        return reservation.id


def finalize_product_usage(reservation_id: str, *, consumed: bool, db: Session | None = None) -> None:
    if not reservation_id:
        return
    if db is not None:
        reservation = db.scalar(
            select(ProductUsageReservation).where(ProductUsageReservation.id == reservation_id).with_for_update()
        )
        if not reservation or reservation.status not in {"reserved", "queued", "running"}:
            return
        reservation.status = "consumed" if consumed else "released"
        reservation.finalized_at = utcnow()
        return
    with session_scope() as owned_db:
        reservation = owned_db.scalar(
            select(ProductUsageReservation).where(ProductUsageReservation.id == reservation_id).with_for_update()
        )
        if not reservation or reservation.status not in {"reserved", "queued", "running"}:
            return
        reservation.status = "consumed" if consumed else "released"
        reservation.finalized_at = utcnow()


def queue_product_usage(reservation_id: str, job_id: str, db: Session) -> None:
    reservation = db.scalar(
        select(ProductUsageReservation).where(ProductUsageReservation.id == reservation_id).with_for_update()
    )
    if not reservation or reservation.status != "reserved":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Product quota reservation is not queueable")
    reservation.status = "queued"
    reservation.job_id = job_id


def claim_product_usage(reservation_id: str, job_id: str, db: Session) -> bool:
    if not reservation_id:
        return True
    reservation = db.scalar(
        select(ProductUsageReservation).where(ProductUsageReservation.id == reservation_id).with_for_update()
    )
    if not reservation or reservation.status != "queued" or reservation.job_id != job_id:
        return False
    reservation.status = "running"
    return True


def billing_summary(db: Session, owner_email: str) -> dict:
    account = ensure_billing_account(db, owner_email)
    effective_plan_key = get_settings().billing_disabled_plan if get_settings().billing_mode == "disabled" else account.plan_key
    plan = get_plan(effective_plan_key)
    documents, storage = _capacity_usage(db, owner_email)
    usage = {
        METER_DOCUMENTS: documents,
        METER_STORAGE: storage,
        METER_DETECTION: _meter_usage(db, owner_email, METER_DETECTION),
        METER_REWRITE: _meter_usage(db, owner_email, METER_REWRITE),
    }
    catalog = plan_catalog()
    checkout_attempt = db.scalar(
        select(BillingCheckoutAttempt)
        .where(BillingCheckoutAttempt.billing_account_id == account.id)
        .order_by(BillingCheckoutAttempt.created_at.desc())
        .limit(1)
    )
    warnings: list[str] = []
    if checkout_attempt and checkout_attempt.status == "conflict":
        warnings.append("Stripe reported a conflicting subscription. Do not retry payment; contact support for reconciliation.")
    elif checkout_attempt and checkout_attempt.status == "completed" and plan.key != "pro":
        warnings.append("Checkout completed, but the subscription webhook has not granted Pro yet.")
    funnel_rows = db.execute(
        select(BillingProductEvent.event_name, func.count(BillingProductEvent.id))
        .where(BillingProductEvent.owner_email == owner_email)
        .group_by(BillingProductEvent.event_name)
    ).all()
    return {
        "mode": get_settings().billing_mode,
        "plan": {
            "key": plan.key,
            "name": plan.name,
            "source": account.plan_source,
            "description": plan.description,
            "entitlements": plan.entitlements,
        },
        "subscription": {
            "status": account.subscription_status,
            "cancelAtPeriodEnd": account.cancel_at_period_end,
            "currentPeriodEnd": account.current_period_end.isoformat() if account.current_period_end else None,
            "graceUntil": account.grace_until.isoformat() if account.grace_until else None,
            "canManage": bool(account.provider_customer_id and get_settings().billing_mode == "stripe"),
            "checkoutStatus": checkout_attempt.status if checkout_attempt else "none",
        },
        "usage": {
            meter: {"used": used, "limit": plan.quotas[meter], "remaining": max(0, plan.quotas[meter] - used)}
            for meter, used in usage.items()
        },
        "plans": [
            {
                "key": item.key,
                "name": item.name,
                "description": item.description,
                "entitlements": item.entitlements,
                "quotas": item.quotas,
            }
            for item in catalog.values()
        ],
        "checkoutAvailable": get_settings().billing_mode in {"test", "stripe"},
        "funnel": {name: int(count) for name, count in funnel_rows},
        "periodStart": _period_start().isoformat(),
        "warnings": warnings,
    }


def _stripe_client(settings: Settings):
    try:
        from stripe import StripeClient
    except ImportError as exc:  # pragma: no cover - deployment dependency guard
        raise RuntimeError("Stripe SDK is not installed") from exc
    return StripeClient(settings.stripe_secret_key)


def create_checkout_session(db: Session, owner_email: str, trigger: str = "pricing") -> str:
    settings = get_settings()
    account = _locked_billing_account(db, owner_email) if settings.billing_mode == "test" else ensure_billing_account(db, owner_email)
    if settings.billing_mode == "test":
        account.plan_key = "pro"
        account.plan_source = "test"
        account.subscription_status = "active"
        account.current_period_end = utcnow() + timedelta(days=30)
        account.updated_at = utcnow()
        record_product_event(db, owner_email, "checkout_started", trigger, mode="test", targetPlan="pro")
        record_product_event(db, owner_email, "plan_changed", trigger, mode="test", targetPlan="pro")
        db.commit()
        return f"{settings.billing_app_url}/?billing=test-success"
    if settings.billing_mode != "stripe":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Billing checkout is not enabled")
    if account.plan_key == "pro" and account.provider_customer_id:
        return create_portal_session(db, owner_email, trigger)
    account = _locked_billing_account(db, owner_email)
    attempt = db.scalar(
        select(BillingCheckoutAttempt)
        .where(BillingCheckoutAttempt.billing_account_id == account.id)
        .order_by(BillingCheckoutAttempt.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    now = utcnow()
    if attempt and attempt.status in {"creating", "open", "completed"} and attempt.price_id != settings.stripe_pro_monthly_price_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Checkout price changed; reconcile the existing attempt before retrying",
        )
    if attempt and attempt.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Checkout completed and subscription reconciliation is still pending",
        )
    if (
        attempt
        and attempt.status == "open"
        and attempt.expires_at
        and attempt.expires_at > now
        and isinstance(attempt.checkout_url, str)
        and attempt.checkout_url.startswith("https://checkout.stripe.com/")
    ):
        return attempt.checkout_url
    if attempt and attempt.status == "open" and attempt.expires_at and attempt.expires_at <= now:
        attempt.status = "expired"
        attempt.updated_at = now
    if not attempt or attempt.status in {"expired", "failed", "closed"}:
        attempt = BillingCheckoutAttempt(
            id=_id("checkout_attempt"),
            billing_account_id=account.id,
            attempt_token=secrets.token_hex(16),
            price_id=settings.stripe_pro_monthly_price_id,
        )
        db.add(attempt)
    elif attempt.status not in {"creating", "open"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Checkout is not ready for another attempt")
    db.commit()
    params: dict[str, Any] = {
        "mode": "subscription",
        "line_items": [{"price": settings.stripe_pro_monthly_price_id, "quantity": 1}],
        "success_url": f"{settings.billing_app_url}/?billing=success&session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{settings.billing_app_url}/?billing=cancelled",
        "client_reference_id": account.id,
        "metadata": {"billing_account_id": account.id, "target_plan": "pro"},
        "subscription_data": {"metadata": {"billing_account_id": account.id, "target_plan": "pro"}},
        "allow_promotion_codes": True,
    }
    if account.provider_customer_id:
        params["customer"] = account.provider_customer_id
    else:
        params["customer_email"] = owner_email
    client = _stripe_client(settings)
    try:
        checkout = client.v1.checkout.sessions.create(
            params,
            options={
                "stripe_version": STRIPE_API_VERSION,
                "idempotency_key": f"checkout-{account.id}-{attempt.attempt_token}",
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to start Stripe Checkout") from exc
    url = getattr(checkout, "url", None)
    session_id = getattr(checkout, "id", None)
    expires_at = _from_unix(getattr(checkout, "expires_at", None))
    if (
        not isinstance(url, str)
        or not url.startswith("https://checkout.stripe.com/")
        or not isinstance(session_id, str)
        or not session_id.startswith("cs_")
        or not expires_at
        or expires_at <= utcnow()
    ):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Stripe did not return a valid Checkout URL")
    current_attempt = db.scalar(
        select(BillingCheckoutAttempt)
        .where(BillingCheckoutAttempt.id == attempt.id)
        .with_for_update()
    )
    if not current_attempt or current_attempt.attempt_token != attempt.attempt_token:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Checkout attempt changed during creation")
    current_attempt.provider_session_id = session_id
    current_attempt.checkout_url = url
    current_attempt.status = "open"
    current_attempt.expires_at = expires_at
    current_attempt.updated_at = utcnow()
    record_product_event(db, owner_email, "checkout_started", trigger, mode="stripe", targetPlan="pro")
    db.commit()
    return url


def create_portal_session(db: Session, owner_email: str, trigger: str = "billing") -> str:
    settings = get_settings()
    account = ensure_billing_account(db, owner_email)
    if settings.billing_mode != "stripe" or not account.provider_customer_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No Stripe customer is available to manage")
    client = _stripe_client(settings)
    try:
        portal = client.v1.billing_portal.sessions.create(
            {"customer": account.provider_customer_id, "return_url": f"{settings.billing_app_url}/?billing=returned"},
            options={"stripe_version": STRIPE_API_VERSION},
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to open the Stripe Customer Portal") from exc
    url = getattr(portal, "url", None)
    if not isinstance(url, str) or not url.startswith("https://billing.stripe.com/"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Stripe did not return a valid portal URL")
    record_product_event(db, owner_email, "portal_opened", trigger, mode="stripe")
    db.commit()
    return url


def set_test_plan(db: Session, owner_email: str, plan_key: str) -> None:
    settings = get_settings()
    if settings.billing_mode != "test" or settings.is_production:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test billing is not enabled")
    if plan_key not in {"free", "pro"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid test plan")
    account = _locked_billing_account(db, owner_email)
    account.plan_key = plan_key
    account.plan_source = "test"
    account.subscription_status = "active" if plan_key == "pro" else "canceled"
    account.current_period_end = utcnow() + timedelta(days=30) if plan_key == "pro" else None
    account.grace_until = None
    account.cancel_at_period_end = False
    account.updated_at = utcnow()
    record_product_event(db, owner_email, "plan_changed", "test_control", mode="test", targetPlan=plan_key)
    db.commit()


def verify_stripe_event(payload: bytes, signature: str) -> dict:
    settings = get_settings()
    if settings.billing_mode != "stripe":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Billing webhook is not enabled")
    if not signature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Stripe signature")
    try:
        from stripe import SignatureVerificationError, Webhook

        event = Webhook.construct_event(
            payload,
            signature,
            settings.stripe_webhook_secret,
            api_key=settings.stripe_secret_key,
        )
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Stripe SDK is not installed") from exc
    except (ValueError, SignatureVerificationError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Stripe webhook") from exc
    converted = event.to_dict() if hasattr(event, "to_dict") else dict(event)
    if not isinstance(converted, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Stripe webhook")
    return converted


def _account_for_event(db: Session, obj: dict) -> BillingAccount | None:
    metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
    account_id = metadata.get("billing_account_id")
    if isinstance(account_id, str):
        account = db.scalar(select(BillingAccount).where(BillingAccount.id == account_id).with_for_update())
        if account:
            return account
    subscription_id = obj.get("id") if obj.get("object") == "subscription" else obj.get("subscription")
    if isinstance(subscription_id, str):
        account = db.scalar(
            select(BillingAccount).where(BillingAccount.provider_subscription_id == subscription_id).with_for_update()
        )
        if account:
            return account
    customer_id = obj.get("customer")
    if isinstance(customer_id, str):
        return db.scalar(select(BillingAccount).where(BillingAccount.provider_customer_id == customer_id).with_for_update())
    return None


def _subscription_price_ids(obj: dict) -> set[str]:
    items = obj.get("items") if isinstance(obj.get("items"), dict) else {}
    data = items.get("data") if isinstance(items.get("data"), list) else []
    result: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        price = item.get("price") if isinstance(item.get("price"), dict) else {}
        price_id = price.get("id")
        if isinstance(price_id, str):
            result.add(price_id)
    return result


def _subscription_period_end(obj: dict) -> datetime | None:
    direct = _from_unix(obj.get("current_period_end"))
    if direct:
        return direct
    items = obj.get("items") if isinstance(obj.get("items"), dict) else {}
    values = [
        _from_unix(item.get("current_period_end"))
        for item in items.get("data", [])
        if isinstance(item, dict)
    ]
    return max((value for value in values if value), default=None)


def _subscription_event_rank(event_type: str, subscription_status: str) -> int:
    if event_type == "customer.subscription.deleted" or subscription_status in REPLACEABLE_SUBSCRIPTION_STATUSES:
        return 40
    if subscription_status == "past_due":
        return 30
    if subscription_status in ACTIVE_SUBSCRIPTION_STATUSES:
        return 20
    return 35


def _checkout_attempt_for_event(
    db: Session,
    account: BillingAccount,
    obj: dict,
) -> BillingCheckoutAttempt | None:
    session_id = obj.get("id")
    if isinstance(session_id, str):
        return db.scalar(
            select(BillingCheckoutAttempt)
            .where(
                BillingCheckoutAttempt.provider_session_id == session_id,
                BillingCheckoutAttempt.billing_account_id == account.id,
            )
            .with_for_update()
        )
    return None


def process_stripe_event(db: Session, event: dict, payload: bytes) -> str:
    event_id = event.get("id")
    event_type = event.get("type")
    if not isinstance(event_id, str) or not event_id.startswith("evt_") or not isinstance(event_type, str):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Stripe event envelope")
    if get_settings().is_production and event.get("livemode") is not True:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Live Stripe event required")
    payload_hash = hashlib.sha256(payload).hexdigest()
    existing = db.scalar(
        select(BillingWebhookEvent).where(BillingWebhookEvent.provider_event_id == event_id).with_for_update()
    )
    if existing and existing.payload_hash != payload_hash:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stripe event replay payload mismatch")
    if existing and existing.status == "processed":
        return "duplicate"
    provider_created = _from_unix(event.get("created"))
    ledger = existing or BillingWebhookEvent(
        id=_id("stripe_event"),
        provider_event_id=event_id,
        event_type=event_type[:128],
        payload_hash=payload_hash,
        provider_created_at=provider_created,
    )
    if not existing:
        db.add(ledger)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            concurrent = db.scalar(
                select(BillingWebhookEvent).where(BillingWebhookEvent.provider_event_id == event_id).with_for_update()
            )
            if not concurrent:
                raise
            if concurrent.payload_hash != payload_hash:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stripe event replay payload mismatch")
            if concurrent.status == "processed":
                return "duplicate"
            ledger = concurrent
    ledger.status = "processing"
    ledger.error_code = None
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    obj = data.get("object") if isinstance(data.get("object"), dict) else {}
    try:
        if event_type in {"checkout.session.completed", "checkout.session.expired"}:
            account = _account_for_event(db, obj)
            if account:
                attempt = _checkout_attempt_for_event(db, account, obj)
                if not attempt:
                    ledger.error_code = "checkout_attempt_mismatch"
                    record_product_event(db, account.owner_email, "billing_conflict", "checkout_webhook", mode="stripe")
                    ledger.status = "processed"
                    ledger.processed_at = utcnow()
                    db.commit()
                    return "checkout_mismatch"
                if attempt.status not in {"creating", "open"}:
                    ledger.error_code = "checkout_attempt_terminal"
                    record_product_event(db, account.owner_email, "billing_conflict", "checkout_webhook", mode="stripe")
                    ledger.status = "processed"
                    ledger.processed_at = utcnow()
                    db.commit()
                    return "checkout_mismatch"
                attempt.status = "completed" if event_type == "checkout.session.completed" else "expired"
                attempt.checkout_url = None
                attempt.updated_at = utcnow()
                if event_type == "checkout.session.completed":
                    customer = obj.get("customer")
                    subscription = obj.get("subscription")
                    customer_conflict = (
                        isinstance(customer, str)
                        and bool(account.provider_customer_id)
                        and account.provider_customer_id != customer
                    )
                    subscription_conflict = (
                        isinstance(subscription, str)
                        and bool(account.provider_subscription_id)
                        and account.provider_subscription_id != subscription
                        and account.subscription_status not in REPLACEABLE_SUBSCRIPTION_STATUSES
                    )
                    if customer_conflict or subscription_conflict:
                        attempt.status = "conflict"
                        ledger.error_code = "customer_conflict" if customer_conflict else "subscription_conflict"
                        record_product_event(
                            db,
                            account.owner_email,
                            "billing_conflict",
                            "checkout_webhook",
                            mode="stripe",
                        )
                    else:
                        if isinstance(customer, str):
                            account.provider_customer_id = customer
                        if isinstance(subscription, str):
                            account.provider_subscription_id = subscription
                        account.provider = "stripe"
                        account.updated_at = utcnow()
        elif event_type in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"}:
            account = _account_for_event(db, obj)
            if account:
                subscription_id = obj.get("id")
                customer_id = obj.get("customer")
                subscription_status = obj.get("status") if isinstance(obj.get("status"), str) else "unknown"
                event_rank = _subscription_event_rank(event_type, subscription_status)
                if account.last_provider_event_created and provider_created and (
                    provider_created < account.last_provider_event_created
                    or (
                        provider_created == account.last_provider_event_created
                        and event_rank <= account.last_provider_event_rank
                    )
                ):
                    ledger.status = "processed"
                    ledger.processed_at = utcnow()
                    db.commit()
                    return "stale"
                metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
                if (
                    isinstance(customer_id, str)
                    and account.provider_customer_id
                    and account.provider_customer_id != customer_id
                ):
                    ledger.error_code = "customer_binding_mismatch"
                    record_product_event(db, account.owner_email, "billing_conflict", "subscription_webhook", mode="stripe")
                    ledger.status = "processed"
                    ledger.processed_at = utcnow()
                    db.commit()
                    return "subscription_mismatch"
                trusted_binding = (
                    isinstance(subscription_id, str)
                    and (
                        account.provider_subscription_id == subscription_id
                        or metadata.get("billing_account_id") == account.id
                    )
                )
                if not trusted_binding:
                    ledger.error_code = "subscription_binding_mismatch"
                    record_product_event(
                        db,
                        account.owner_email,
                        "billing_conflict",
                        "subscription_webhook",
                        mode="stripe",
                    )
                    ledger.status = "processed"
                    ledger.processed_at = utcnow()
                    db.commit()
                    return "subscription_mismatch"
                prices = _subscription_price_ids(obj)
                approved_price = get_settings().stripe_pro_monthly_price_id in prices
                subscription_conflict = (
                    isinstance(subscription_id, str)
                    and bool(account.provider_subscription_id)
                    and account.provider_subscription_id != subscription_id
                    and account.subscription_status not in REPLACEABLE_SUBSCRIPTION_STATUSES
                )
                if subscription_conflict:
                    ledger.error_code = "subscription_mismatch"
                    record_product_event(
                        db,
                        account.owner_email,
                        "billing_conflict",
                        "subscription_webhook",
                        mode="stripe",
                    )
                    ledger.status = "processed"
                    ledger.processed_at = utcnow()
                    db.commit()
                    return "subscription_mismatch"
                if isinstance(subscription_id, str):
                    account.provider_subscription_id = subscription_id
                if isinstance(customer_id, str):
                    account.provider_customer_id = customer_id
                account.provider = "stripe"
                account.provider_price_id = (
                    get_settings().stripe_pro_monthly_price_id
                    if approved_price and event_type != "customer.subscription.deleted"
                    else None
                )
                previous_status = account.subscription_status
                account.subscription_status = "canceled" if event_type == "customer.subscription.deleted" else subscription_status
                account.current_period_end = _subscription_period_end(obj)
                account.cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
                if approved_price and subscription_status in ACTIVE_SUBSCRIPTION_STATUSES and event_type != "customer.subscription.deleted":
                    account.plan_key = "pro"
                    account.grace_until = None
                elif approved_price and subscription_status == "past_due" and event_type != "customer.subscription.deleted":
                    if previous_status != "past_due" or not account.grace_until:
                        account.grace_until = utcnow() + timedelta(days=get_settings().billing_past_due_grace_days)
                    account.plan_key = "pro" if account.grace_until > utcnow() else "free"
                else:
                    account.plan_key = "free"
                    account.grace_until = None
                account.plan_source = "stripe"
                account.last_provider_event_created = provider_created or utcnow()
                account.last_provider_event_rank = event_rank
                account.updated_at = utcnow()
                if account.plan_key == "free" and account.subscription_status in REPLACEABLE_SUBSCRIPTION_STATUSES:
                    completed_attempt = db.scalar(
                        select(BillingCheckoutAttempt)
                        .where(
                            BillingCheckoutAttempt.billing_account_id == account.id,
                            BillingCheckoutAttempt.status == "completed",
                        )
                        .order_by(BillingCheckoutAttempt.created_at.desc())
                        .limit(1)
                        .with_for_update()
                    )
                    if completed_attempt:
                        completed_attempt.status = "closed"
                        completed_attempt.updated_at = utcnow()
                record_product_event(
                    db,
                    account.owner_email,
                    "plan_changed",
                    "stripe_webhook",
                    mode="stripe",
                    targetPlan=account.plan_key,
                )
        elif event_type in {"invoice.paid", "invoice.payment_failed"}:
            # Invoice events are deliberately informational. They can arrive after
            # cancellation or belong to another subscription on the same customer.
            # Only a price-validated subscription event may grant or revoke access.
            pass
        ledger.status = "processed"
        ledger.processed_at = utcnow()
        db.commit()
        return "processed"
    except Exception:
        db.rollback()
        failed = db.scalar(select(BillingWebhookEvent).where(BillingWebhookEvent.provider_event_id == event_id))
        if not failed:
            failed = BillingWebhookEvent(
                id=_id("stripe_event"),
                provider_event_id=event_id,
                event_type=event_type[:128],
                payload_hash=payload_hash,
                provider_created_at=provider_created,
            )
            db.add(failed)
        failed.status = "failed"
        failed.error_code = "processing_failed"
        failed.processed_at = utcnow()
        db.commit()
        raise
