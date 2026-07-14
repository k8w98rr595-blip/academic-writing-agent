from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path


PROTECTED_PATTERN = re.compile(
    r"https?://\S+|\[[0-9,\-\s]+\]|\([A-Z][A-Za-z'’-]+(?:\s+et al\.)?,?\s+\d{4}[a-z]?\)|"
    r"\b\d+(?:\.\d+)?%?\b|\b[A-Z]{2,}[A-Z0-9-]*\b|[\"“”][^\"“”]{2,240}[\"“”]"
)


def synthetic_paper() -> str:
    paragraphs = [
        "Introduction\nAcademic writing tools can support revision when they preserve the writer's evidence, uncertainty, and responsibility. This synthetic paper examines a narrow question: how should a university writing assistant improve clarity without pretending to determine authorship? The discussion treats automated scores as indicators rather than verdicts. It also assumes that students remain responsible for checking citations, interpreting feedback, and deciding whether a proposed change represents their intended claim. A useful system therefore combines transparent labels, reversible edits, and limits on what the software may change. These controls matter because a fluent sentence can still be inaccurate, and an attractive score can still encourage misplaced confidence.",
        "A small pilot reviewed 42 records in 2025 and reported a 17.5% revision rate. According to (Lovelace, 1843) and [2], \"Reliable review requires context.\" The public reference was https://example.org/research and the protected names were OpenAI, Cambridge University, Ada Lovelace, UNESCO, and GDPR. These details are synthetic and do not describe real students. They are included to test whether a revision system preserves numbers, quotations, URLs, citation markers, abbreviations, and proper nouns while changing surrounding prose. Any acceptable patch must keep every listed item exactly and must not introduce a new factual claim.",
        "The first design principle is reversibility. A revision assistant should present a proposed change beside the original passage, explain the reason for the change, and wait for the owner to accept or reject it. This arrangement keeps authorship decisions with the user. It also makes errors visible before they enter the current document. Version history provides a second layer of protection because an accepted patch can be inspected against its base version. When the current version changes, older analysis ranges and pending patches should become stale rather than silently attaching themselves to new text.",
        "The second principle is honest uncertainty. Pattern detectors do not observe the writing process, so they cannot prove who produced a sentence. They estimate characteristics of text using models, thresholds, and reference data that may change. A responsible interface should identify a demonstration provider, show that its score is probabilistic, and distinguish agreement between providers from a single-provider signal. The interface should also avoid marketing language that promises a particular institutional outcome. In practice, the most useful result is often a set of passages for human review, not a single percentage presented without context.",
        "The third principle is data minimization. Course papers can contain names, research participants, unpublished findings, or confidential placement information. A private prototype should accept only the material needed for the requested operation, avoid placing full papers in logs, and delete documents after a short retention period. Provider calls should have clear boundaries, timeouts, and failure behavior. If a provider rejects a request or returns malformed output, the application should fail closed instead of applying a partial response. Owners also need an immediate delete action that removes versions, jobs, analyses, rewrite sessions, patches, and stored files together.",
        "Operational controls are equally important. A paid model can create unexpected cost when duplicate jobs, rapid retries, or a user interface bug repeats the same request. Idempotency keys should connect an operation to a document version and provider. Retry policies should exclude authentication, balance, validation, and permission errors. A small service can start with conservative daily and weekly warnings, followed by a monthly soft limit that disables optional repeat work. A final hard limit should stop new paid tasks while leaving login, viewing, export, and deletion available to the owner.",
        "Evaluation should test both expected behavior and cleanup. A production exercise can create a synthetic paper, run the labeled demonstration detector, request a real rewrite, accept one patch, and confirm that the previous detector result is stale. It can then run a second analysis, export a Word document in memory, delete the paper, and verify that related job and rewrite identifiers no longer resolve. The exercise should not use a real assignment or preserve the exported file. Repeating this check after meaningful deployment changes gives the owner evidence that the main workflow and its privacy boundary still function.",
        "Interface testing should cover more than a successful desktop screenshot. Keyboard access, narrow screens, loading states, and error messages determine whether the owner can recover from a failed provider call. On a mobile viewport, navigation and the primary editor must remain reachable without hiding destructive actions or important warnings. On a desktop viewport, the document list, editor, analysis evidence, and patch review should remain distinguishable. Static hosting under a repository subpath adds another risk because absolute asset paths can work locally but fail after deployment.",
        "The limitations of this exercise are deliberate. The demonstration detector is deterministic test infrastructure and is not a substitute for a commercial authorship classifier. The production rewrite call verifies integration and preservation controls, but one successful passage cannot establish general model reliability. The test also does not compare results with a university database or a plagiarism corpus. Those questions require a separate benchmark, lawful data access, documented sampling, and human review. The present goal is narrower: determine whether the private owner workflow behaves as documented without exposing a real student's work.",
        "Conclusion\nA writing assistant is most trustworthy when it makes narrow promises and preserves user control. Reversible patches, protected tokens, stale-result handling, explicit demonstration labels, short retention, and cost limits reinforce one another. Together they reduce the chance that a convenient feature becomes an unreviewed content change, an unsupported accusation, a privacy incident, or an unexpected bill. Production acceptance should therefore record not only successful output but also authentication boundaries, provider identity, cleanup, static asset behavior, and known limitations. That record gives the owner a practical basis for deciding whether the private service is ready for continued use.",
    ]
    text = "\n\n".join(paragraphs)
    if len(re.findall(r"\b[\w’'-]+\b", text)) < 800:
        raise RuntimeError("Synthetic paper unexpectedly fell below 800 words")
    return text


