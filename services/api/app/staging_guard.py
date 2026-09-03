"""Fail-closed policy for the credential-free, loopback-only rehearsal environment."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.engine import make_url

if TYPE_CHECKING:
    from .config import Settings

STAGING_ROOT = Path(__file__).resolve().parents[3] / ".staging"
WEB_ORIGIN = "http://127.0.0.1:3100"
BASE_PATH = "/academic-writing-agent"
API_ORIGIN = "http://127.0.0.1:8100"


def inside_staging(path: Path) -> bool:
    resolved = path.resolve()
    root = STAGING_ROOT.resolve()
    return (root == Path(__file__).resolve().parents[3] / ".staging"
            and path.is_absolute() and resolved != root and resolved.is_relative_to(root))


def validate_local_staging(settings: Settings) -> None:
    # Never include the offending value: it might be a production secret/URL.
    if settings.host != "127.0.0.1" or settings.port != 8100:
        raise RuntimeError("Local staging must listen on 127.0.0.1:8100")
    if settings.allowed_origins != (WEB_ORIGIN,) or settings.billing_app_url != WEB_ORIGIN + BASE_PATH:
        raise RuntimeError("Local staging requires its dedicated loopback web origin")
    try:
        url = make_url(settings.database_url)
        safe_database = url.drivername == "sqlite" and not url.query and bool(url.database) and inside_staging(Path(url.database))
    except Exception:
        safe_database = False
    if not safe_database:
        raise RuntimeError("Local staging requires an isolated absolute SQLite path")
    if settings.object_storage_mode != "local" or not inside_staging(settings.object_storage_dir):
        raise RuntimeError("Local staging requires isolated local object storage")
    if settings.job_mode != "eager" or settings.redis_url:
        raise RuntimeError("Local staging must not connect to a shared queue")
    if settings.detector_mode != "mock" or settings.rewrite_mode != "mock":
        raise RuntimeError("Local staging permits only Mock providers")
    if settings.pangram_paid_calls_enabled or settings.detector_data_processing_acknowledged:
        raise RuntimeError("Local staging cannot enable paid detection or data submission")
    if settings.billing_mode not in {"test", "disabled"}:
        raise RuntimeError("Local staging permits only simulated or disabled billing")
    if any((settings.pangram_api_key, settings.deepseek_api_key, settings.stripe_secret_key,
            settings.stripe_webhook_secret, settings.stripe_pro_monthly_price_id,
            settings.s3_access_key_id, settings.s3_secret_access_key, settings.s3_endpoint_url,
            settings.owner_totp_secret)):
        raise RuntimeError("Local staging must not receive external service credentials")
    if settings.owner_email != "owner@staging.paperlight.local" or settings.require_totp or settings.trust_proxy:
        raise RuntimeError("Local staging requires its separate local-only owner configuration")
