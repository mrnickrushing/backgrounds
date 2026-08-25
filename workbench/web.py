from __future__ import annotations

import argparse
import json
import mimetypes
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .core import (
    AREAS,
    AREA_LABELS,
    CASE_STATUSES,
    DIMENSIONS,
    DIMENSION_LABELS,
    WorkbenchError,
    append_activity,
    audit_case,
    cases_root,
    load_case,
    new_case,
    next_id,
    render_report,
    save_case,
    utc_now,
)

STATIC_ROOT = Path(__file__).with_name("static")


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

    def log_message(self, format, *args):
        if getattr(self.server, "quiet", False):  # type: ignore[attr-defined]
            return
        super().log_message(format, *args)

    def do_GET(self):
        try:
            path = urlparse(self.path).path
            if path == "/api/meta":
                return self.send_json({"areas": AREA_LABELS, "dimensions": DIMENSION_LABELS, "case_statuses": CASE_STATUSES})
            if path == "/api/cases":
                cases = []
                for item in sorted(cases_root(self.data_root).glob("*/workbench.json")):
                    try:
                        cases.append(case_summary(json.loads(item.read_text(encoding="utf-8"))))
                    except (OSError, ValueError, KeyError):
                        continue
                return self.send_json(cases)
            parts = self.api_parts(path)
            if len(parts) >= 2 and parts[0] == "cases":
                data = load_case(parts[1], self.data_root)
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
            body = self.read_json()
            if path == "/api/cases":
                data = new_case(body.get("case_id", ""), body.get("investigator", ""), body.get("target_date", ""))
                save_case(data, self.data_root)
                return self.send_json({**data, "audit": audit_case(data)}, HTTPStatus.CREATED)
            parts = self.api_parts(path)
            if len(parts) != 3 or parts[0] != "cases":
                return self.send_json({"error": "unknown endpoint"}, HTTPStatus.NOT_FOUND)
            data = load_case(parts[1], self.data_root)
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
            save_case(data, self.data_root)
            self.send_json(item, HTTPStatus.CREATED)
        except (WorkbenchError, ValueError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_PATCH(self):
        try:
            parts = self.api_parts(urlparse(self.path).path)
            if len(parts) < 2 or parts[0] != "cases":
                return self.send_json({"error": "unknown endpoint"}, HTTPStatus.NOT_FOUND)
            body = self.read_json()
            data = load_case(parts[1], self.data_root)
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
            save_case(data, self.data_root)
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

    def send_json(self, value, status=HTTPStatus.OK):
        payload = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_text(self, value, content_type, status=HTTPStatus.OK):
        payload = value.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_static(self, path):
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
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def serve(host="127.0.0.1", port=8765, data_root=None, quiet=False):
    server = ThreadingHTTPServer((host, port), WorkbenchHandler)
    server.data_root = data_root
    server.quiet = quiet
    print(f"Investigator Workbench: http://{host}:{server.server_port}")
    print(f"Case data: {cases_root(data_root)}")
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
