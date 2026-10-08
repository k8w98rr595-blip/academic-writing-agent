"""Student identity and public-launch controls; no external identity service."""
from __future__ import annotations

import hmac
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db, session_scope
from .models import AuditEvent, BillingAccount, BillingCheckoutAttempt, BillingProductEvent, Document, ProductUsageReservation, SessionRecord, UserAccount
from .security import (SlidingWindowLimiter, audit, client_key, create_session, current_owner,
                       hash_password, session_identity, token_hash, verify_password)
from .service import delete_document_tree, new_id

TERMS_VERSION = "2026-10-08"
router = APIRouter(prefix="/api/v1")
account_limiter = SlidingWindowLimiter(5, 3600)
# Unknown usernames use a real dummy verifier to avoid a fast password check.
DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{2,31}$")
    password: str = Field(min_length=12, max_length=256)
    accepted_terms_version: str
    adult_confirmed: bool
    cloud_storage_consent: bool


class RecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=32)
    recovery_key: str = Field(min_length=20, max_length=128)
    new_password: str = Field(min_length=12, max_length=256)


class PasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=12, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class DeleteAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=12, max_length=256)


class ProviderConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted_terms_version: str
    consent: bool


def limit_account_action(request: Request, action: str, limit: int = 10) -> None:
    settings = get_settings()
    key = token_hash(f"{action}:{client_key(request)}")
    if settings.is_production and (settings.public_registration_enabled or settings.public_ai_enabled):
        import redis
        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
        try:
            # Increment and expiry are atomic; only a hash of the address is kept.
            count = client.eval("local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],3600) end; return n", 1, f"paperlight:auth:{key}")
        except redis.RedisError:
            raise HTTPException(503, "账号服务暂时不可用，请稍后重试") from None
        finally:
            client.close()
        if int(count) > limit:
            raise HTTPException(429, "操作过于频繁，请稍后再试")
    elif not account_limiter.allow(key):
        raise HTTPException(429, "操作过于频繁，请稍后再试")


def member_credentials(db: Session, username: str, password: str) -> str | None:
    user = db.scalar(select(UserAccount).where(UserAccount.username == username.strip().lower()))
    valid = verify_password(user.password_hash if user else DUMMY_HASH, password)
    return user.principal if user and valid else None


def require_public_ai(principal: str, mode: str) -> None:
    settings = get_settings()
    if principal != settings.owner_email and mode != "mock" and not settings.public_ai_enabled:
        raise HTTPException(403, detail={"code": "public_ai_not_enabled", "message": "公众真实 AI 服务尚未开放；可继续编辑、保存和导出，或使用本地写作自检。"})
    if principal != settings.owner_email and mode != "mock":
        with session_scope() as db:
            user = db.scalar(select(UserAccount).where(UserAccount.principal == principal))
            if not user or not user.provider_consent or user.terms_version != TERMS_VERSION:
                raise HTTPException(403, "请先在账号设置中单独确认供应商文稿处理说明")


@router.get("/public/config")
def public_config():
    settings = get_settings()
    return {"registrationEnabled": settings.public_registration_enabled, "publicAiEnabled": settings.public_ai_enabled,
            "termsVersion": TERMS_VERSION, "operator": settings.operator_name, "supportEmail": settings.support_email,
            "localExperienceAvailable": True, "languages": ["zh", "en"], "retentionDays": settings.retention_days}


@router.post("/auth/register", status_code=201)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    if not get_settings().public_registration_enabled:
        raise HTTPException(403, "云端注册暂未开放；可使用无需上传文稿的本地体验")
    limit_account_action(request, "register", 5)
    if payload.accepted_terms_version != TERMS_VERSION or not payload.adult_confirmed or not payload.cloud_storage_consent:
        raise HTTPException(422, "请确认已满18岁，并阅读服务说明和境外云端存储提示")
    username = payload.username.lower()
    if username in {"owner", "admin", "paperlight", "support"}:
        raise HTTPException(409, "用户名不可用")
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(506170014293216800)"))
    if (db.scalar(select(func.count(UserAccount.id))) or 0) >= get_settings().public_max_accounts:
        raise HTTPException(503, "当前试用名额已满，请稍后再试")
    recovery = secrets.token_urlsafe(32)
    user_id = new_id("user")
    user = UserAccount(id=user_id, username=username, principal=f"{user_id}@paperlight.invalid",
                       password_hash=hash_password(payload.password), recovery_hash=token_hash(recovery), terms_version=TERMS_VERSION,
                       provider_consent=False)
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "用户名不可用") from None
    token, expiry = create_session(db, user.principal)
    audit(db, user.principal, "account.registered")
    db.commit()
    return {"session_token": token, "expires_at": expiry.isoformat(), "username": username, "recovery_key": recovery}


