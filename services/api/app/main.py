from __future__ import annotations

import hashlib
import json
import re
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db, init_db, session_scope
from .documents import DOCX_MIME, build_docx, extract_docx_text, validate_docx_upload
from .models import AnalysisRun, Document, DocumentVersion, JobRecord, PatchRecord, RewriteSession, SessionRecord, utcnow
from .providers import detection_content_fingerprint, propose_first_pass_rewrites, propose_rewrite, run_detection
from .provider_usage import (
    ProviderCallSpec,
    cancel_unused_reservations,
    cleanup_provider_usage_events,
    finalize_provider_call,
    provider_usage_summary,
    reserve_provider_calls,
)
from .request_limits import RequestBodyLimitMiddleware
from .schemas import (
    DocumentUpdateRequest,
    FirstPassRewriteRequest,
    LoginRequest,
    LoginResponse,
    PatchDecisionRequest,
    ProviderUsageSummaryResponse,
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
        cleanup_provider_usage_events(db)
    yield


settings = get_settings()
MAX_AGENT_CONTEXT_CHARACTERS = 60_000
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
        "detectorProvider": {
            "provider": "Pangram" if settings.detector_mode == "pangram" else "Mock Pangram",
            "model": settings.pangram_model if settings.detector_mode == "pangram" else "mock",
            "paidCallsEnabled": settings.pangram_paid_calls_enabled if settings.detector_mode == "pangram" else False,
            "dataProcessingAcknowledged": (
                settings.detector_data_processing_acknowledged if settings.detector_mode == "pangram" else False
            ),
        },
    }


def _looks_like_heading(text: str) -> bool:
    stripped = text.strip()
    return bool(stripped) and len(stripped) < 80 and not re.search(r"[.!?]$", stripped)


def _agent_context(paragraphs: list[dict], paragraph_id: str, scope: str, confirmed: bool) -> str:
    index = next((position for position, item in enumerate(paragraphs) if item["id"] == paragraph_id), None)
    if index is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paragraph not found")
    if scope in {"selection", "paragraph"}:
        selected = [paragraphs[index]]
    elif scope == "section":
        start = index
        while start > 0 and not _looks_like_heading(paragraphs[start]["text"]):
            start -= 1
        if not _looks_like_heading(paragraphs[start]["text"]):
            start = index
        end = start + 1
        while end < len(paragraphs) and not _looks_like_heading(paragraphs[end]["text"]):
            end += 1
        selected = paragraphs[start:end]
    else:
        if not confirmed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Full-document context requires explicit confirmation",
            )
        selected = paragraphs
    context = "\n\n".join(item["text"] for item in selected)
    if len(context) > MAX_AGENT_CONTEXT_CHARACTERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Requested Agent context is too large",
        )
    return context


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


@app.get("/api/v1/provider-usage/summary", response_model=ProviderUsageSummaryResponse)
def get_provider_usage_summary(owner: str = Depends(current_owner), db: Session = Depends(get_db)):
    cleanup_provider_usage_events(db)
    summary = provider_usage_summary(db, owner)
    audit(db, owner, "provider.usage_viewed")
    db.commit()
    return summary


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
    operation_seed = detection_content_fingerprint(version.paragraphs, settings.pangram_model)
    usage_reservation_id = ""
    usage_finalized = False
    if settings.detector_mode == "pangram":
        usage_reservation_id = reserve_provider_calls(
            owner,
            "Pangram",
            [ProviderCallSpec("detection", settings.pangram_model, operation_seed)],
        )["detection"]
    job = create_job(db, owner, document.id, "analysis")
    run = AnalysisRun(id=new_id("analysis"), document_id=document.id, version_id=version.id, status="running", provider_mode=settings.detector_mode)
    db.add(run)
    if settings.job_mode == "celery":
        run.status = "queued"
        job.status = "queued"
        db.commit()
        from services.worker.celery_app import run_analysis_job

        run_analysis_job.delay(job.id, run.id, usage_reservation_id)
        audit(db, owner, "analysis.queued", document.id, analysisId=run.id, providerMode=settings.detector_mode)
        db.commit()
        return {"jobId": job.id, "analysis": document_payload(db, document)["analysis"]}
    db.commit()
    try:
        result = await run_detection(
            version.paragraphs,
            idempotency_key=operation_seed,
            analyzed_version_id=version.id,
        )
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
            usage_finalized = True
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
        if usage_reservation_id and not usage_finalized:
            cancel_unused_reservations([usage_reservation_id])
        run.status = "failed"
        run.error_code = "PROVIDER_FAILED"
        job.status = "failed"
        job.error_code = "PROVIDER_FAILED"
        job.updated_at = utcnow()
        db.commit()
        raise
    except Exception:
        if usage_reservation_id and not usage_finalized:
            finalize_provider_call(
                usage_reservation_id,
                final_status="outcome_unknown",
                error_code="application_interrupted",
            )
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


