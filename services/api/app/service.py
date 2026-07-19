from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import AnalysisRun, AuditEvent, Document, DocumentVersion, JobRecord, PatchRecord, RewriteSession, utcnow
from .storage import get_object_storage


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


def get_owned_document(db: Session, owner_email: str, document_id: str) -> Document:
    document = db.scalar(select(Document).where(Document.id == document_id, Document.owner_email == owner_email))
    if not document or document.expires_at <= utcnow():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


def get_version(db: Session, document: Document, version_id: str | None = None) -> DocumentVersion:
    target_id = version_id or document.current_version_id
    version = db.scalar(
        select(DocumentVersion).where(DocumentVersion.id == target_id, DocumentVersion.document_id == document.id)
    )
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document version not found")
    return version


def create_version(db: Session, document: Document, paragraphs: list[dict], word_count: int, source: str) -> DocumentVersion:
    current_max = db.scalar(select(func.max(DocumentVersion.version_number)).where(DocumentVersion.document_id == document.id)) or 0
    version = DocumentVersion(
        id=new_id("version"),
        document_id=document.id,
        version_number=int(current_max) + 1,
        paragraphs=paragraphs,
        word_count=word_count,
        source=source,
        parent_version_id=document.current_version_id,
    )
    db.add(version)
    document.current_version_id = version.id
    document.updated_at = utcnow()
    return version


def document_payload(db: Session, document: Document) -> dict:
    current = get_version(db, document)
    versions = list(
        db.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.version_number.desc())
            .limit(20)
        )
    )
    analysis = db.scalar(
        select(AnalysisRun)
        .where(AnalysisRun.document_id == document.id)
        .order_by(AnalysisRun.created_at.desc())
        .limit(1)
    )
    patches = list(
        db.scalars(
            select(PatchRecord)
            .where(PatchRecord.document_id == document.id)
            .order_by(PatchRecord.created_at.desc())
            .limit(30)
        )
    )
    return {
        "id": document.id,
        "title": document.title,
        "createdAt": document.created_at.isoformat(),
        "updatedAt": document.updated_at.isoformat(),
        "expiresAt": document.expires_at.isoformat(),
        "currentVersion": {
            "id": current.id,
            "number": current.version_number,
            "paragraphs": current.paragraphs,
            "wordCount": current.word_count,
            "source": current.source,
            "createdAt": current.created_at.isoformat(),
        },
        "versions": [
            {
                "id": version.id,
                "number": version.version_number,
                "wordCount": version.word_count,
                "source": version.source,
                "createdAt": version.created_at.isoformat(),
            }
            for version in versions
        ],
        "analysis": None
        if not analysis
        else {
            "id": analysis.id,
            "versionId": analysis.version_id,
            "status": analysis.status,
            "isStale": analysis.version_id != current.id,
            "result": analysis.result,
            "createdAt": analysis.created_at.isoformat(),
            "completedAt": analysis.completed_at.isoformat() if analysis.completed_at else None,
        },
        "patches": [
            {
                "id": patch.id,
                "baseVersionId": patch.base_version_id,
                "paragraphId": patch.paragraph_id,
                "originalText": patch.original_text,
                "revisedText": patch.revised_text,
                "reason": patch.reason,
                "protectedStatus": patch.protected_status,
                "status": patch.status,
                "createdAt": patch.created_at.isoformat(),
            }
            for patch in patches
        ],
    }


def add_risk_comparison(db: Session, analysis: AnalysisRun, result: dict) -> dict:
    """Attach an honest before/after comparison without mutating old analysis rows."""
    current_score = result.get("combinedRiskPercent")
    if not isinstance(current_score, (int, float)) or isinstance(current_score, bool):
        return result
    previous = db.scalar(
        select(AnalysisRun)
        .where(
            AnalysisRun.document_id == analysis.document_id,
            AnalysisRun.id != analysis.id,
            AnalysisRun.status == "completed",
        )
        .order_by(AnalysisRun.created_at.desc())
        .limit(1)
    )
    if not previous or not isinstance(previous.result, dict):
        return result
    previous_score = previous.result.get("combinedRiskPercent")
    if not isinstance(previous_score, (int, float)) or isinstance(previous_score, bool):
        # Legacy dual-provider results remain comparable only when they stored a real fused estimate.
        previous_score = previous.result.get("estimate")
    if not isinstance(previous_score, (int, float)) or isinstance(previous_score, bool):
        return result
    result["riskComparison"] = {
        "beforePercent": round(float(previous_score), 1),
        "afterPercent": round(float(current_score), 1),
        "changePercentagePoints": round(float(current_score) - float(previous_score), 1),
        "beforeAnalysisId": previous.id,
    }
    return result


def delete_document_tree(db: Session, document: Document) -> None:
    document_id = document.id
    db.execute(delete(PatchRecord).where(PatchRecord.document_id == document_id))
    db.execute(delete(RewriteSession).where(RewriteSession.document_id == document_id))
    db.execute(delete(AnalysisRun).where(AnalysisRun.document_id == document_id))
    db.execute(delete(JobRecord).where(JobRecord.document_id == document_id))
    db.execute(delete(DocumentVersion).where(DocumentVersion.document_id == document_id))
    db.delete(document)
    get_object_storage().delete_prefix(f"documents/{document_id}")


def cleanup_expired_documents(db: Session) -> int:
    expired = list(db.scalars(select(Document).where(Document.expires_at <= utcnow())))
    for document in expired:
        delete_document_tree(db, document)
    return len(expired)


def create_document_record(db: Session, owner_email: str, title: str, paragraphs: list[dict], count: int, source: str) -> Document:
    settings = get_settings()
    document = Document(
        id=new_id("document"),
        owner_email=owner_email,
        title=title[:180],
        expires_at=utcnow() + timedelta(days=settings.retention_days),
    )
    db.add(document)
    db.flush()
    create_version(db, document, paragraphs, count, source)
    return document


def create_job(db: Session, owner_email: str, document_id: str, job_type: str) -> JobRecord:
    job = JobRecord(id=new_id("job"), owner_email=owner_email, document_id=document_id, job_type=job_type, status="running")
    db.add(job)
    return job
