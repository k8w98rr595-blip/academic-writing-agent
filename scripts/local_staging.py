"""Credential-free local rehearsal; never loads an env file or contacts a provider."""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
from functools import partial
from getpass import getpass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
from urllib.parse import unquote, urlsplit
import uuid

import httpx
from argon2 import PasswordHasher

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.api.app.staging_guard import API_ORIGIN, BASE_PATH, STAGING_ROOT, WEB_ORIGIN, inside_staging

OWNER = "owner@staging.paperlight.local"
# Use an allowlist, not a denylist: newly added production credentials cannot leak
# into child processes through environment inheritance.
SYSTEM_ENV = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP",
              "HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "PROGRAMDATA",
              "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "SYSTEMDRIVE"}


class StagingError(RuntimeError):
    """Only constant, credential-free diagnostic messages may use this class."""


def clean_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    source = os.environ if source is None else source
    return {key: value for key, value in source.items() if key.upper() in SYSTEM_ENV}


def api_environment(run_dir: Path, password_hash: str) -> dict[str, str]:
    if not inside_staging(run_dir):
        raise StagingError("Run directory must stay inside .staging")
    return {
        **clean_environment(), "PYTHONUTF8": "1", "PYTHONPATH": str(ROOT),
        "APP_ENV": "local-staging", "HOST": "127.0.0.1", "PORT": "8100",
        "DATABASE_URL": f"sqlite:///{(run_dir / 'paperlight.db').as_posix()}",
        "OBJECT_STORAGE_MODE": "local", "OBJECT_STORAGE_DIR": str(run_dir / "objects"),
        "JOB_MODE": "eager", "REDIS_URL": "", "ALLOWED_ORIGINS": WEB_ORIGIN,
        "OWNER_EMAIL": OWNER, "OWNER_PASSWORD_HASH": password_hash,
        "REQUIRE_TOTP": "0", "COOKIE_SECURE": "0", "TRUST_PROXY": "0", "SESSION_TTL_HOURS": "1",
        "DETECTOR_MODE": "mock", "REWRITE_MODE": "mock", "PANGRAM_PAID_CALLS_ENABLED": "0",
        "DETECTOR_DATA_PROCESSING_ACKNOWLEDGED": "0",
        "BILLING_MODE": "test", "BILLING_APP_URL": WEB_ORIGIN + BASE_PATH,
    }


def ensure_free_ports() -> None:
    for port in (3100, 8100):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                raise StagingError(f"Port {port} is in use; no existing process was stopped") from None


def build_site() -> Path:
    node = shutil.which("node")
    modules = ROOT / "apps/web/node_modules"
    if not node or not (modules / "next/dist/bin/next").is_file():
        raise StagingError("Install Node.js and run pnpm install --frozen-lockfile first")
    build = STAGING_ROOT / "builds" / uuid.uuid4().hex / "web"
    if not inside_staging(build):
        raise StagingError("Refusing build through an external staging path alias")
    build.mkdir(parents=True)
    source = ROOT / "apps/web"
    # Explicit source allowlist: no .env files, local data, credentials or old output.
    for name in ("app", "components", "lib", "public"):
        shutil.copytree(source / name, build / name, ignore=shutil.ignore_patterns(".env*", "*.tsbuildinfo"))
    for name in ("package.json", "next.config.mjs", "tsconfig.json", "next-env.d.ts"):
        if (source / name).is_file():
            shutil.copy2(source / name, build / name)
    link = build / "node_modules"
    if os.name == "nt":
        # A junction only shares installed packages; never recursively delete it.
        quoted_link = str(link).replace("'", "''")
        quoted_target = str(modules).replace("'", "''")
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"New-Item -ItemType Junction -Path '{quoted_link}' -Target '{quoted_target}' | Out-Null"],
                       check=True, env=clean_environment(), cwd=build)
    else:
        link.symlink_to(modules, target_is_directory=True)
    runtime_config = {"apiBaseUrl": API_ORIGIN, "basePath": BASE_PATH, "environment": "local-staging"}
    (build / "public/config.js").write_text(
        f"window.PAPERLIGHT_CONFIG = Object.freeze({json.dumps(runtime_config)});\n", encoding="utf-8")
    environment = {**clean_environment(), "NEXT_TELEMETRY_DISABLED": "1", "PAPERLIGHT_LOCAL_STAGING": "1",
                   "NEXT_PUBLIC_BASE_PATH": BASE_PATH, "NEXT_PUBLIC_API_BASE_URL": API_ORIGIN}
    subprocess.run([node, str(modules / "next/dist/bin/next"), "build", str(build)],
                   cwd=build, env=environment, check=True)
    site = build / "out"
    subprocess.run([node, str(ROOT / "scripts/check-static-secrets.mjs"), str(site)],
                   cwd=ROOT, env=environment, check=True)
    (STAGING_ROOT / "site.json").write_text(json.dumps({"path": str(site.relative_to(STAGING_ROOT))}), encoding="utf-8")
    print("Isolated Pages-subpath build and static secret scan passed; source config was not changed.")
    return site