@app.post("/api/v1/documents/{document_id}/first-pass-rewrite", status_code=status.HTTP_201_CREATED)
async def first_pass_rewrite(
    document_id: str,
    payload: FirstPassRewriteRequest,
    owner: str = Depends(current_owner),
    db: Session = Depends(get_db),
):
    document = get_owned_document(db, owner, document_id)
    if document.current_version_id != payload.version_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="First pass must use the current version")
    version = get_version(db, document, payload.version_id)
    analysis = db.scalar(
        select(AnalysisRun)
        .where(
            AnalysisRun.document_id == document.id,
            AnalysisRun.version_id == version.id,
            AnalysisRun.status == "completed",
        )
        .order_by(AnalysisRun.created_at.desc())
        .limit(1)
    )
    result = analysis.result if analysis and isinstance(analysis.result, dict) else None
    spans = result.get("spans") if result and result.get("status") == "success" else None
    if not isinstance(spans, list):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A current successful detection is required")
    risk_ids = {
        span.get("paragraphId")
        for span in spans
        if isinstance(span, dict)
        and span.get("classification") in {"ai_generated", "ai_assisted"}
        and isinstance(span.get("paragraphId"), str)
    }
    passages = [
        {"paragraphId": paragraph["id"], "originalText": paragraph["text"]}
        for paragraph in version.paragraphs
        if paragraph["id"] in risk_ids
    ]
    if not passages:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="No marked risk paragraphs are available")
    total_characters = sum(len(item["originalText"]) for item in passages)
    if total_characters > MAX_AGENT_CONTEXT_CHARACTERS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Marked passages exceed the safe first-pass context limit")

    operation_seed = hashlib.sha256(
        json.dumps({"versionId": version.id, "passages": passages}, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    reservations: dict[str, str] = {}
    finalized_operations: set[str] = set()
    if settings.rewrite_mode == "deepseek":
        reservations = reserve_provider_calls(
            owner,
            "DeepSeek",
            [
                ProviderCallSpec("rewrite", settings.deepseek_model, f"{operation_seed}:rewrite"),
                ProviderCallSpec("validation", settings.deepseek_validator_model, f"{operation_seed}:validation"),
            ],
        )

    def observe_usage(**observation) -> None:
        operation = observation.pop("operation")
        reservation_id = reservations.get(operation)
        if not reservation_id:
            return
        finalize_provider_call(reservation_id, **observation)
        finalized_operations.add(operation)

    try:
        proposal = await propose_first_pass_rewrites(
            passages,
            idempotency_seed=operation_seed,
            usage_observer=observe_usage if reservations else None,
        )
    finally:
        cancel_unused_reservations(
            [reservation_id for operation, reservation_id in reservations.items() if operation not in finalized_operations]
        )
    db.refresh(document)
    if document.current_version_id != version.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Document changed during the first pass")

    rewrite = RewriteSession(id=new_id("rewrite"), document_id=document.id, version_id=version.id)
    db.add(rewrite)
    db.flush()
    if proposal["isMock"]:
        revision = proposal["revisions"][0]
        patch = PatchRecord(
            id=new_id("patch"),
            rewrite_session_id=rewrite.id,
            document_id=document.id,
            base_version_id=version.id,
            paragraph_id=revision["paragraphId"],
            original_text=revision["originalText"],
            revised_text=revision["revisedText"],
            reason=revision["reason"],
            protected_status="Citations, numbers, quotations, URLs, and abbreviations preserved",
        )
        db.add(patch)
        audit(db, owner, "patch.proposed", document.id, patchId=patch.id, mock=True, provider=proposal["provider"], model=proposal["modelVersion"])
        db.commit()
        return {
            "applied": False,
            "patch": {
                "id": patch.id,
                "baseVersionId": patch.base_version_id,
                "paragraphId": patch.paragraph_id,
                "originalText": patch.original_text,
                "revisedText": patch.revised_text,
                "reason": patch.reason,
                "protectedStatus": patch.protected_status,
                "status": patch.status,
                "isMock": True,
                "provider": proposal["provider"],
                "modelVersion": proposal["modelVersion"],
                "validatorModelVersion": None,
                "rewriteSessionId": rewrite.id,
                "revisionNumber": 1,
                "contextScope": "document",
                "contextCharacters": total_characters,
                "supersedesPatchId": None,
            },
            "targetParagraphCount": len(passages),
        }

    paragraphs = [dict(item) for item in version.paragraphs]
    revisions_by_id = {item["paragraphId"]: item for item in proposal["revisions"]}
    for paragraph in paragraphs:
        revision = revisions_by_id.get(paragraph["id"])
        if revision:
            assert_protected_equal(paragraph["text"], revision["revisedText"])
            paragraph["text"] = revision["revisedText"]
    count = validate_paragraphs(paragraphs)
    create_version(db, document, paragraphs, count, "agent-first-pass")
    for revision in proposal["revisions"]:
        patch = PatchRecord(
            id=new_id("patch"),
            rewrite_session_id=rewrite.id,
            document_id=document.id,
            base_version_id=version.id,
            paragraph_id=revision["paragraphId"],
            original_text=revision["originalText"],
            revised_text=revision["revisedText"],
            reason=revision["reason"],
            protected_status="Citations, numbers, quotations, URLs, and abbreviations preserved",
            status="accepted",
            decided_at=utcnow(),
        )
        db.add(patch)
        audit(db, owner, "patch.accepted", document.id, patchId=patch.id)
    audit(db, owner, "document.version", document.id, source="agent-first-pass", wordCount=count)
    db.commit()
    return {
        "applied": True,
        "document": document_payload(db, document),
        "targetParagraphCount": len(passages),
        "revisedParagraphCount": len(proposal["revisions"]),
    }


@app.post("/api/v1/rewrite-sessions/{session_id}/messages", status_code=status.HTTP_201_CREATED)
async def rewrite_message(
    session_id: str,
    payload: RewriteMessageRequest,
    owner: str = Depends(current_owner),
    db: Session = Depends(get_db),
):
    # Serialize proposals within one rewrite session so concurrent clicks cannot
    # create two independently pending successors. SQLite ignores this clause;
    # PostgreSQL enforces it in production.
    rewrite = db.scalar(select(RewriteSession).where(RewriteSession.id == session_id).with_for_update())
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
    previous_patch = None
    if payload.previous_patch_id:
        previous_patch = db.scalar(
            select(PatchRecord).where(
                PatchRecord.id == payload.previous_patch_id,
                PatchRecord.rewrite_session_id == rewrite.id,
            )
        )
        if not previous_patch:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Previous patch not found")
        if (
            previous_patch.status != "pending"
            or previous_patch.base_version_id != version.id
            or previous_patch.paragraph_id != payload.paragraph_id
        ):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Previous patch cannot be refined")
        if paragraph["text"].count(previous_patch.original_text) != 1:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Previous patch no longer matches the document")
    else:
        existing_pending = db.scalar(
            select(PatchRecord).where(
                PatchRecord.rewrite_session_id == rewrite.id,
                PatchRecord.status == "pending",
            )
        )
        if existing_pending:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Review or refine the pending patch before creating another",
            )

    context_text = _agent_context(
        version.paragraphs,
        payload.paragraph_id,
        payload.context_scope,
        payload.confirm_full_document_context,
    )
    current_candidate = previous_patch.revised_text if previous_patch else ""
    instruction_hash = hashlib.sha256(
        f"{payload.instruction}:{payload.selected_text}:{payload.context_scope}".encode("utf-8")
    ).hexdigest()
    operation_seed = f"{rewrite.id}:{version.id}:{payload.paragraph_id}:{previous_patch.id if previous_patch else 'first'}:{instruction_hash}"
    reservations: dict[str, str] = {}
    finalized_operations: set[str] = set()
    if settings.rewrite_mode == "deepseek":
        reservations = reserve_provider_calls(
            owner,
            "DeepSeek",
            [
                ProviderCallSpec("rewrite", settings.deepseek_model, f"{operation_seed}:rewrite"),
                ProviderCallSpec("validation", settings.deepseek_validator_model, f"{operation_seed}:validation"),
            ],
        )

    def observe_usage(**observation) -> None:
        operation = observation.pop("operation")
        reservation_id = reservations.get(operation)
        if not reservation_id:
            return
        finalize_provider_call(reservation_id, **observation)
        finalized_operations.add(operation)

    try:
        proposal = await propose_rewrite(
            payload.instruction,
            payload.paragraph_id,
            paragraph["text"],
            "" if previous_patch else payload.selected_text,
            anchor_text=previous_patch.original_text if previous_patch else "",
            current_candidate=current_candidate,
            context_text=context_text,
            idempotency_seed=operation_seed,
            usage_observer=observe_usage if reservations else None,
        )
    finally:
        cancel_unused_reservations(
            [reservation_id for operation, reservation_id in reservations.items() if operation not in finalized_operations]
        )
    if proposal["revisedText"] == (current_candidate or proposal["originalText"]):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="No safe automatic change was found for this passage")
    revision_number = int(
        db.scalar(select(func.count(PatchRecord.id)).where(PatchRecord.rewrite_session_id == rewrite.id)) or 0
    ) + 1
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
    if previous_patch:
        previous_patch.status = "superseded"
        previous_patch.decided_at = utcnow()
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
            "rewriteSessionId": rewrite.id,
            "revisionNumber": revision_number,
            "contextScope": payload.context_scope,
            "contextCharacters": len(context_text),
            "supersedesPatchId": previous_patch.id if previous_patch else None,
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
    other_pending = list(
        db.scalars(
            select(PatchRecord).where(
                PatchRecord.document_id == document.id,
                PatchRecord.base_version_id == patch.base_version_id,
                PatchRecord.status == "pending",
                PatchRecord.id != patch.id,
            )
        )
    )
    for other in other_pending:
        other.status = "superseded"
        other.decided_at = utcnow()
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
