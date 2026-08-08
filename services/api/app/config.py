from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


if os.getenv("APP_ENV", "development").strip().lower() != "test":
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
    pangram_model: str
    pangram_paid_calls_enabled: bool
    pangram_poll_interval_seconds: float
    pangram_max_poll_seconds: int
    pangram_hourly_warning: int
    pangram_hourly_hard_limit: int
    pangram_daily_hard_limit: int
    pangram_max_concurrent_calls: int
    pangram_reservation_ttl_seconds: int
    detector_data_processing_acknowledged: bool
    deepseek_base_url: str
    deepseek_api_key: str
    deepseek_model: str
    deepseek_validator_model: str
    provider_timeout_seconds: int
    paid_call_hourly_warning: int
    paid_call_hourly_hard_limit: int
    provider_failure_breaker_threshold: int
    provider_breaker_seconds: int
    provider_usage_retention_days: int

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
        pangram_api_url=os.getenv(
            "PANGRAM_API_BASE_URL",
            os.getenv("PANGRAM_API_URL", "https://text.external-api.pangram.com"),
        ).strip(),
        pangram_api_key=os.getenv("PANGRAM_API_KEY", ""),
        pangram_model=os.getenv("PANGRAM_MODEL", "pangram-4").strip().lower(),
        pangram_paid_calls_enabled=_bool("PANGRAM_PAID_CALLS_ENABLED", False),
        pangram_poll_interval_seconds=float(os.getenv("PANGRAM_POLL_INTERVAL_SECONDS", "0.75")),
        pangram_max_poll_seconds=int(os.getenv("PANGRAM_MAX_POLL_SECONDS", "45")),
        pangram_hourly_warning=int(os.getenv("PANGRAM_HOURLY_WARNING", "1")),
        pangram_hourly_hard_limit=int(os.getenv("PANGRAM_HOURLY_HARD_LIMIT", "2")),
        pangram_daily_hard_limit=int(os.getenv("PANGRAM_DAILY_HARD_LIMIT", "4")),
        pangram_max_concurrent_calls=int(os.getenv("PANGRAM_MAX_CONCURRENT_CALLS", "1")),
        pangram_reservation_ttl_seconds=int(os.getenv("PANGRAM_RESERVATION_TTL_SECONDS", "900")),
        detector_data_processing_acknowledged=_bool("DETECTOR_DATA_PROCESSING_ACKNOWLEDGED", False),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
        deepseek_validator_model=os.getenv("DEEPSEEK_VALIDATOR_MODEL", "deepseek-v4-flash"),
        provider_timeout_seconds=int(os.getenv("PROVIDER_TIMEOUT_SECONDS", "45")),
        paid_call_hourly_warning=int(os.getenv("PAID_CALL_HOURLY_WARNING", "10")),
        paid_call_hourly_hard_limit=int(os.getenv("PAID_CALL_HOURLY_HARD_LIMIT", "20")),
        provider_failure_breaker_threshold=int(os.getenv("PROVIDER_FAILURE_BREAKER_THRESHOLD", "5")),
        provider_breaker_seconds=int(os.getenv("PROVIDER_BREAKER_SECONDS", "900")),
        provider_usage_retention_days=int(os.getenv("PROVIDER_USAGE_RETENTION_DAYS", "30")),
    )
    settings.object_storage_dir.mkdir(parents=True, exist_ok=True)
    if settings.is_production and "*" in settings.allowed_origins:
        raise RuntimeError("Production CORS must not allow every origin")
    if settings.is_production and settings.rewrite_mode == "deepseek":
        deepseek_url = urlsplit(settings.deepseek_base_url)
        if (
            deepseek_url.scheme != "https"
            or deepseek_url.hostname != "api.deepseek.com"
            or deepseek_url.port not in {None, 443}
            or deepseek_url.username
            or deepseek_url.password
            or deepseek_url.query
            or deepseek_url.fragment
            or deepseek_url.path.rstrip("/") not in {"", "/v1"}
        ):
            raise RuntimeError("Production DeepSeek base URL must use the official HTTPS API host")
        if settings.deepseek_model != "deepseek-v4-pro" or settings.deepseek_validator_model != "deepseek-v4-flash":
            raise RuntimeError("Production DeepSeek mode requires the approved V4 Pro and V4 Flash model pair")
    if settings.detector_mode not in {"mock", "pangram"}:
        raise RuntimeError("DETECTOR_MODE must be mock or pangram")
    if settings.pangram_poll_interval_seconds <= 0 or settings.pangram_max_poll_seconds <= 0:
        raise RuntimeError("Pangram polling settings must be positive")
    if settings.pangram_model != "pangram-4":
        raise RuntimeError("PANGRAM_MODEL must be pangram-4 for the current Paperlight detector")
    if not 1 <= settings.pangram_hourly_warning <= settings.pangram_hourly_hard_limit <= 100:
        raise RuntimeError("Pangram hourly warning and hard limit are invalid")
    if not settings.pangram_hourly_hard_limit <= settings.pangram_daily_hard_limit <= 1000:
        raise RuntimeError("Pangram daily hard limit is invalid")
    if not 1 <= settings.pangram_max_concurrent_calls <= 10:
        raise RuntimeError("Pangram concurrency limit is invalid")
    if not 60 <= settings.pangram_reservation_ttl_seconds <= 86400:
        raise RuntimeError("Pangram reservation TTL is invalid")
    if settings.detector_mode == "pangram":
        _require_official_endpoint(settings.pangram_api_url, "text.external-api.pangram.com", "Pangram", {""})
        if not settings.pangram_api_key:
            raise RuntimeError("Pangram mode requires PANGRAM_API_KEY")
        if not settings.detector_data_processing_acknowledged:
            raise RuntimeError("Pangram mode requires acknowledged data-processing terms")
        if not settings.pangram_paid_calls_enabled:
            raise RuntimeError("Pangram mode requires PANGRAM_PAID_CALLS_ENABLED=1")
    if not 1 <= settings.paid_call_hourly_warning <= settings.paid_call_hourly_hard_limit <= 1000:
        raise RuntimeError("Paid-call warning and hard-limit settings are invalid")
    if not 2 <= settings.provider_failure_breaker_threshold <= 100:
        raise RuntimeError("Provider failure breaker threshold is invalid")
    if not 60 <= settings.provider_breaker_seconds <= 86400:
        raise RuntimeError("Provider breaker duration is invalid")
    if not 1 <= settings.provider_usage_retention_days <= 365:
        raise RuntimeError("Provider usage retention is invalid")
    return settings


def _require_official_endpoint(value: str, hostname: str, label: str, allowed_paths: set[str]) -> None:
    parsed = urlsplit(value)
    normalized_path = parsed.path.rstrip("/")
    if (
        parsed.scheme != "https"
        or parsed.hostname != hostname
        or parsed.port not in {None, 443}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or normalized_path not in allowed_paths
    ):
        raise RuntimeError(f"Production {label} URL must use the official HTTPS API host")