def site_directory() -> Path:
    manifest = STAGING_ROOT / "site.json"
    if not inside_staging(manifest):
        raise StagingError("Refusing a non-isolated site manifest")
    if not manifest.is_file():
        raise StagingError("Run the build command first")
    site = (STAGING_ROOT / json.loads(manifest.read_text(encoding="utf-8"))["path"]).resolve()
    if not inside_staging(site) or not (site / "index.html").is_file():
        raise StagingError("Invalid isolated site artifact")
    config = (site / "config.js").read_text(encoding="utf-8")
    if API_ORIGIN not in config or '"local-staging"' not in config:
        raise StagingError("Site is not an isolated staging build")
    return site


class StagingFiles(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass  # No URLs, headers, or client payloads in console logs.

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "connect-src 'self' http://127.0.0.1:8100; frame-ancestors 'none'")
        super().end_headers()

    def do_GET(self):
        if self.headers.get("Host") != "127.0.0.1:3100":
            self.send_error(403)
            return
        requested = unquote(urlsplit(self.path).path)
        if requested == "/":
            self.send_response(302)
            self.send_header("Location", BASE_PATH + "/")
            self.end_headers()
            return
        if not requested.startswith(BASE_PATH + "/"):
            self.send_error(404)
            return
        relative = requested[len(BASE_PATH):]
        if any(part in {"..", "."} for part in relative.split("/")) or "\\" in relative:
            self.send_error(404)
            return
        self.path = relative
        super().do_GET()

    def do_HEAD(self):
        self.send_error(405)

    def list_directory(self, path):
        self.send_error(404)
        return None


