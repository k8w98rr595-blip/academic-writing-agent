from __future__ import annotations

import asyncio

from celery import Celery

from services.api.app.config import get_settings
from services.api.app.database import session_scope
from services.api.app.models import AnalysisRun, JobRecord, utcnow
from services.api.app.providers import run_detection
from services.api.app.service import get_version
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


@celery.task(name="paperlight.analysis", autoretry_for=(Exception,), retry_backoff=True, max_retries=2)
def run_analysis_job(job_id: str, analysis_id: str) -> str:
    with session_scope() as db:
        job = db.get(JobRecord, job_id)
        analysis = db.get(AnalysisRun, analysis_id)
        if not job or not analysis or job.status not in {"queued", "running"}:
            return "ignored"
        document = db.get(Document, analysis.document_id)
        if not document:
            job.status = "cancelled"
            return "cancelled"
        version = get_version(db, document, analysis.version_id)
        job.status = "running"
        analysis.status = "running"
        result = asyncio.run(run_detection(version.paragraphs))
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
        return cleanup_expired_documents(db)