def load_owner_handoff(path: Path) -> tuple[str, str]:
    raw = path.read_text(encoding="utf-8")
    email = re.search(r"(?m)^OWNER_EMAIL=(.+)$", raw)
    password = re.search(r"(?m)^Login password: (.+)$", raw)
    if not email or not password:
        raise RuntimeError("Owner handoff is missing required login fields")
    return email.group(1).strip(), password.group(1).strip()


class ApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.token = ""

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body=None,
        form=None,
        headers=None,
        timeout: int = 90,
    ) -> tuple[int, dict, bytes]:
        request_headers = {"Accept": "application/json", **(headers or {})}
        body = None
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        elif form is not None:
            body = urllib.parse.urlencode(form).encode("utf-8")
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        if self.token:
            request_headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=body, headers=request_headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read()
                return response.status, dict(response.headers.items()), payload
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers.items()), error.read()

    def json(
        self,
        method: str,
        path: str,
        *,
        expected: int,
        json_body=None,
        form=None,
        timeout: int = 90,
    ) -> dict:
        status, _, payload = self.request(
            method, path, json_body=json_body, form=form, timeout=timeout
        )
        if status != expected:
            detail = payload.decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"{method} {path} returned {status}, expected {expected}: {detail}")
        return json.loads(payload or b"{}")


def assert_static_pages(pages_url: str, api_url: str, results: dict) -> None:
    with urllib.request.urlopen(f"{pages_url.rstrip('/')}/", timeout=30) as response:
        html = response.read().decode("utf-8", errors="replace")
        if response.status != 200:
            raise RuntimeError("Pages root did not return HTTP 200")
    asset_paths = re.findall(r'(?:src|href)="([^"#?]+)"', html)
    same_origin_assets = []
    for path in asset_paths:
        url = urllib.parse.urljoin(f"{pages_url.rstrip('/')}/", path)
        if urllib.parse.urlparse(url).netloc == urllib.parse.urlparse(pages_url).netloc:
            same_origin_assets.append(url)
    config_url = f"{pages_url.rstrip('/')}/config.js"
    if config_url not in same_origin_assets:
        same_origin_assets.append(config_url)
    checked = 0
    for url in list(dict.fromkeys(same_origin_assets))[:12]:
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = response.read()
            if response.status != 200 or not payload:
                raise RuntimeError(f"Static asset failed: {url}")
            if url == config_url and api_url.encode("utf-8") not in payload:
                raise RuntimeError("Pages config.js does not reference the production API")
            checked += 1
    results["frontend_static"] = {"status": "pass", "assets_checked": checked}


