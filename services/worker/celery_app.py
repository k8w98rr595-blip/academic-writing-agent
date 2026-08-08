from __future__ import annotations

import asyncio

from celery import Celery

from services.api.app.config import get_settings
from services.api.app.database import session_scope
from services.api.app.models import AnalysisRun, JobRecord, utcnow
from services.api.app.providers import detection_content_fingerprint, run_detection
from services.api.app.provider_usage import (
    cancel_unused_reservations,
    claim_provider_call,
    cleanup_provider_usage_events,
    finalize_provider_call,
)
from services.api.app.service import add_risk_comparison, get_version
from services.api.app.service import cleanup_expired_documents
from services.api.app.models import Document


settings = get_settings()
celery = Celery("paperlight", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(task_serializer="json", result_serializer="json", accept_content=["json"], task_acks_late=True)
celery.conf.beat_schedule = {
    "delete-expired-documents-hourly": {
        "task": "paperlight.cleanup_expired_documents",
        "schedule": 3600.0,
    }
}


@celery.task(name="paperlight.analysis")
def run_analysis_job(job_id: str, analysis_id: str, usage_reservation_id: str = "") -> str:
    with session_scope() as db:
        job = db.get(JobRecord, job_id)
        analysis = db.get(AnalysisRun, analysis_id)
        if not job or not analysis or job.status not in {"queued", "running"}:
            if usage_reservation_id:
                cancel_unused_reservations([usage_reservation_id])
            return "ignored"
        document = db.get(Document, analysis.document_id)
        if not document:
            job.status = "cancelled"
            if usage_reservation_id:
                cancel_unused_reservations([usage_reservation_id])
            return "cancelled"
        version = get_version(db, document, analysis.version_id)
        if usage_reservation_id and not claim_provider_call(usage_reservation_id):
            finalize_provider_call(
                usage_reservation_id,
                final_status="outcome_unknown",
                error_code="duplicate_worker_delivery",
            )
            analysis.status = "failed"
            analysis.error_code = "PROVIDER_OUTCOME_UNKNOWN"
            job.status = "failed"
            job.error_code = "PROVIDER_OUTCOME_UNKNOWN"
            job.updated_at = utcnow()
            return "duplicate_blocked"
        job.status = "running"
        analysis.status = "running"
        try:
            result = asyncio.run(
                run_detection(
                    version.paragraphs,
                    idempotency_key=detection_content_fingerprint(version.paragraphs, settings.pangram_model),
                    analyzed_version_id=version.id,
                )
            )
        except Exception:
            if usage_reservation_id:
                finalize_provider_call(
                    usage_reservation_id,
                    final_status="outcome_unknown",
                    error_code="worker_interrupted",
                )
            analysis.status = "failed"
            analysis.error_code = "PROVIDER_FAILED"
            job.status = "failed"
            job.error_code = "PROVIDER_FAILED"
            job.updated_at = utcnow()
            return "failed"
        if usage_reservation_id:
            error_code = (result.get("error") or {}).get("code") if isinstance(result.get("error"), dict) else None
            final_status = "success" if result.get("status") == "success" else (
                "outcome_unknown" if error_code == "submission_outcome_unknown" else "failed"
            )
            finalize_provider_call(
                usage_reservation_id,
                final_status=final_status,
                error_code=error_code,
                latency_ms=result.get("latencyMs"),
                input_units=result.get("qualifyingWords"),
                model_version=result.get("providerModelVersion"),
            )
        add_risk_comparison(db, analysis, result)
        analysis.result = result
        analysis.status = "completed"
        analysis.completed_at = utcnow()
        job.status = "completed"
        job.result_ref = analysis.id
        job.updated_at = utcnow()
        return analysis.id


@celery.task(name="paperlight.cleanup_expired_documents")
def cleanup_expired_documents_job() -> int:
    with session_scope() as db:
        deleted_documents = cleanup_expired_documents(db)
        cleanup_provider_usage_events(db)
        return deleted_documents
