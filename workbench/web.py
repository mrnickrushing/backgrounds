from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import mimetypes
import os
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from .core import (
    AREAS,
    AREA_LABELS,
    CASE_STATUSES,
    DIMENSIONS,
    DIMENSION_LABELS,
    WorkbenchError,
    append_activity,
    audit_case,
    new_case,
    next_id,
    render_report,
    utc_now,
)
from .security import verify_totp
from .store import WorkbenchStore

STATIC_ROOT = Path(__file__).with_name("static")


def create_session(secret, issued_at=None):
    timestamp = str(int(issued_at if issued_at is not None else time.time()))
    signature = hmac.new(secret.encode(), timestamp.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{timestamp}.{signature}".encode()).decode()


def valid_session(token, secret, now=None, max_age=43_200):
    if not token or not secret:
        return False
    try:
        timestamp, signature = base64.urlsafe_b64decode(token.encode()).decode().split(".", 1)
        issued_at = int(timestamp)
    except (ValueError, UnicodeDecodeError):
        return False
    expected = hmac.new(secret.encode(), timestamp.encode(), hashlib.sha256).hexdigest()
    current = int(now if now is not None else time.time())
    return hmac.compare_digest(signature, expected) and 0 <= current - issued_at <= max_age


def case_summary(data):
    audit = audit_case(data)
    return {
        "case_id": data["case_id"],
        "investigator": data["investigator"],
        "status": data["status"],
        "target_date": data["target_date"],
        "updated_at": data["updated_at"],
        **audit["metrics"],
    }


class WorkbenchHandler(BaseHTTPRequestHandler):
    server_version = "BackgroundsWorkbench/0.1"

    @property
    def data_root(self):
        return self.server.data_root  # type: ignore[attr-defined]

    @property
    def store(self):
        return self.server.store  # type: ignore[attr-defined]

    def log_message(self, format, *args):
        if getattr(self.server, "quiet", False):  # type: ignore[attr-defined]
            return
        super().log_message(format, *args)

    def do_GET(self):
        try:
            path = urlparse(self.path).path
            if path == "/healthz":
                return self.send_json({"status": "ok"})
            if path == "/login":
                if self.is_authenticated():
                    return self.redirect("/")
                return self.send_login("Invalid username or password." if "error=1" in self.path else "")
            if path == "/login.css":
                return self.send_static(path)
            if not self.require_auth(path):
                return
            if path == "/api/me":
                user = self.current_user()
                return self.send_json({key: user.get(key) for key in ("id", "username", "display_name", "role")})
            if path == "/api/users":
                if not self.require_role("admin"):
                    return
                return self.send_json(self.store.list_users())
            if path == "/api/audit":
                if not self.require_role("admin", "supervisor"):
                    return
                return self.send_json(self.store.audit_events(limit=200))
            if path == "/api/meta":
                return self.send_json({"areas": AREA_LABELS, "dimensions": DIMENSION_LABELS, "case_statuses": CASE_STATUSES})
            if path == "/api/cases":
                cases = [case_summary(item) for item in self.store.list_cases()]
                return self.send_json(cases)
            parts = self.api_parts(path)
            if len(parts) >= 2 and parts[0] == "cases":
                data = self.store.load_case(parts[1])
                if len(parts) == 2:
                    return self.send_json({**data, "audit": audit_case(data)})
                if len(parts) == 3 and parts[2] == "report":
                    return self.send_text(render_report(data), "text/markdown; charset=utf-8")
            return self.send_static(path)
        except WorkbenchError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self.send_json({"error": f"request failed: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self):
        try:
            path = urlparse(self.path).path
            if path == "/login":
                return self.login()
            if path == "/logout":
                return self.logout()
            if not self.require_auth(path):
                return
            body = self.read_json()
            if path == "/api/users":
                if not self.require_role("admin"):
                    return
                user = self.store.create_user(body.get("username", ""), body.get("display_name", ""), body.get("password", ""), body.get("role", "investigator"), body.get("totp_secret", ""))
                self.store.audit(self.current_user(), "user_created", detail=f"{user['username']}:{user['role']}", ip=self.client_address[0])
                return self.send_json(user, HTTPStatus.CREATED)
            if path == "/api/change-password":
                user = self.current_user()
                self.store.change_password(user["id"], body.get("current_password", ""), body.get("new_password", ""))
                self.store.audit(user, "password_changed", ip=self.client_address[0])
                return self.send_json({"status": "password changed; sign in again"})
            if path == "/api/backups":
                if not self.require_role("admin"):
                    return
                target = self.store.backup()
                self.store.audit(self.current_user(), "backup_created", detail=target.name, ip=self.client_address[0])
                return self.send_json({"status": "ok", "file": target.name}, HTTPStatus.CREATED)
            if not self.require_role("admin", "supervisor", "investigator"):
                return
            if path == "/api/cases":
                data = new_case(body.get("case_id", ""), body.get("investigator", ""), body.get("target_date", ""))
                self.store.save_case(data, self.current_user(), "case_created")
                return self.send_json({**data, "audit": audit_case(data)}, HTTPStatus.CREATED)
            parts = self.api_parts(path)
            if len(parts) != 3 or parts[0] != "cases":
                return self.send_json({"error": "unknown endpoint"}, HTTPStatus.NOT_FOUND)
            data = self.store.load_case(parts[1])
            resource = parts[2]
            if resource == "inquiries":
                if body.get("area") not in AREAS:
                    raise WorkbenchError("invalid investigation area")
                item = {
                    "id": next_id(data["inquiries"], "INQ"), "area": body["area"],
                    "source_type": body.get("source_type", ""), "source_label": body.get("source_label", ""),
                    "method": body.get("method", ""), "status": "planned", "created_at": utc_now(), "sent_at": "",
                    "follow_up_due": body.get("follow_up_due", ""), "release_required": bool(body.get("release_required")),
                    "release_attached": bool(body.get("release_attached")), "response_summary": "",
                }
                if not item["source_type"] or not item["source_label"]:
                    raise WorkbenchError("source type and label are required")
                data["inquiries"].append(item)
                append_activity(data, "inquiry_added", item["id"])
            elif resource == "discrepancies":
                if body.get("area") not in AREAS:
                    raise WorkbenchError("invalid investigation area")
                item = {
                    "id": next_id(data["discrepancies"], "DSC"), "title": body.get("title", ""), "area": body["area"],
                    "candidate_statement": body.get("candidate_statement", ""), "contrary_information": body.get("contrary_information", ""),
                    "source_ids": body.get("source_ids", []), "dimensions": body.get("dimensions", []), "status": "open",
                    "candidate_response": "", "corroboration": "", "resolution": "", "created_at": utc_now(),
                }
                if not all((item["title"], item["candidate_statement"], item["contrary_information"])):
                    raise WorkbenchError("title and both accounts are required")
                data["discrepancies"].append(item)
                append_activity(data, "discrepancy_added", item["id"])
            elif resource == "interviews":
                item = {
                    "id": next_id(data["interviews"], "INT"), "kind": body.get("kind", "other"), "date": body.get("date", ""),
                    "participant_role": body.get("participant_role", ""), "notes": body.get("notes", ""),
                    "recording_locator": body.get("recording_locator", ""), "uploaded_to_esoph": bool(body.get("uploaded_to_esoph")),
                    "created_at": utc_now(),
                }
                if not item["date"] or not item["participant_role"]:
                    raise WorkbenchError("date and participant role are required")
                data["interviews"].append(item)
                append_activity(data, "interview_added", item["id"])
            elif resource == "sources":
                item = {
                    "id": next_id(data["sources"], "SRC"), "label": body.get("label", ""), "kind": body.get("kind", ""),
                    "location": body.get("location", ""), "notes": body.get("notes", ""), "created_at": utc_now(),
                }
                if not all((item["label"], item["kind"], item["location"])):
                    raise WorkbenchError("label, kind, and locator are required")
                data["sources"].append(item)
                append_activity(data, "source_added", item["id"])
            else:
                return self.send_json({"error": "unknown endpoint"}, HTTPStatus.NOT_FOUND)
            self.store.save_case(data, self.current_user(), f"{resource.rstrip('s')}_added", detail=item["id"])
            self.send_json(item, HTTPStatus.CREATED)
        except (WorkbenchError, ValueError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_PATCH(self):
        try:
            if not self.require_auth(urlparse(self.path).path):
                return
            if not self.require_role("admin", "supervisor", "investigator"):
                return
            parts = self.api_parts(urlparse(self.path).path)
            if len(parts) < 2 or parts[0] != "cases":
                return self.send_json({"error": "unknown endpoint"}, HTTPStatus.NOT_FOUND)
            body = self.read_json()
            data = self.store.load_case(parts[1])
            if len(parts) == 2:
                if "status" in body:
                    if body["status"] not in CASE_STATUSES:
                        raise WorkbenchError("invalid case status")
                    data["status"] = body["status"]
                if "target_date" in body:
                    data["target_date"] = body["target_date"]
                append_activity(data, "case_updated", "Case details updated")
            elif len(parts) == 4 and parts[2] == "inquiries":
                item = self.find_item(data["inquiries"], parts[3])
                for key in ("status", "response_summary", "follow_up_due", "release_attached"):
                    if key in body:
                        item[key] = body[key]
                if item["status"] == "sent" and not item["sent_at"]:
                    item["sent_at"] = utc_now()
                append_activity(data, "inquiry_updated", item["id"])
            elif len(parts) == 4 and parts[2] == "discrepancies":
                item = self.find_item(data["discrepancies"], parts[3])
                for key in ("status", "candidate_response", "corroboration", "resolution"):
                    if key in body:
                        item[key] = body[key]
                append_activity(data, "discrepancy_updated", item["id"])
            elif len(parts) == 4 and parts[2] in {"areas", "dimensions"}:
                collection = data[parts[2]]
                if parts[3] not in collection:
                    raise WorkbenchError("unknown report section")
                collection[parts[3]]["narrative"] = body.get("narrative", collection[parts[3]]["narrative"])
                collection[parts[3]]["source_ids"] = body.get("source_ids", collection[parts[3]]["source_ids"])
                if parts[2] == "areas" and "status" in body:
                    collection[parts[3]]["status"] = body["status"]
                append_activity(data, "section_updated", f"{parts[2]}:{parts[3]}")
            elif len(parts) == 3 and parts[2] == "bias":
                data["bias_relevant_findings"]["narrative"] = body.get("narrative", data["bias_relevant_findings"]["narrative"])
                data["bias_relevant_findings"]["source_ids"] = body.get("source_ids", data["bias_relevant_findings"]["source_ids"])
                append_activity(data, "section_updated", "bias_relevant_findings")
            else:
                return self.send_json({"error": "unknown endpoint"}, HTTPStatus.NOT_FOUND)
            self.store.save_case(data, self.current_user(), "case_updated")
            self.send_json({**data, "audit": audit_case(data)})
        except WorkbenchError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    @staticmethod
    def find_item(items, item_id):
        for item in items:
            if item["id"] == item_id:
                return item
        raise WorkbenchError(f"item not found: {item_id}")

    @staticmethod
    def api_parts(path):
        return [unquote(item) for item in path.removeprefix("/api/").split("/") if item]

    def read_json(self):
        length = int(self.headers.get("content-length", "0"))
        if length > 1_000_000:
            raise WorkbenchError("request too large")
        return json.loads(self.rfile.read(length) or b"{}")

    def session_token(self):
        for part in self.headers.get("Cookie", "").split(";"):
            if "=" in part:
                key, value = part.strip().split("=", 1)
                if key == "workbench_session":
                    return value
        return ""

    def current_user(self):
        username = getattr(self.server, "auth_username", "")  # type: ignore[attr-defined]
        password = getattr(self.server, "auth_password", "")  # type: ignore[attr-defined]
        if not username or not password:
            return {"id": None, "username": "local", "role": "admin"}
        return self.store.session_user(self.session_token())

    def is_authenticated(self):
        return bool(self.current_user())

    def require_auth(self, path):
        if self.is_authenticated():
            return True
        if path.startswith("/api/"):
            self.send_json({"error": "authentication required"}, HTTPStatus.UNAUTHORIZED)
        else:
            self.redirect("/login")
        return False

    def require_role(self, *roles):
        user = self.current_user()
        if user and user.get("role") in roles:
            return True
        self.send_json({"error": "insufficient permissions"}, HTTPStatus.FORBIDDEN)
        return False

    def login(self):
        length = min(int(self.headers.get("content-length", "0")), 16_384)
        form = parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
        supplied_username = form.get("username", [""])[0]
        supplied_password = form.get("password", [""])[0]
        supplied_totp = form.get("totp", [""])[0]
        ip = self.client_address[0]
        if self.store.login_blocked(supplied_username, ip):
            self.store.audit(None, "login_throttled", detail=supplied_username, ip=ip)
            return self.redirect("/login?error=1")
        user = self.store.authenticate(supplied_username, supplied_password)
        valid = bool(user) and verify_totp(user.get("totp_secret", ""), supplied_totp)
        self.store.record_login(supplied_username, ip, valid, user if valid else None)
        if not valid or not user:
            return self.redirect("/login?error=1")
        token = self.store.create_session(user["id"], ip, self.headers.get("User-Agent", ""))
        secure = "; Secure" if self.headers.get("X-Forwarded-Proto", "").lower() == "https" else ""
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/")
        self.send_header("Set-Cookie", f"workbench_session={token}; Path=/; Max-Age=43200; HttpOnly; SameSite=Strict{secure}")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def logout(self):
        user = self.current_user()
        self.store.revoke_session(self.session_token())
        self.store.audit(user, "logout", ip=self.client_address[0])
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/login")
        self.send_header("Set-Cookie", "workbench_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def redirect(self, location):
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def send_login(self, error=""):
        error_html = f'<p class="login-error" role="alert">{error}</p>' if error else ""
        html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sign in · Investigator Workbench</title><link rel="stylesheet" href="/login.css"></head><body class="login-page"><main class="login-card"><div class="login-mark">IW</div><p class="eyebrow">Secure workspace</p><h1>Investigator Workbench</h1><p class="login-intro">Sign in to access your protected caseload.</p>{error_html}<form method="post" action="/login"><label>Username<input name="username" autocomplete="username" required autofocus></label><label>Password<input name="password" type="password" autocomplete="current-password" required></label><label>Authenticator code <span class="optional">if enabled</span><input name="totp" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{{6}}" maxlength="6"></label><button type="submit">Sign in</button></form><p class="login-note">Authorized access only · Sessions lock after 30 minutes idle</p></main></body></html>'''
        self.send_text(html, "text/html; charset=utf-8")

    def send_json(self, value, status=HTTPStatus.OK):
        payload = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_text(self, value, content_type, status=HTTPStatus.OK):
        payload = value.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_static(self, path):
        if path == "/login.css":
            target = STATIC_ROOT / "login.css"
        else:
            relative = "index.html" if path in {"/", ""} else path.lstrip("/")
            target = (STATIC_ROOT / relative).resolve()
        if STATIC_ROOT.resolve() not in target.parents and target != STATIC_ROOT.resolve():
            return self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        if not target.is_file():
            target = STATIC_ROOT / "index.html"
        payload = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(target)[0] or "application/octet-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def serve(host="127.0.0.1", port=8765, data_root=None, quiet=False):
    server = ThreadingHTTPServer((host, port), WorkbenchHandler)
    server.data_root = data_root
    server.store = WorkbenchStore(data_root)
    server.quiet = quiet
    server.auth_username = os.environ.get("WORKBENCH_USERNAME", "")
    server.auth_password = os.environ.get("WORKBENCH_PASSWORD", "")
    server.session_secret = os.environ.get("WORKBENCH_SESSION_SECRET", "")
    if bool(server.auth_username) != bool(server.auth_password):
        raise RuntimeError("WORKBENCH_USERNAME and WORKBENCH_PASSWORD must both be set")
    if server.auth_username and len(server.session_secret) < 32:
        raise RuntimeError("WORKBENCH_SESSION_SECRET must be at least 32 characters when authentication is enabled")
    server.store.ensure_bootstrap_user(server.auth_username, server.auth_password, os.environ.get("WORKBENCH_TOTP_SECRET", ""))
    print(f"Investigator Workbench: http://{host}:{server.server_port}")
    print(f"Case data: {server.store.root}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the local Investigator Workbench")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--cases-dir")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    serve(args.host, args.port, args.cases_dir, args.quiet)


if __name__ == "__main__":
    main()
