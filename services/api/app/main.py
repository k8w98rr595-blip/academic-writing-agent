from __future__ import annotations

import json
import re
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db, init_db, session_scope
from .documents import DOCX_MIME, build_docx, extract_docx_text, validate_docx_upload
from .models import AnalysisRun, Document, DocumentVersion, JobRecord, PatchRecord, RewriteSession, SessionRecord, utcnow
from .providers import propose_rewrite, run_detection
from .request_limits import RequestBodyLimitMiddleware
from .schemas import (
    DocumentUpdateRequest,
    LoginRequest,
    LoginResponse,
    PatchDecisionRequest,
    RestoreVersionRequest,
    RewriteMessageRequest,
    RewriteSessionRequest,
)
from .security import audit, client_key, create_session, current_owner, login_limiter, token_hash, validate_owner_credentials
from .service import (
    add_risk_comparison,
    cleanup_expired_documents,
    create_document_record,
    create_job,
    create_version,
    delete_document_tree,
    document_payload,
    get_owned_document,
    get_version,
    new_id,
)
from .storage import get_object_storage
from .text import assert_protected_equal, paragraphs_from_text, validate_english_coursework, validate_paragraphs, word_count


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with session_scope() as db:
        cleanup_expired_documents(db)
    yield


settings = get_settings()
app = FastAPI(title="Paperlight API", version="0.1.0", lifespan=lifespan, docs_url=None if settings.is_production else "/api/docs")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["Content-Disposition", "X-Request-ID"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    request_id = request.headers.get("x-request-id", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", request_id):
        request_id = secrets.token_urlsafe(12)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/v1") else "no-cache"
    return response


# Register last so this pure-ASGI guard remains outside BaseHTTPMiddleware and
# counts streamed chunks before request bodies can be buffered or parsed.
app.add_middleware(
    RequestBodyLimitMiddleware,
    max_bytes=6 * 1024 * 1024,
    allowed_origins=tuple(settings.allowed_origins),
    is_production=settings.is_production,
)


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "service": "paperlight-api",
        "providerMode": {"detector": settings.detector_mode, "rewrite": settings.rewrite_mode},
    }


@app.get("/api/v1/auth/status")
def auth_status() -> dict:
    return {"configured": bool(settings.owner_password_hash and (settings.owner_totp_secret or not settings.require_totp)), "requiresTotp": settings.require_totp}


@app.post("/api/v1/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    key = client_key(request)
    if not login_limiter.allow(key):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many login attempts")
    if not validate_owner_credentials(payload.email, payload.password, payload.totp_code):
        audit(db, "anonymous", "auth.failure", ipHash=token_hash(key)[:16])
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid owner credentials")
    session_token, expires_at = create_session(db, settings.owner_email)
    audit(db, settings.owner_email, "auth.login")
    db.commit()
    return LoginResponse(session_token=session_token, expires_at=expires_at.isoformat(), owner_email=settings.owner_email)


@app.post("/api/v1/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    authorization: str | None = Header(default=None),
    owner: str = Depends(current_owner),
    db: Session = Depends(get_db),
):
    if authorization:
        db.execute(delete(SessionRecord).where(SessionRecord.token_hash == token_hash(authorization.removeprefix("Bearer ").strip())))
    audit(db, owner, "auth.logout")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/v1/documents")
def list_documents(owner: str = Depends(current_owner), db: Session = Depends(get_db)):
    cleanup_expired_documents(db)
    documents = list(db.scalars(select(Document).where(Document.owner_email == owner).order_by(Document.updated_at.desc()).limit(50)))
    db.commit()
    return {
        "documents": [
            {"id": item.id, "title": item.title, "updatedAt": item.updated_at.isoformat(), "expiresAt": item.expires_at.isoformat()}
            for item in documents
        ]
    }


@app.post("/api/v1/documents", status_code=status.HTTP_201_CREATED)
async def create_document(
    title: str = Form(default="Untitled coursework"),
    text: str = Form(default=""),
    file: UploadFile | None = File(default=None),
    owner: str = Depends(current_owner),
    db: Session = Depends(get_db),
):
    if len(title.strip()) < 2 or len(title) > 180:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid document title")
    source = "text"
    original_payload: bytes | None = None
    if file:
        original_payload = await file.read(5 * 1024 * 1024 + 1)
        validate_docx_upload(file.filename or "", file.content_type or "", original_payload)
        text = extract_docx_text(original_payload)
        source = "docx"
    normalized_count = validate_english_coursework(text)
    paragraphs = paragraphs_from_text(text)
    document = create_document_record(db, owner, title.strip(), paragraphs, normalized_count, source)
    db.flush()
    if original_payload:
        get_object_storage().put(f"documents/{document.id}/original.docx", original_payload)
    audit(db, owner, "document.created", document.id, source=source, wordCount=normalized_count)
    db.commit()
    return {"document": document_payload(db, document)}


@app.get("/api/v1/documents/{document_id}")
def read_document(document_id: str, owner: str = Depends(current_owner), db: Session = Depends(get_db)):
    document = get_owned_document(db, owner, document_id)
    return {"document": document_payload(db, document)}


@app.patch("/api/v1/documents/{document_id}")
def update_document(
    document_id: str,
    payload: DocumentUpdateRequest,
    owner: str = Depends(current_owner),
    db: Session = Depends(get_db),
):
    document = get_owned_document(db, owner, document_id)
    if document.current_version_id != payload.base_version_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Document changed; reload before saving")
    paragraphs = [{"id": row.id, "text": row.text.strip()} for row in payload.paragraphs]
    count = validate_paragraphs(paragraphs)
    create_version(db, document, paragraphs, count, "manual")
    audit(db, owner, "document.version", document.id, source="manual", wordCount=count)
    db.commit()
    return {"document": document_payload(db, document)}


@app.post("/api/v1/documents/{document_id}/versions/{version_id}/restore")
def restore_document_version(
    document_id: str,
    version_id: str,
    payload: RestoreVersionRequest,
    owner: str = Depends(current_owner),
    db: Session = Depends(get_db),
):
    document = get_owned_document(db, owner, document_id)
    if document.current_version_id != payload.expected_current_version_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Document changed; reload before restoring")
    target = get_version(db, document, version_id)
    create_version(db, document, target.paragraphs, target.word_count, "restore")
    audit(db, owner, "document.version", document.id, source="restore", restoredFrom=target.id)
    db.commit()
    return {"document": document_payload(db, document)}


@app.post("/api/v1/documents/{document_id}/analyses", status_code=status.HTTP_201_CREATED)
async def analyze_document(document_id: str, owner: str = Depends(current_owner), db: Session = Depends(get_db)):
    document = get_owned_document(db, owner, document_id)
    version = get_version(db, document)
    job = create_job(db, owner, document.id, "analysis")
    run = AnalysisRun(id=new_id("analysis"), document_id=document.id, version_id=version.id, status="running", provider_mode=settings.detector_mode)
    db.add(run)
    if settings.job_mode == "celery":
        run.status = "queued"
        job.status = "queued"
        db.commit()
        from services.worker.celery_app import run_analysis_job

        run_analysis_job.delay(job.id, run.id)
        audit(db, owner, "analysis.queued", document.id, analysisId=run.id, providerMode=settings.detector_mode)
        db.commit()
        return {"jobId": job.id, "analysis": document_payload(db, document)["analysis"]}
    db.commit()
    try:
        result = await run_detection(
            version.paragraphs,
            idempotency_key=run.id,
            analyzed_version_id=version.id,
        )
        add_risk_comparison(db, run, result)
        run.status = "completed"
        run.result = result
        run.completed_at = utcnow()
        job.status = "completed"
        job.result_ref = run.id
        job.updated_at = utcnow()
        audit(db, owner, "analysis.complete", document.id, analysisId=run.id, providerMode=settings.detector_mode)
        db.commit()
    except HTTPException:
        run.status = "failed"
        run.error_code = "PROVIDER_FAILED"
        job.status = "failed"
        job.error_code = "PROVIDER_FAILED"
        job.updated_at = utcnow()
        db.commit()
        raise
    return {"jobId": job.id, "analysis": document_payload(db, document)["analysis"]}


@app.post("/api/v1/documents/{document_id}/rewrite-sessions", status_code=status.HTTP_201_CREATED)
def create_rewrite_session(
    document_id: str,
    payload: RewriteSessionRequest,
    owner: str = Depends(current_owner),
    db: Session = Depends(get_db),
):
    document = get_owned_document(db, owner, document_id)
    if document.current_version_id != payload.version_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Rewrite session must use the current version")
    session = RewriteSession(id=new_id("rewrite"), document_id=document.id, version_id=payload.version_id)
    db.add(session)
    audit(db, owner, "rewrite.started", document.id, rewriteSessionId=session.id)
    db.commit()
    return {"rewriteSession": {"id": session.id, "documentId": document.id, "versionId": session.version_id}}


@app.post("/api/v1/rewrite-sessions/{session_id}/messages", status_code=status.HTTP_201_CREATED)
async def rewrite_message(
    session_id: str,
    payload: RewriteMessageRequest,
    owner: str = Depends(current_owner),
    db: Session = Depends(get_db),
):
    rewrite = db.scalar(select(RewriteSession).where(RewriteSession.id == session_id))
    if not rewrite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rewrite session not found")
    document = get_owned_document(db, owner, rewrite.document_id)
    if document.current_version_id != rewrite.version_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Rewrite session is stale")
    version = get_version(db, document, rewrite.version_id)
    paragraph = next((item for item in version.paragraphs if item["id"] == payload.paragraph_id), None)
    if not paragraph:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paragraph not found")
    if payload.selected_text and paragraph["text"].count(payload.selected_text) != 1:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Selected text must occur exactly once")
    proposal = await propose_rewrite(payload.instruction, payload.paragraph_id, paragraph["text"], payload.selected_text)
    if proposal["revisedText"] == proposal["originalText"]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="No safe automatic change was found for this passage")
    patch = PatchRecord(
        id=new_id("patch"),
        rewrite_session_id=rewrite.id,
        document_id=document.id,
        base_version_id=version.id,
        paragraph_id=proposal["paragraphId"],
        original_text=proposal["originalText"],
        revised_text=proposal["revisedText"],
        reason=proposal["reason"],
        protected_status=proposal["protectedStatus"],
    )
    db.add(patch)
    audit(
        db,
        owner,
        "patch.proposed",
        document.id,
        patchId=patch.id,
        mock=proposal["isMock"],
        provider=proposal["provider"],
        model=proposal["modelVersion"],
        validatorModel=proposal["validatorModelVersion"],
    )
    db.commit()
    return {
        "patch": {
            "id": patch.id,
            "baseVersionId": patch.base_version_id,
            "paragraphId": patch.paragraph_id,
            "originalText": patch.original_text,
            "revisedText": patch.revised_text,
            "reason": patch.reason,
            "protectedStatus": patch.protected_status,
            "status": patch.status,
            "isMock": proposal["isMock"],
            "provider": proposal["provider"],
            "modelVersion": proposal["modelVersion"],
            "validatorModelVersion": proposal["validatorModelVersion"],
        }
    }


@app.post("/api/v1/patches/{patch_id}/accept")
def accept_patch(
    patch_id: str,
    payload: PatchDecisionRequest,
    owner: str = Depends(current_owner),
    db: Session = Depends(get_db),
):
    patch = db.scalar(select(PatchRecord).where(PatchRecord.id == patch_id))
    if not patch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patch not found")
    document = get_owned_document(db, owner, patch.document_id)
    if patch.status != "pending" or patch.base_version_id != payload.expected_base_version_id or document.current_version_id != patch.base_version_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Patch is stale or already decided")
    version = get_version(db, document, patch.base_version_id)
    paragraphs = [dict(item) for item in version.paragraphs]
    paragraph = next((item for item in paragraphs if item["id"] == patch.paragraph_id), None)
    if not paragraph or paragraph["text"].count(patch.original_text) != 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Patch no longer matches the document")
    assert_protected_equal(patch.original_text, patch.revised_text)
    paragraph["text"] = paragraph["text"].replace(patch.original_text, patch.revised_text, 1)
    count = validate_paragraphs(paragraphs)
    create_version(db, document, paragraphs, count, "agent-patch")
    patch.status = "accepted"
    patch.decided_at = utcnow()
    audit(db, owner, "patch.accepted", document.id, patchId=patch.id)
    db.commit()
    return {"document": document_payload(db, document)}


@app.post("/api/v1/patches/{patch_id}/reject")
def reject_patch(
    patch_id: str,
    payload: PatchDecisionRequest,
    owner: str = Depends(current_owner),
    db: Session = Depends(get_db),
):
    patch = db.scalar(select(PatchRecord).where(PatchRecord.id == patch_id))
    if not patch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patch not found")
    document = get_owned_document(db, owner, patch.document_id)
    if patch.status != "pending" or patch.base_version_id != payload.expected_base_version_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Patch is stale or already decided")
    patch.status = "rejected"
    patch.decided_at = utcnow()
    audit(db, owner, "patch.rejected", document.id, patchId=patch.id)
    db.commit()
    return {"patch": {"id": patch.id, "status": patch.status}}


@app.post("/api/v1/documents/{document_id}/exports")
def export_document(document_id: str, owner: str = Depends(current_owner), db: Session = Depends(get_db)):
    document = get_owned_document(db, owner, document_id)
    version = get_version(db, document)
    payload = build_docx(document.title, version.paragraphs, version.version_number)
    safe_filename = re.sub(r"[^A-Za-z0-9_-]+", "-", document.title).strip("-")[:60] or "paperlight-document"
    audit(db, owner, "document.exported", document.id, versionId=version.id)
    db.commit()
    return StreamingResponse(
        iter([payload]),
        media_type=DOCX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}-v{version.version_number}.docx"'},
    )


@app.delete("/api/v1/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str, owner: str = Depends(current_owner), db: Session = Depends(get_db)):
    document = get_owned_document(db, owner, document_id)
    audit(db, owner, "document.deleted", document.id)
    db.flush()
    delete_document_tree(db, document)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/v1/jobs/{job_id}/events")
def job_events(job_id: str, owner: str = Depends(current_owner), db: Session = Depends(get_db)):
    job = db.scalar(select(JobRecord).where(JobRecord.id == job_id, JobRecord.owner_email == owner))
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    event = json.dumps({"id": job.id, "status": job.status, "resultRef": job.result_ref, "errorCode": job.error_code})
    return StreamingResponse(iter([f"event: job\ndata: {event}\n\n"]), media_type="text/event-stream")
