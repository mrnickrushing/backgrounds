from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import mimetypes
import os
import time
import threading
import uuid
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from .core import (
    AREAS,
    AREA_LABELS,
    AREA_STATUSES,
    CASE_STATUSES,
    DOCUMENT_STATUSES,
    DIMENSIONS,
    DIMENSION_LABELS,
    INTERVIEW_PLAN_STATUSES,
    INTERVIEW_PLAN_STATUS_LABELS,
    build_inquiries_from_templates,
    daily_queue,
    inquiry_template_preview,
    template_lookup,
    TIMELINE_CATEGORIES,
    WorkbenchError,
    append_activity,
    audit_case,
    command_center,
    normalize_case,
    new_case,
    next_id,
    render_report,
    utc_now,
    validate_case_package,
)
from .security import new_totp_secret, verify_totp
from .store import WorkbenchStore
from .exports import docx_export, html_report, json_export, pdf_export

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
    overdue = sum(1 for item in data["inquiries"] if item.get("follow_up_due") and item["status"] not in {"received", "declined", "not_applicable"} and item["follow_up_due"] < __import__("datetime").date.today().isoformat())
    return {
        "case_id": data["case_id"],
        "investigator": data["investigator"],
        "status": data["status"],
        "target_date": data["target_date"],
        "updated_at": data["updated_at"],
        "priority": data.get("priority", "normal"),
        "tags": data.get("tags", []),
        "review_status": data.get("review", {}).get("status", "not_submitted"),
        "overdue_follow_ups": overdue,
        "timeline_items": len(data.get("timeline", [])),
        "document_items": len(data.get("documents", [])),
        "open_documents": sum(1 for item in data.get("documents", []) if item.get("status") in {"needed", "requested", "returned"}),
        "open_phs_changes": sum(1 for item in data.get("phs_changes", []) if not str(item.get("disposition", "")).strip()),
        "assigned_user_id": data.get("record_meta", {}).get("assigned_user_id"),
        "supervisor_user_id": data.get("record_meta", {}).get("supervisor_user_id"),
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
        entry = {"at": utc_now(), "request_id": self.request_id(), "ip": self.client_address[0], "method": self.command, "path": urlparse(self.path).path, "message": format % args}
        print(json.dumps(entry, separators=(",", ":")))

    def request_id(self):
        if not hasattr(self, "_request_id"):
            self._request_id = self.headers.get("X-Request-ID", "")[:80] or uuid.uuid4().hex
        return self._request_id

    def do_GET(self):
        try:
            path = urlparse(self.path).path
            if path == "/healthz":
                return self.send_json({"status": "ok", "version": getattr(self.server, "version", "dev")})
            if path == "/readyz":
                health = self.store.health()
                return self.send_json({"status": "ready" if health["database"] == "ok" else "degraded", "database": health["database"], "version": getattr(self.server, "version", "dev")}, HTTPStatus.OK if health["database"] == "ok" else HTTPStatus.SERVICE_UNAVAILABLE)
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
            if path == "/api/notifications":
                return self.send_json(self.store.notifications(self.current_user()["id"]))
            if path == "/api/system":
                if not self.require_role("admin"):
                    return
                return self.send_json({**self.store.health(), "version": getattr(self.server, "version", "dev")})
            if path == "/api/templates":
                return self.send_json({
                    "inquiries": [dict(template) for template in template_lookup().values()],
                    "interview_plans": [
                        {"id": "pre_investigatory", "label": "Pre-Investigatory Interview packet"},
                        {"id": "discrepancy", "label": "Discrepancy clarification packet"},
                        {"id": "reference", "label": "Reference verification packet"},
                        {"id": "employer", "label": "Employment verification packet"},
                    ],
                    "interviews": ["Pre-Investigatory Interview", "Employment verification", "Reference interview", "Discrepancy clarification"],
                    "timeline": ["Employment history", "Residence history", "Education history", "Military history"],
                    "documents": ["Release form", "Employment verification", "Education records", "Court document"],
                })
            if path == "/api/queue":
                me = self.current_user()
                return self.send_json(command_center(self.store.list_cases(), me.get("role", "investigator")))
            if path == "/api/meta":
                return self.send_json({
                    "areas": AREA_LABELS,
                    "dimensions": DIMENSION_LABELS,
                    "case_statuses": CASE_STATUSES,
                    "timeline_categories": {key: key.replace("_", " ").title() for key in TIMELINE_CATEGORIES},
                    "document_statuses": {key: key.replace("_", " ").title() for key in DOCUMENT_STATUSES},
                    "interview_plan_statuses": INTERVIEW_PLAN_STATUS_LABELS,
                })
            if path == "/api/cases":
                query = parse_qs(urlparse(self.path).query)
                cases = [case_summary(item) for item in self.store.list_cases(query.get("archived", [""])[0] == "1")]
                search = query.get("q", [""])[0].strip().lower()
                status_filter = query.get("status", [""])[0]
                due_filter = query.get("due", [""])[0]
                if search:
                    cases = [item for item in cases if search in " ".join((item["case_id"], item["investigator"], " ".join(item["tags"]))).lower()]
                if status_filter:
                    cases = [item for item in cases if item["status"] == status_filter]
                if due_filter == "overdue":
                    cases = [item for item in cases if item["overdue_follow_ups"]]
                return self.send_json(cases)
            parts = self.api_parts(path)
            if len(parts) >= 2 and parts[0] == "cases":
                data = self.store.load_case(parts[1])
                if len(parts) == 2:
                    return self.send_json({**data, "audit": audit_case(data)})
                if len(parts) == 3 and parts[2] == "report":
                    report_format = parse_qs(urlparse(self.path).query).get("format", ["html"])[0]
                    self.store.audit(self.current_user(), "report_previewed", data["case_id"], report_format, self.client_address[0])
                    if report_format == "markdown":
                        return self.send_text(render_report(data), "text/markdown; charset=utf-8")
                    if report_format == "html":
                        return self.send_text(html_report(data), "text/html; charset=utf-8")
                    raise WorkbenchError("unsupported report format")
                if len(parts) == 3 and parts[2] == "attachments":
                    return self.send_json(self.store.attachments(data["case_id"]))
                if len(parts) == 4 and parts[2] == "attachments":
                    item, content = self.store.attachment(parts[3])
                    if item["case_id"] != data["case_id"]:
                        raise WorkbenchError("attachment not found")
                    self.store.audit(self.current_user(), "attachment_downloaded", data["case_id"], item["id"], self.client_address[0])
                    return self.send_bytes(content, item["media_type"], item["filename"], attachment=True)
                if len(parts) == 3 and parts[2] == "export":
                    export_format = parse_qs(urlparse(self.path).query).get("format", ["pdf"])[0]
                    exporters = {"pdf": (pdf_export, "application/pdf"), "docx": (docx_export, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"), "json": (json_export, "application/json")}
                    if export_format not in exporters:
                        raise WorkbenchError("unsupported export format")
                    exporter, media_type = exporters[export_format]
                    self.store.audit(self.current_user(), "case_exported", data["case_id"], export_format, self.client_address[0])
                    return self.send_bytes(exporter(data), media_type, f"{data['case_id']}.{export_format}", attachment=True)
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
            if path == "/api/mfa/setup":
                return self.send_json({"secret": new_totp_secret(), "account": self.current_user().get("username", "")})
            if path == "/api/mfa/enable":
                secret = body.get("secret", "")
                if len(secret) < 16 or not verify_totp(secret, body.get("code", "")):
                    raise WorkbenchError("authenticator code is invalid")
                user = self.current_user()
                self.store.enable_totp(user["id"], secret)
                self.store.audit(user, "mfa_enabled", ip=self.client_address[0])
                return self.send_json({"status": "MFA enabled"})
            if path == "/api/backups":
                if not self.require_role("admin"):
                    return
                target = self.store.backup()
                self.store.audit(self.current_user(), "backup_created", detail=target.name, ip=self.client_address[0])
                return self.send_json({"status": "ok", "file": target.name}, HTTPStatus.CREATED)
            if path == "/api/cases/import":
                if not self.require_role("admin"):
                    return
                data = validate_case_package(body.get("case"))
                try:
                    self.store.load_case(data["case_id"])
                except WorkbenchError:
                    pass
                else:
                    raise WorkbenchError("a case with that identifier already exists; imports never overwrite cases")
                append_activity(data, "case_imported", "Imported from a validated JSON case package")
                self.store.save_case(data, self.current_user(), "case_imported")
                self.store.audit(self.current_user(), "case_package_imported", data["case_id"], ip=self.client_address[0])
                return self.send_json({**data, "audit": audit_case(data)}, HTTPStatus.CREATED)
            if not self.require_role("admin", "supervisor", "investigator"):
                return
            if path == "/api/cases":
                data = new_case(body.get("case_id", ""), body.get("investigator", ""), body.get("target_date", ""))
                self.store.save_case(data, self.current_user(), "case_created")
                return self.send_json({**data, "audit": audit_case(data)}, HTTPStatus.CREATED)
            parts = self.api_parts(path)
            if len(parts) < 3 or parts[0] != "cases":
                return self.send_json({"error": "unknown endpoint"}, HTTPStatus.NOT_FOUND)
            data = self.store.load_case(parts[1])
            resource = parts[2]
            if resource == "attachments":
                try:
                    content = base64.b64decode(body.get("content_base64", ""), validate=True)
                except ValueError as exc:
                    raise WorkbenchError("attachment content is not valid base64") from exc
                item = self.store.save_attachment(data["case_id"], body.get("filename", ""), body.get("media_type", ""), content, self.current_user())
                return self.send_json(item, HTTPStatus.CREATED)
            if resource == "inquiries" and len(parts) == 4 and parts[3] == "batch":
                template_ids = body.get("template_ids", [])
                if not isinstance(template_ids, list) or not template_ids:
                    raise WorkbenchError("template_ids must be a non-empty list")
                follow_up_due = str(body.get("follow_up_due", ""))
                preview = inquiry_template_preview(template_ids, follow_up_due)
                if not preview:
                    raise WorkbenchError("no valid templates selected")
                created = build_inquiries_from_templates(data, template_ids, follow_up_due)
                if not created:
                    raise WorkbenchError("selected templates are already represented")
                for item in created:
                    data["inquiries"].append(item)
                    append_activity(data, "inquiry_added", f"{item['id']} from {item.get('template_id', 'template')}")
                self.store.save_case(data, self.current_user(), "case_updated")
                return self.send_json({"created": created, "preview": preview}, HTTPStatus.CREATED)
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
            elif resource == "timeline":
                if body.get("category", "other") not in TIMELINE_CATEGORIES:
                    raise WorkbenchError("invalid timeline category")
                if body.get("source_ids", []) and not isinstance(body.get("source_ids"), list):
                    raise WorkbenchError("timeline source identifiers must be a list")
                item = {
                    "id": next_id(data["timeline"], "TIM"),
                    "category": body.get("category", "other"),
                    "label": body.get("label", ""),
                    "start_date": body.get("start_date", ""),
                    "end_date": body.get("end_date", ""),
                    "source_ids": body.get("source_ids", []),
                    "notes": body.get("notes", ""),
                    "created_at": date.today().isoformat(),
                    "updated_at": "",
                }
                if not item["label"] or not item["start_date"]:
                    raise WorkbenchError("timeline label and start date are required")
                data["timeline"].append(item)
                append_activity(data, "timeline_added", item["id"])
            elif resource == "documents":
                if body.get("status", "needed") not in DOCUMENT_STATUSES:
                    raise WorkbenchError("invalid document status")
                if body.get("required_original") not in {None, True, False, 0, 1, ""} and not isinstance(body.get("required_original"), bool):
                    raise WorkbenchError("required_original must be a boolean")
                item = {
                    "id": next_id(data["documents"], "DOC"),
                    "title": body.get("title", ""),
                    "status": body.get("status", "needed"),
                    "due_date": body.get("due_date", ""),
                    "received_at": body.get("received_at", ""),
                    "verified_at": body.get("verified_at", ""),
                    "returned_at": body.get("returned_at", ""),
                    "source_locator": body.get("source_locator", ""),
                    "notes": body.get("notes", ""),
                    "required_original": bool(body.get("required_original")),
                    "created_at": date.today().isoformat(),
                    "updated_at": "",
                }
                if not item["title"]:
                    raise WorkbenchError("document title is required")
                today = date.today().isoformat()
                if item["status"] == "received" and not item["received_at"]:
                    item["received_at"] = today
                if item["status"] == "verified" and not item["verified_at"]:
                    item["verified_at"] = today
                if item["status"] == "returned" and not item["returned_at"]:
                    item["returned_at"] = today
                data["documents"].append(item)
                append_activity(data, "document_added", item["id"])
            elif resource == "phs-changes":
                if body.get("source_ids", []) and not isinstance(body.get("source_ids"), list):
                    raise WorkbenchError("phs source identifiers must be a list")
                item = {
                    "id": next_id(data["phs_changes"], "PHS"),
                    "field_label": body.get("field_label", ""),
                    "prior_value": body.get("prior_value", ""),
                    "current_value": body.get("current_value", ""),
                    "reported_at": body.get("reported_at", "") or date.today().isoformat(),
                    "source_ids": body.get("source_ids", []),
                    "disposition": body.get("disposition", ""),
                }
                if not item["field_label"] or item["prior_value"] == "" or item["current_value"] == "":
                    raise WorkbenchError("field label, prior value, and current value are required")
                data["phs_changes"].append(item)
                append_activity(data, "phs_change_added", item["id"])
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
            elif resource == "interview-plans":
                if body.get("source_ids", []) and not isinstance(body.get("source_ids"), list):
                    raise WorkbenchError("source identifiers must be a list")
                if body.get("discrepancy_ids", []) and not isinstance(body.get("discrepancy_ids"), list):
                    raise WorkbenchError("discrepancy identifiers must be a list")
                item = {
                    "id": next_id(data["interview_plans"], "PLN"),
                    "subject": body.get("subject", ""),
                    "question": body.get("question", ""),
                    "status": body.get("status", "planned"),
                    "notes": body.get("notes", ""),
                    "source_ids": body.get("source_ids", []),
                    "discrepancy_ids": body.get("discrepancy_ids", []),
                    "recording_locator": body.get("recording_locator", ""),
                    "created_at": utc_now(),
                    "updated_at": "",
                }
                if item["status"] not in INTERVIEW_PLAN_STATUSES:
                    raise WorkbenchError("invalid interview plan status")
                if not all((item["subject"], item["question"])):
                    raise WorkbenchError("subject and question are required")
                data["interview_plans"].append(item)
                append_activity(data, "interview_plan_added", item["id"])
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
            if urlparse(self.path).path.startswith("/api/notifications/"):
                notification_id = self.api_parts(urlparse(self.path).path)
                if len(notification_id) != 2 or notification_id[0] != "notifications":
                    return self.send_json({"error": "unknown endpoint"}, HTTPStatus.NOT_FOUND)
                self.store.mark_notification_read(notification_id[1], self.current_user()["id"])
                return self.send_json({"status": "read"})
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
                if "priority" in body:
                    if body["priority"] not in {"low", "normal", "high", "urgent"}:
                        raise WorkbenchError("invalid priority")
                    data["priority"] = body["priority"]
                if "tags" in body:
                    data["tags"] = [str(item).strip()[:40] for item in body["tags"][:20] if str(item).strip()]
                if "review_action" in body:
                    action = body["review_action"]
                    review = data.setdefault("review", {"status": "not_submitted", "submitted_at": "", "decided_at": "", "comments": []})
                    user = self.current_user()
                    if action == "submit":
                        review["status"] = "pending"
                        review["submitted_at"] = utc_now()
                        self.store.add_notification(None, data["case_id"], "review_submitted", f"{data['case_id']} was submitted for supervisory review")
                    elif action in {"approve", "return"}:
                        if user.get("role") not in {"admin", "supervisor"}:
                            return self.send_json({"error": "supervisor role required"}, HTTPStatus.FORBIDDEN)
                        review["status"] = "approved" if action == "approve" else "corrections_requested"
                        review["decided_at"] = utc_now()
                        self.store.add_notification(None, data["case_id"], "review_approved" if action == "approve" else "corrections_requested", f"{data['case_id']} was {'approved' if action == 'approve' else 'returned for correction'}")
                    else:
                        raise WorkbenchError("invalid review action")
                    if body.get("review_comment"):
                        review["comments"].append({"at": utc_now(), "by": user.get("username", ""), "text": str(body["review_comment"])[:4000]})
                meta_keys = {key: body[key] for key in ("assigned_user_id", "supervisor_user_id", "retention_date", "archived") if key in body}
                if meta_keys:
                    if self.current_user().get("role") not in {"admin", "supervisor"}:
                        return self.send_json({"error": "supervisor role required"}, HTTPStatus.FORBIDDEN)
                    self.store.update_case_meta(data["case_id"], **meta_keys)
                append_activity(data, "case_updated", "Case details updated")
            elif len(parts) == 4 and parts[2] == "inquiries":
                item = self.find_item(data["inquiries"], parts[3])
                for key in ("status", "response_summary", "follow_up_due", "release_attached"):
                    if key in body:
                        item[key] = body[key]
                if item["status"] == "sent" and not item["sent_at"]:
                    item["sent_at"] = utc_now()
                append_activity(data, "inquiry_updated", item["id"])
            elif len(parts) == 4 and parts[2] == "interview-plans":
                item = self.find_item(data["interview_plans"], parts[3])
                if "subject" in body:
                    item["subject"] = body["subject"]
                if "question" in body:
                    item["question"] = body["question"]
                if "status" in body:
                    if body["status"] not in INTERVIEW_PLAN_STATUSES:
                        raise WorkbenchError("invalid interview plan status")
                    item["status"] = body["status"]
                if "notes" in body:
                    item["notes"] = body["notes"]
                if "recording_locator" in body:
                    item["recording_locator"] = body["recording_locator"]
                if "source_ids" in body:
                    if not isinstance(body["source_ids"], list):
                        raise WorkbenchError("source identifiers must be a list")
                    item["source_ids"] = body["source_ids"]
                if "discrepancy_ids" in body:
                    if not isinstance(body["discrepancy_ids"], list):
                        raise WorkbenchError("discrepancy identifiers must be a list")
                    item["discrepancy_ids"] = body["discrepancy_ids"]
                if not all((item.get("subject", ""), item.get("question", ""))):
                    raise WorkbenchError("subject and question are required")
                item["updated_at"] = utc_now()
                append_activity(data, "interview_plan_updated", item["id"])
            elif len(parts) == 4 and parts[2] == "discrepancies":
                item = self.find_item(data["discrepancies"], parts[3])
                for key in ("status", "candidate_response", "corroboration", "resolution"):
                    if key in body:
                        item[key] = body[key]
                append_activity(data, "discrepancy_updated", item["id"])
            elif len(parts) == 4 and parts[2] == "timeline":
                item = self.find_item(data["timeline"], parts[3])
                if "category" in body:
                    if body["category"] not in TIMELINE_CATEGORIES:
                        raise WorkbenchError("invalid timeline category")
                    item["category"] = body["category"]
                for key in ("label", "start_date", "end_date", "notes"):
                    if key in body:
                        item[key] = body[key]
                if "source_ids" in body:
                    item["source_ids"] = body["source_ids"]
                item["updated_at"] = date.today().isoformat()
                append_activity(data, "timeline_updated", item["id"])
            elif len(parts) == 4 and parts[2] == "documents":
                item = self.find_item(data["documents"], parts[3])
                if "status" in body:
                    if body["status"] not in DOCUMENT_STATUSES:
                        raise WorkbenchError("invalid document status")
                    item["status"] = body["status"]
                for key in ("title", "due_date", "received_at", "verified_at", "returned_at", "source_locator", "notes"):
                    if key in body:
                        item[key] = body[key]
                if "required_original" in body:
                    item["required_original"] = bool(body["required_original"])
                today = date.today().isoformat()
                if item["status"] == "received" and not item.get("received_at"):
                    item["received_at"] = today
                if item["status"] == "verified" and not item.get("verified_at"):
                    item["verified_at"] = today
                if item["status"] == "returned" and not item.get("returned_at"):
                    item["returned_at"] = today
                item["updated_at"] = date.today().isoformat()
                append_activity(data, "document_updated", item["id"])
            elif len(parts) == 4 and parts[2] == "phs-changes":
                item = self.find_item(data["phs_changes"], parts[3])
                for key in ("field_label", "prior_value", "current_value", "reported_at", "disposition"):
                    if key in body:
                        item[key] = body[key]
                if "source_ids" in body:
                    if not isinstance(body["source_ids"], list):
                        raise WorkbenchError("phs source identifiers must be a list")
                    item["source_ids"] = body["source_ids"]
                if not item.get("field_label") or item.get("prior_value", "") == "" or item.get("current_value", "") == "":
                    raise WorkbenchError("field label, prior value, and current value are required")
                if not item.get("reported_at"):
                    item["reported_at"] = date.today().isoformat()
                item["updated_at"] = date.today().isoformat()
                append_activity(data, "phs_change_updated", item["id"])
            elif len(parts) == 4 and parts[2] in {"areas", "dimensions"}:
                collection = data[parts[2]]
                if parts[3] not in collection:
                    raise WorkbenchError("unknown report section")
                collection[parts[3]]["narrative"] = body.get("narrative", collection[parts[3]]["narrative"])
                collection[parts[3]]["source_ids"] = body.get("source_ids", collection[parts[3]]["source_ids"])
                if parts[2] == "areas" and "status" in body:
                    # Checked the way document status already is: this value is
                    # stored and later rendered into the caseload markup, so an
                    # unvalidated string is a stored-XSS vector, not just bad data.
                    if body["status"] not in AREA_STATUSES:
                        raise WorkbenchError("invalid area status")
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
        self.security_headers()
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
        self.security_headers()
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_bytes(self, payload, content_type, filename="download", attachment=False, status=HTTPStatus.OK):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.security_headers()
        if attachment:
            safe = quote(filename.replace('"', ""))
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{safe}")
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
        self.security_headers()
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def security_headers(self):
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("X-Request-ID", self.request_id())


def serve(host="127.0.0.1", port=8765, data_root=None, quiet=False):
    server = ThreadingHTTPServer((host, port), WorkbenchHandler)
    server.data_root = data_root
    server.store = WorkbenchStore(data_root)
    server.quiet = quiet
    server.auth_username = os.environ.get("WORKBENCH_USERNAME", "")
    server.auth_password = os.environ.get("WORKBENCH_PASSWORD", "")
    server.session_secret = os.environ.get("WORKBENCH_SESSION_SECRET", "")
    server.version = os.environ.get("RAILWAY_GIT_COMMIT_SHA", os.environ.get("WORKBENCH_VERSION", "dev"))[:12]
    if bool(server.auth_username) != bool(server.auth_password):
        raise RuntimeError("WORKBENCH_USERNAME and WORKBENCH_PASSWORD must both be set")
    if server.auth_username and len(server.session_secret) < 32:
        raise RuntimeError("WORKBENCH_SESSION_SECRET must be at least 32 characters when authentication is enabled")
    server.store.ensure_bootstrap_user(server.auth_username, server.auth_password, os.environ.get("WORKBENCH_TOTP_SECRET", ""))
    backup_stop = threading.Event()
    backup_interval = max(300, int(os.environ.get("WORKBENCH_BACKUP_INTERVAL_SECONDS", "86400")))
    backup_thread = threading.Thread(target=server.store.backup_worker, args=(backup_stop, backup_interval), daemon=True, name="workbench-backup")
    backup_thread.start()
    print(f"Investigator Workbench: http://{host}:{server.server_port}")
    print(f"Case data: {server.store.root}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        backup_stop.set()
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