def protected_tokens(value: str) -> collections.Counter[str]:
    return collections.Counter(match.group(0) for match in PROTECTED_PATTERN.finditer(value))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a destructive, synthetic-only Paperlight production acceptance test")
    parser.add_argument("--api-url", default="https://api-production-840c.up.railway.app")
    parser.add_argument("--pages-url", default="https://k8w98rr595-blip.github.io/academic-writing-agent")
    parser.add_argument("--owner-handoff", required=True)
    parser.add_argument("--json-output")
    args = parser.parse_args()

    if not args.api_url.startswith("https://") or not args.pages_url.startswith("https://"):
        raise RuntimeError("Production acceptance requires HTTPS URLs")

    started = dt.datetime.now(dt.timezone.utc)
    results: dict[str, object] = {"started_at": started.isoformat(), "steps": {}}
    steps: dict = results["steps"]
    client = ApiClient(args.api_url)
    document_id = ""
    rewrite_id = ""
    patch_id = ""
    analysis_job_id = ""
    email, password = load_owner_handoff(Path(args.owner_handoff))

    try:
        assert_static_pages(args.pages_url, args.api_url, steps)

        health = client.json("GET", "/api/health", expected=200)
        if health.get("ok") is not True or health.get("providerMode") != {"detector": "mock", "rewrite": "deepseek"}:
            raise RuntimeError("Production provider mode does not match mock detector + DeepSeek rewrite")
        steps["health"] = {"status": "pass", "provider_mode": health["providerMode"]}

        auth = client.json("GET", "/api/v1/auth/status", expected=200)
        if auth.get("configured") is not True or auth.get("requiresTotp") is not False:
            raise RuntimeError("Owner authentication status does not match password-only mode")
        steps["auth_status"] = {"status": "pass", "requires_totp": False}

        unauth_status, _, _ = client.request("GET", "/api/v1/documents")
        if unauth_status != 401:
            raise RuntimeError(f"Unauthenticated documents endpoint returned {unauth_status}")
        steps["unauthenticated_boundary"] = {"status": "pass", "http_status": 401}

        origin = urllib.parse.urlsplit(args.pages_url)
        cors_origin = f"{origin.scheme}://{origin.netloc}"
        cors_status, cors_headers, _ = client.request(
            "OPTIONS",
            "/api/v1/auth/login",
            headers={
                "Origin": cors_origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        allow_origin = next((value for key, value in cors_headers.items() if key.lower() == "access-control-allow-origin"), "")
        if cors_status != 200 or allow_origin != cors_origin:
            raise RuntimeError("Production CORS preflight did not allow the exact Pages origin")
        steps["cors"] = {"status": "pass", "allowed_origin": cors_origin}

        login = client.json(
            "POST", "/api/v1/auth/login", expected=200, json_body={"email": email, "password": password}
        )
        client.token = login.get("session_token", "")
        if not client.token:
            raise RuntimeError("Password login did not return a session")
        steps["password_login"] = {"status": "pass"}

        paper = synthetic_paper()
        created = client.json(
            "POST",
            "/api/v1/documents",
            expected=201,
            form={
                "title": f"Synthetic production acceptance {started.strftime('%Y%m%d-%H%M%S')}",
                "text": paper,
            },
        )["document"]
        document_id = created["id"]
        if created["currentVersion"]["wordCount"] < 800:
            raise RuntimeError("Created synthetic document is below the production minimum")
        steps["document_create"] = {
            "status": "pass",
            "word_count": created["currentVersion"]["wordCount"],
            "paragraph_count": len(created["currentVersion"]["paragraphs"]),
        }

        analysis_response = client.json(
            "POST", f"/api/v1/documents/{document_id}/analyses", expected=201
        )
        analysis_job_id = analysis_response["jobId"]
        analysis = analysis_response["analysis"]
        detection = analysis["result"]
        if detection.get("isMock") is not True or not detection.get("providers"):
            raise RuntimeError("Detector did not return an explicitly labeled Mock result")
        if not all(provider.get("isMock") is True for provider in detection["providers"]):
            raise RuntimeError("A detector provider was not labeled as Mock")
        if "probabilistic" not in detection.get("disclaimer", "").lower():
            raise RuntimeError("Mock detector disclaimer is missing")
        steps["mock_detection"] = {
            "status": "pass",
            "is_mock": True,
            "provider_count": len(detection["providers"]),
            "evidence_count": len(detection.get("evidence", [])),
        }

        job_status, _, job_payload = client.request("GET", f"/api/v1/jobs/{analysis_job_id}/events")
        if job_status != 200 or b'"status": "completed"' not in job_payload:
            raise RuntimeError("Analysis job did not complete")
        steps["analysis_job"] = {"status": "pass"}

        rewrite = client.json(
            "POST",
            f"/api/v1/documents/{document_id}/rewrite-sessions",
            expected=201,
            json_body={"version_id": created["currentVersion"]["id"]},
        )["rewriteSession"]
        rewrite_id = rewrite["id"]
        target = created["currentVersion"]["paragraphs"][1]
        patch = client.json(
            "POST",
            f"/api/v1/rewrite-sessions/{rewrite_id}/messages",
            expected=201,
            timeout=240,
            json_body={
                "instruction": "Make this paragraph more direct and natural while preserving every fact and protected token exactly.",
                "paragraph_id": target["id"],
                "selected_text": "",
            },
        )["patch"]
        patch_id = patch["id"]
        if patch.get("isMock") is not False or patch.get("provider") != "DeepSeek":
            raise RuntimeError("Rewrite patch did not come from the real DeepSeek provider")
        if patch.get("modelVersion") != "deepseek-v4-pro" or patch.get("validatorModelVersion") != "deepseek-v4-flash":
            raise RuntimeError("DeepSeek model metadata did not match the configured V4 pair")
        if protected_tokens(patch["originalText"]) != protected_tokens(patch["revisedText"]):
            raise RuntimeError("A server-protected token changed in the proposed patch")
        proper_names = ["OpenAI", "Cambridge University", "Ada Lovelace", "UNESCO", "GDPR"]
        if not all(name in patch["originalText"] and name in patch["revisedText"] for name in proper_names):
            raise RuntimeError("A required proper noun changed in the proposed patch")
        steps["deepseek_patch"] = {
            "status": "pass",
            "provider": patch["provider"],
            "model": patch["modelVersion"],
            "validator_model": patch["validatorModelVersion"],
            "protected_tokens_preserved": True,
            "proper_nouns_preserved": True,
        }

        accepted = client.json(
            "POST",
            f"/api/v1/patches/{patch_id}/accept",
            expected=200,
            json_body={"expected_base_version_id": patch["baseVersionId"]},
        )["document"]
        if accepted.get("analysis", {}).get("isStale") is not True:
            raise RuntimeError("Accepted patch did not make the previous analysis stale")
        steps["patch_acceptance"] = {
            "status": "pass",
            "new_version": accepted["currentVersion"]["number"],
            "previous_analysis_stale": True,
        }

        reanalysis = client.json(
            "POST", f"/api/v1/documents/{document_id}/analyses", expected=201
        )["analysis"]
        if reanalysis.get("isStale") is not False or reanalysis.get("result", {}).get("isMock") is not True:
            raise RuntimeError("Reanalysis did not produce a fresh Mock result")
        steps["reanalysis"] = {"status": "pass", "fresh": True, "is_mock": True}

        export_status, export_headers, export_payload = client.request(
            "POST", f"/api/v1/documents/{document_id}/exports"
        )
        content_type = next((value for key, value in export_headers.items() if key.lower() == "content-type"), "")
        if export_status != 200 or not content_type.startswith(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ):
            raise RuntimeError("DOCX export returned an unexpected response")
        if export_payload[:2] != b"PK":
            raise RuntimeError("DOCX export is not a ZIP-based Word file")
        with zipfile.ZipFile(BytesIO(export_payload)) as archive:
            names = set(archive.namelist())
            if "word/document.xml" not in names or "[Content_Types].xml" not in names:
                raise RuntimeError("DOCX export is missing required package entries")
        steps["docx_export"] = {
            "status": "pass",
            "bytes": len(export_payload),
            "persisted_locally": False,
        }

        delete_status, _, _ = client.request("DELETE", f"/api/v1/documents/{document_id}")
        if delete_status != 204:
            raise RuntimeError(f"Document deletion returned {delete_status}")
        read_status, _, _ = client.request("GET", f"/api/v1/documents/{document_id}")
        list_payload = client.json("GET", "/api/v1/documents", expected=200)
        job_after_delete, _, _ = client.request("GET", f"/api/v1/jobs/{analysis_job_id}/events")
        rewrite_after_delete, _, _ = client.request(
            "POST",
            f"/api/v1/rewrite-sessions/{rewrite_id}/messages",
            json_body={"instruction": "No-op cleanup probe", "paragraph_id": target["id"], "selected_text": ""},
        )
        patch_after_delete, _, _ = client.request(
            "POST",
            f"/api/v1/patches/{patch_id}/accept",
            json_body={"expected_base_version_id": patch["baseVersionId"]},
        )
        if read_status != 404 or any(row.get("id") == document_id for row in list_payload.get("documents", [])):
            raise RuntimeError("Deleted test document is still reachable")
        if job_after_delete != 404 or rewrite_after_delete != 404 or patch_after_delete != 404:
            raise RuntimeError("A test job, rewrite session, or patch remained reachable after deletion")
        document_id = ""
        steps["cleanup"] = {
            "status": "pass",
            "document": "not_found",
            "job": "not_found",
            "rewrite_session": "not_found",
            "patch": "not_found",
            "export_file_persisted": False,
        }
    finally:
        if document_id and client.token:
            client.request("DELETE", f"/api/v1/documents/{document_id}")
        if client.token:
            logout_status, _, _ = client.request("POST", "/api/v1/auth/logout")
            steps["logout"] = {"status": "pass" if logout_status == 204 else "fail", "http_status": logout_status}
            client.token = ""

    results["completed_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    results["status"] = "pass"
    rendered = json.dumps(results, ensure_ascii=False, indent=2)
    if args.json_output:
        Path(args.json_output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"status": "fail", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
