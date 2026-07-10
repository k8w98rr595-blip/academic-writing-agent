from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(".env.local")


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _origins() -> tuple[str, ...]:
    raw = os.getenv("ALLOWED_ORIGINS", "http://127.0.0.1:3000,http://localhost:3000")
    return tuple(origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip())


@dataclass(frozen=True)
class Settings:
    app_env: str
    host: str
    port: int
    database_url: str
    object_storage_mode: str
    object_storage_dir: Path
    s3_endpoint_url: str
    s3_access_key_id: str
    s3_secret_access_key: str
    s3_bucket: str
    s3_region: str
    allowed_origins: tuple[str, ...]
    session_ttl_hours: int
    retention_days: int
    owner_email: str
    owner_password_hash: str
    owner_totp_secret: str
    require_totp: bool
    cookie_secure: bool
    trust_proxy: bool
    job_mode: str
    redis_url: str
    detector_mode: str
    rewrite_mode: str
    pangram_api_url: str
    pangram_api_key: str
    copyleaks_api_url: str
    copyleaks_access_token: str
    deepseek_base_url: str
    deepseek_api_key: str
    deepseek_model: str
    deepseek_validator_model: str
    provider_timeout_seconds: int

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings(
        app_env=os.getenv("APP_ENV", "development"),
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./data/paperlight.db"),
        object_storage_mode=os.getenv("OBJECT_STORAGE_MODE", "local"),
        object_storage_dir=Path(os.getenv("OBJECT_STORAGE_DIR", "./data/objects")),
        s3_endpoint_url=os.getenv("S3_ENDPOINT_URL", ""),
        s3_access_key_id=os.getenv("S3_ACCESS_KEY_ID", ""),
        s3_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY", ""),
        s3_bucket=os.getenv("S3_BUCKET", "paperlight"),
        s3_region=os.getenv("S3_REGION", "us-east-1"),
        allowed_origins=_origins(),
        session_ttl_hours=int(os.getenv("SESSION_TTL_HOURS", "12")),
        retention_days=int(os.getenv("DOCUMENT_RETENTION_DAYS", "7")),
        owner_email=os.getenv("OWNER_EMAIL", "owner@example.com").strip().lower(),
        owner_password_hash=os.getenv("OWNER_PASSWORD_HASH", ""),
        owner_totp_secret=os.getenv("OWNER_TOTP_SECRET", ""),
        require_totp=_bool("REQUIRE_TOTP", True),
        cookie_secure=_bool("COOKIE_SECURE", False),
        trust_proxy=_bool("TRUST_PROXY", False),
        job_mode=os.getenv("JOB_MODE", "eager").strip().lower(),
        redis_url=os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"),
        detector_mode=os.getenv("DETECTOR_MODE", "mock").strip().lower(),
        rewrite_mode=os.getenv("REWRITE_MODE", "mock").strip().lower(),
        pangram_api_url=os.getenv("PANGRAM_API_URL", "https://api.pangram.com/v1/predict"),
        pangram_api_key=os.getenv("PANGRAM_API_KEY", ""),
        copyleaks_api_url=os.getenv("COPYLEAKS_API_URL", "https://api.copyleaks.com/v2/writer-detector"),
        copyleaks_access_token=os.getenv("COPYLEAKS_ACCESS_TOKEN", ""),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
        deepseek_validator_model=os.getenv("DEEPSEEK_VALIDATOR_MODEL", "deepseek-v4-flash"),
        provider_timeout_seconds=int(os.getenv("PROVIDER_TIMEOUT_SECONDS", "45")),
    )
    settings.object_storage_dir.mkdir(parents=True, exist_ok=True)
    if settings.is_production and "*" in settings.allowed_origins:
        raise RuntimeError("Production CORS must not allow every origin")
    return settings