@contextmanager
def running_stage(run_dir: Path, password: str):
    if not inside_staging(run_dir):
        raise StagingError("Refusing a non-isolated runtime directory")
    site = site_directory()
    ensure_free_ports()
    run_dir.mkdir(parents=True, exist_ok=True)
    verifier = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2).hash(password)
    server = ThreadingHTTPServer(("127.0.0.1", 3100), partial(StagingFiles, directory=str(site)))
    process = None
    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "services.api.app.main:app", "--host", "127.0.0.1",
             "--port", "8100", "--no-access-log", "--log-level", "error"],
            cwd=ROOT, env=api_environment(run_dir, verifier), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        with httpx.Client(trust_env=False, timeout=2) as client:
            for _ in range(80):
                if process.poll() is not None:
                    raise StagingError("Isolated API startup failed; no secrets or request bodies were logged")
                try:
                    health = client.get(API_ORIGIN + "/api/health").json()
                    if health.get("environment") == "local-staging":
                        break
                except (httpx.HTTPError, ValueError):
                    pass
                time.sleep(0.25)
            else:
                raise StagingError("Isolated API startup timed out")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield
        finally:
            server.shutdown()
            thread.join(timeout=3)
    finally:
        server.server_close()
        if process is not None:
            if os.name == "nt" and process.poll() is None:
                # Windows venv launchers may own a second Python process. Stop
                # only the child tree we created, not unrelated Python servers.
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            else:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def smoke_checks(password: str) -> list[str]:
    checks = []
    document_id = None
    token = None
    with httpx.Client(base_url=API_ORIGIN, trust_env=False, timeout=30) as client:
        def request(method, path, status=200, **kwargs):
            response = client.request(method, path, **kwargs)
            if response.status_code != status:
                raise StagingError(f"Staging acceptance failed: {method} route returned {response.status_code}, expected {status}")
            return response

        health = request("GET", "/api/health").json()
        assert health["environment"] == "local-staging"
        assert health["providerMode"] == {"detector": "mock", "rewrite": "mock"}
        assert health["billing"]["mode"] == "test"
        request("GET", "/api/v1/documents", 401)
        request("GET", "/api/health", 403, headers={"Host": "attacker.invalid"})
        request("GET", "/api/health", 403, headers={"Origin": "https://attacker.invalid"})
        checks.append("environment, Mock modes, unauthenticated 401, hostile Host/Origin rejected")
        try:
            token = request("POST", "/api/v1/auth/login", json={"email": OWNER, "password": password, "totp_code": ""}).json()["session_token"]
            client.headers["Authorization"] = "Bearer " + token
            summary = request("GET", "/api/v1/billing/summary").json()
            assert summary["plan"]["key"] == "free"
            checkout = request("POST", "/api/v1/billing/checkout-session", json={"trigger": "manual"}).json()
            assert checkout["url"].startswith(WEB_ORIGIN + BASE_PATH)
            request("POST", "/api/v1/billing/test/plan", 204, json={"plan": "pro"})
            assert request("GET", "/api/v1/billing/summary").json()["plan"]["key"] == "pro"
            checks.append("separate owner login and simulated Free/Pro upgrade")
            sentence = "It is important to note that ethical data reuse requires consent, purpose limitation, careful governance, and accountable review. "
            paper = "Introduction\n\n" + sentence * 40
            document = request("POST", "/api/v1/documents", 201,
                               data={"title": "Synthetic local staging acceptance", "text": paper}).json()["document"]
            document_id = document["id"]
            prefix = f"/api/v1/documents/{document_id}"
            idempotency = lambda: {"Idempotency-Key": str(uuid.uuid4())}
            analysis = request("POST", prefix + "/analyses", 201, headers=idempotency()).json()["analysis"]["result"]
            assert analysis["isMock"] and analysis["spans"]
            assert all(span["classification"] in {"ai_generated", "ai_assisted"} for span in analysis["spans"])
            checks.append("synthetic document, Mock analysis and classified spans")
            base = document["currentVersion"]
            preview = request("POST", prefix + "/first-pass-rewrite", 201, headers=idempotency(),
                              json={"version_id": base["id"]}).json()
            assert preview["applied"] is False
            batch = preview["document"]["patches"]
            assert batch and all(patch["batch"] and patch["isMock"] for patch in batch)
            updated = request("POST", f"/api/v1/rewrite-sessions/{preview['rewriteSessionId']}/batch-decision",
                              json={"expected_base_version_id": base["id"],
                                    "accepted_patch_ids": [patch["id"] for patch in batch]}).json()["document"]
            assert updated["analysis"]["isStale"] and updated["currentVersion"]["number"] == 2
            document = request("POST", prefix + f"/versions/{base['id']}/restore",
                               json={"expected_current_version_id": updated["currentVersion"]["id"]}).json()["document"]
            assert document["currentVersion"]["paragraphs"] == base["paragraphs"]
            checks.append("persisted batch preview, explicit acceptance and whole-version restoration")
            session = request("POST", prefix + "/rewrite-sessions", 201,
                              json={"version_id": document["currentVersion"]["id"]}).json()["rewriteSession"]
            patch = request("POST", f"/api/v1/rewrite-sessions/{session['id']}/messages", 201,
                            headers=idempotency(), json={"instruction": "Make the argument more direct",
                            "paragraph_id": document["currentVersion"]["paragraphs"][1]["id"], "selected_text": ""}).json()["patch"]
            assert patch["isMock"]
            updated = request("POST", f"/api/v1/patches/{patch['id']}/accept",
                              json={"expected_base_version_id": patch["baseVersionId"]}).json()["document"]
            assert updated["analysis"]["isStale"] is True
            analysis = request("POST", prefix + "/analyses", 201, headers=idempotency()).json()["analysis"]["result"]
            assert "riskComparison" in analysis
            assert request("POST", prefix + "/exports", json={"expected_version_id": updated["currentVersion"]["id"]}).content.startswith(b"PK")
            checks.append("Mock rewrite, patch acceptance, stale result, explicit recheck, comparison, DOCX")
        finally:
            if document_id:
                request("DELETE", f"/api/v1/documents/{document_id}", 204)
                request("GET", f"/api/v1/documents/{document_id}", 404)
            if token:
                request("POST", "/api/v1/billing/test/plan", 204, json={"plan": "free"})
                request("POST", "/api/v1/auth/logout", 204)
                request("GET", "/api/v1/documents", 401)
        checks.append("document deletion, simulated downgrade and session revocation")
    return checks


