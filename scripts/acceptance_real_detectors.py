from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any

import httpx


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def require_status(response: httpx.Response, expected: int, step: str) -> None:
    if response.status_code != expected:
        detail = ""
        try:
            payload = response.json()
            if isinstance(payload, dict) and isinstance(payload.get("detail"), str):
                detail = f": {payload['detail']}"
        except ValueError:
            pass
        raise RuntimeError(f"{step} returned HTTP {response.status_code}{detail}")


def synthetic_paper() -> str:
    sentence = (
        "This synthetic evaluation paragraph describes how researchers compare evidence, document uncertainty, "
        "review alternative explanations, and preserve transparent reasoning before drawing a limited conclusion."
    )
    body = " ".join(f"{sentence} Test case {index} remains nonpersonal and reproducible." for index in range(1, 46))
    return f"Synthetic Provider Acceptance\n\n{body}"


def validate_provider(provider: dict[str, Any], expected_name: str) -> None:
    required = {
        "overallScore",
        "sentenceSpans",
        "confidence",
        "provider",
        "providerModelVersion",
        "requestId",
        "warnings",
        "isMock",
        "latencyMs",
        "status",
        "error",
    }
    missing = sorted(required - set(provider))
    if missing:
        raise RuntimeError(f"{expected_name} response is missing normalized fields: {', '.join(missing)}")
    if provider["provider"] != expected_name:
        raise RuntimeError(f"Expected {expected_name}, received a different provider")
    if provider["status"] != "success" or provider["error"] is not None:
        message = provider.get("error", {}).get("message", "unknown provider failure") if provider.get("error") else "unknown provider failure"
        raise RuntimeError(f"{expected_name} failed: {message}")
    if provider["isMock"] is not False:
        raise RuntimeError(f"{expected_name} returned a mock/sandbox result")
    if provider["overallScore"] is None or not provider["providerModelVersion"] or not provider["requestId"]:
        raise RuntimeError(f"{expected_name} did not return a complete real result")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one paid synthetic Paperlight dual-detector acceptance flow.")
    parser.add_argument(
        "--confirm-cost",
        action="store_true",
        help="Required acknowledgement that this script performs one real Pangram and one real Copyleaks analysis.",
    )
    args = parser.parse_args()
    if not args.confirm_cost:
        parser.error("--confirm-cost is required because this script consumes real provider credits")

    base_url = os.getenv("PAPERLIGHT_API_BASE_URL", "https://api-production-840c.up.railway.app").rstrip("/")
    owner_email = require_env("PAPERLIGHT_OWNER_EMAIL")
    owner_password = require_env("PAPERLIGHT_OWNER_PASSWORD")
    totp_code = os.getenv("PAPERLIGHT_OWNER_TOTP", "").strip()
    document_id = ""
    logged_in = False

    with httpx.Client(base_url=base_url, timeout=180.0, follow_redirects=False) as client:
        try:
            health = client.get("/api/health")
            require_status(health, 200, "Health check")
            provider_mode = health.json().get("providerMode", {})
            if provider_mode.get("detector") != "dual":
                raise RuntimeError("Production DETECTOR_MODE is not dual; no paid scan was started")

            login = client.post(
                "/api/v1/auth/login",
                json={"email": owner_email, "password": owner_password, "totp_code": totp_code},
            )
            require_status(login, 200, "Owner login")
            session_token = login.json().get("session_token")
            if not isinstance(session_token, str) or not session_token:
                raise RuntimeError("Login returned no session token")
            client.headers["Authorization"] = f"Bearer {session_token}"
            logged_in = True

            created = client.post(
                "/api/v1/documents",
                data={"title": "Synthetic dual-provider acceptance", "text": synthetic_paper()},
            )
            require_status(created, 201, "Synthetic document creation")
            document = created.json()["document"]
            document_id = document["id"]

            analysis = client.post(f"/api/v1/documents/{document_id}/analyses")
            require_status(analysis, 201, "Dual-provider analysis")
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                current = client.get(f"/api/v1/documents/{document_id}")
                require_status(current, 200, "Analysis polling")
                document = current.json()["document"]
                if document.get("analysis", {}).get("result"):
                    break
                time.sleep(2)
            else:
                raise RuntimeError("Analysis did not complete within 180 seconds")

            result = document["analysis"]["result"]
            providers = {row.get("provider"): row for row in result.get("providers", [])}
            validate_provider(providers.get("Pangram", {}), "Pangram")
            validate_provider(providers.get("Copyleaks", {}), "Copyleaks")
            if result.get("isMock") is not False:
                raise RuntimeError("Top-level analysis was incorrectly labeled as mock")
            if result.get("fusionStatus") not in {"provider-agreement", "disagreement"}:
                raise RuntimeError("Dual analysis did not reach a valid two-provider terminal state")
            if result.get("fusionStatus") == "disagreement" and result.get("overallScore") is not None:
                raise RuntimeError("Disagreement incorrectly returned a fused percentage")

            paragraph_lengths = {
                row["id"]: len(row["text"]) for row in document["currentVersion"]["paragraphs"]
            }
            for span in result.get("spans", []):
                if (
                    span.get("paragraphId") not in paragraph_lengths
                    or not 0 <= span.get("start", -1) < span.get("end", -1) <= paragraph_lengths[span["paragraphId"]]
                    or span.get("evidence") not in {"single", "consensus"}
                ):
                    raise RuntimeError("Fused sentence mapping contains an invalid range")

            exported = client.post(f"/api/v1/documents/{document_id}/exports")
            require_status(exported, 200, "DOCX export")
            if not exported.content.startswith(b"PK"):
                raise RuntimeError("DOCX export is not a valid ZIP-based Word package")

            paragraphs = [dict(row) for row in document["currentVersion"]["paragraphs"]]
            paragraphs[-1]["text"] += " This final synthetic sentence records a harmless post-analysis edit."
            updated = client.patch(
                f"/api/v1/documents/{document_id}",
                json={"base_version_id": document["currentVersion"]["id"], "paragraphs": paragraphs},
            )
            require_status(updated, 200, "Post-analysis edit")
            if updated.json()["document"].get("analysis", {}).get("isStale") is not True:
                raise RuntimeError("Editing the paper did not mark the previous analysis stale")

            deleted = client.delete(f"/api/v1/documents/{document_id}")
            require_status(deleted, 204, "Synthetic document deletion")
            document_id = ""
            remaining = client.get("/api/v1/documents")
            require_status(remaining, 200, "Residue check")
            if any(row.get("title") == "Synthetic dual-provider acceptance" for row in remaining.json()["documents"]):
                raise RuntimeError("Synthetic document remained after deletion")

            logout = client.post("/api/v1/auth/logout")
            require_status(logout, 204, "Logout")
            logged_in = False
            print("PASS: one synthetic dual-provider analysis, mapping check, DOCX export, stale transition, deletion, and logout completed.")
            return 0
        finally:
            if document_id:
                try:
                    client.delete(f"/api/v1/documents/{document_id}")
                except httpx.HTTPError:
                    pass
            if logged_in:
                try:
                    client.post("/api/v1/auth/logout")
                except httpx.HTTPError:
                    pass


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, httpx.HTTPError, KeyError, TypeError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