@router.post("/auth/recover")
def recover(payload: RecoveryRequest, request: Request, db: Session = Depends(get_db)):
    limit_account_action(request, "recover", 5)
    user = db.scalar(select(UserAccount).where(UserAccount.username == payload.username.strip().lower()).with_for_update())
    if not user or not hmac.compare_digest(user.recovery_hash, token_hash(payload.recovery_key)):
        raise HTTPException(401, "用户名或恢复码无效")
    identity = session_identity(db, user.principal)
    recovery = secrets.token_urlsafe(32)
    user.password_hash = hash_password(payload.new_password)
    user.recovery_hash = token_hash(recovery)
    db.execute(delete(SessionRecord).where(SessionRecord.owner_email == identity))
    audit(db, user.principal, "account.recovered")
    db.commit()
    return {"recovery_key": recovery, "message": "密码已更新，旧会话和旧恢复码已失效，请重新登录"}


@router.get("/account")
def account(principal: str = Depends(current_owner), db: Session = Depends(get_db)):
    if principal == get_settings().owner_email:
        return {"role": "owner", "username": "所有者", "canUseRealAi": True}
    user = db.scalar(select(UserAccount).where(UserAccount.principal == principal))
    return {"role": "student", "username": user.username, "canUseRealAi": get_settings().public_ai_enabled,
            "providerConsent": user.provider_consent, "termsVersion": TERMS_VERSION}


@router.post("/account/provider-consent")
def provider_consent(payload: ProviderConsentRequest, principal: str = Depends(current_owner), db: Session = Depends(get_db)):
    user = db.scalar(select(UserAccount).where(UserAccount.principal == principal).with_for_update())
    if not user:
        raise HTTPException(403, "此设置仅适用于学生账号")
    if payload.consent and (not get_settings().public_ai_enabled or payload.accepted_terms_version != TERMS_VERSION):
        raise HTTPException(403, "公众真实 AI 服务尚未开放或说明版本已更新")
    user.provider_consent = payload.consent
    if payload.consent:
        user.terms_version = TERMS_VERSION
    audit(db, principal, "account.provider_consent.granted" if payload.consent else "account.provider_consent.revoked")
    db.commit()
    return {"providerConsent": user.provider_consent}


@router.post("/account/password")
def change_password(payload: PasswordRequest, principal: str = Depends(current_owner), db: Session = Depends(get_db)):
    user = db.scalar(select(UserAccount).where(UserAccount.principal == principal).with_for_update())
    if not user or not verify_password(user.password_hash, payload.current_password):
        raise HTTPException(403, "请使用学生账号的当前密码；所有者凭据仍由部署配置管理")
    identity = session_identity(db, principal)
    user.password_hash = hash_password(payload.new_password)
    db.execute(delete(SessionRecord).where(SessionRecord.owner_email == identity))
    audit(db, principal, "account.password_changed")
    db.commit()
    return {"message": "密码已更新，请重新登录"}


@router.delete("/account", status_code=204)
def delete_account(payload: DeleteAccountRequest, principal: str = Depends(current_owner), db: Session = Depends(get_db)):
    user = db.scalar(select(UserAccount).where(UserAccount.principal == principal).with_for_update())
    if not user or not verify_password(user.password_hash, payload.password):
        raise HTTPException(403, "账号密码无效；所有者账号不能在此删除")
    billing = db.scalar(select(BillingAccount).where(BillingAccount.owner_email == principal))
    if billing and billing.subscription_status in {"active", "trialing", "past_due"}:
        raise HTTPException(409, "请先终止订阅，再注销账号")
    for document in list(db.scalars(select(Document).where(Document.owner_email == principal))):
        delete_document_tree(db, document)
    db.execute(delete(SessionRecord).where(SessionRecord.owner_email == session_identity(db, principal)))
    db.execute(delete(AuditEvent).where(AuditEvent.actor == principal))
    # No customer billing existed: discard free-plan metadata too. Do not erase
    # real payment reconciliation records through a generic account-delete call.
    has_checkout = billing and db.scalar(select(BillingCheckoutAttempt.id).where(BillingCheckoutAttempt.billing_account_id == billing.id).limit(1))
    if billing and not billing.provider_customer_id and not billing.provider_subscription_id and not has_checkout:
        db.execute(delete(ProductUsageReservation).where(ProductUsageReservation.owner_email == principal))
        db.execute(delete(BillingProductEvent).where(BillingProductEvent.owner_email == principal))
        db.delete(billing)
    db.delete(user)
    db.commit()