def verify_empty_and_remove_smoke_db(run_dir: Path) -> None:
    # This database is newly generated by smoke, never the interactive staging DB.
    if not inside_staging(run_dir) or not run_dir.name.startswith("smoke-"):
        raise StagingError("Refusing cleanup outside the dedicated synthetic smoke run")
    database = run_dir / "paperlight.db"
    with closing(sqlite3.connect(database)) as connection:
        for table in ("documents", "document_versions", "analysis_runs", "rewrite_sessions", "patches", "jobs", "sessions"):
            if connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] != 0:
                raise StagingError("Synthetic document/session cleanup failed; inspect the isolated run")
        if connection.execute("SELECT COUNT(*) FROM provider_usage_events").fetchone()[0] != 0:
            raise StagingError("Unexpected external provider usage in local staging")
    objects = run_dir / "objects"
    if any(path.is_file() for path in objects.rglob("*")):
        raise StagingError("Synthetic object cleanup failed")
    # Remove only these known disposable DB files; never credentials or user files.
    for suffix in ("", "-wal", "-shm", "-journal"):
        (run_dir / ("paperlight.db" + suffix)).unlink(missing_ok=True)
    for directory in sorted((item for item in objects.rglob("*") if item.is_dir()), key=lambda item: len(item.parts), reverse=True):
        directory.rmdir()
    objects.rmdir()
    run_dir.rmdir()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "serve", "smoke"))
    parser.add_argument("--preview-seconds", type=int, default=0,
                        help="After smoke cleanup in-app, retain the signed-out login screen briefly for visual QA")
    args = parser.parse_args()
    if args.command == "build":
        build_site()
        return
    if args.command == "serve":
        password = getpass("Choose a separate LOCAL TEST password (12+ characters; never use your production password): ")
        if len(password) < 12 or password != getpass("Confirm LOCAL TEST password: "):
            raise StagingError("Local password is too short or does not match")
        with running_stage(STAGING_ROOT / "local", password):
            print(f"Local staging: {WEB_ORIGIN}{BASE_PATH}/ | owner: {OWNER}")
            print("Mock providers and simulated billing only. Ctrl+C stops both services; local test data is retained.")
            while True:
                time.sleep(1)
    else:
        run_dir = STAGING_ROOT / ("smoke-" + uuid.uuid4().hex)
        password = secrets.token_urlsafe(24)  # Memory-only synthetic credential; never printed or persisted.
        completed = False
        try:
            with running_stage(run_dir, password):
                checks = smoke_checks(password)
                completed = True
                print("Staging smoke passed: " + "; ".join(checks), flush=True)
                if args.preview_seconds:
                    print(f"Signed-out QA preview: {WEB_ORIGIN}{BASE_PATH}/", flush=True)
                    time.sleep(min(max(args.preview_seconds, 0), 600))
        finally:
            if completed:
                verify_empty_and_remove_smoke_db(run_dir)
        print("Cleanup verified: no synthetic documents, object files, sessions, databases, or provider calls remain.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Local staging stopped. Production was not changed.")
    except Exception as error:
        # Avoid tracing HTTP responses, secrets, environment dictionaries or paper text.
        location = traceback.extract_tb(error.__traceback__)[-1]
        print(f"Local staging failed ({type(error).__name__}, {location.name}:{location.lineno}); no secret values are included.", file=sys.stderr)
        if isinstance(error, StagingError):
            print(str(error), file=sys.stderr)
        sys.exit(1)
