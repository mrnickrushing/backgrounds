from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from .core import (
    AREAS,
    CASE_STATUSES,
    DISCREPANCY_STATUSES,
    DIMENSIONS,
    INQUIRY_STATUSES,
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


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(prog="backgrounds-workbench")
    command.add_argument("--cases-dir", help="override the ignored local cases directory")
    sub = command.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="initialize a local case workspace")
    init.add_argument("case_id")
    init.add_argument("--investigator", default="")
    init.add_argument("--target-date", default="")

    status = sub.add_parser("status", help="show progress and outstanding work")
    status.add_argument("case_id")

    set_status = sub.add_parser("set-status")
    set_status.add_argument("case_id")
    set_status.add_argument("status", choices=CASE_STATUSES)

    inquiry = sub.add_parser("add-inquiry")
    inquiry.add_argument("case_id")
    inquiry.add_argument("--area", required=True, choices=AREAS)
    inquiry.add_argument("--source-type", required=True)
    inquiry.add_argument("--source-label", required=True)
    inquiry.add_argument("--method", default="")
    inquiry.add_argument("--follow-up-due", default="")
    inquiry.add_argument("--release-required", action="store_true")
    inquiry.add_argument("--release-attached", action="store_true")

    update = sub.add_parser("update-inquiry")
    update.add_argument("case_id")
    update.add_argument("inquiry_id")
    update.add_argument("--status", required=True, choices=INQUIRY_STATUSES)
    update.add_argument("--response-summary", default="")
    update.add_argument("--follow-up-due", default="")
    update.add_argument("--release-attached", action="store_true")

    source = sub.add_parser("add-source")
    source.add_argument("case_id")
    source.add_argument("--label", required=True)
    source.add_argument("--kind", required=True)
    source.add_argument("--location", required=True, help="approved-system locator or local relative path")
    source.add_argument("--notes", default="")

    discrepancy = sub.add_parser("add-discrepancy")
    discrepancy.add_argument("case_id")
    discrepancy.add_argument("--title", required=True)
    discrepancy.add_argument("--area", required=True, choices=AREAS)
    discrepancy.add_argument("--candidate-statement", required=True)
    discrepancy.add_argument("--contrary-information", required=True)
    discrepancy.add_argument("--source-ids", nargs="*", default=[])
    discrepancy.add_argument("--dimensions", nargs="*", choices=DIMENSIONS, default=[])

    resolve = sub.add_parser("resolve-discrepancy")
    resolve.add_argument("case_id")
    resolve.add_argument("discrepancy_id")
    resolve.add_argument("--status", required=True, choices=DISCREPANCY_STATUSES)
    resolve.add_argument("--candidate-response", default="")
    resolve.add_argument("--corroboration", default="")
    resolve.add_argument("--resolution", default="")

    interview = sub.add_parser("add-interview")
    interview.add_argument("case_id")
    interview.add_argument("--kind", required=True, choices=("pre_investigatory", "field", "reference", "employer", "discrepancy", "other"))
    interview.add_argument("--date", default="")
    interview.add_argument("--participant-role", required=True)
    interview.add_argument("--notes", default="")
    interview.add_argument("--recording-locator", default="")
    interview.add_argument("--uploaded-to-esoph", action="store_true")

    section = sub.add_parser("set-section")
    section.add_argument("case_id")
    section.add_argument("--type", required=True, choices=("area", "dimension", "bias"))
    section.add_argument("--key", default="")
    section.add_argument("--narrative", required=True)
    section.add_argument("--status", choices=("not_started", "in_progress", "complete", "not_applicable"))
    section.add_argument("--source-ids", nargs="*", default=[])

    audit = sub.add_parser("audit")
    audit.add_argument("case_id")

    report = sub.add_parser("report")
    report.add_argument("case_id")
    report.add_argument("--output")

    dashboard = sub.add_parser("dashboard")
    dashboard.add_argument("--json", action="store_true")
    serve = sub.add_parser("serve", help="run the local browser workbench")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    return command


def find_item(items, item_id):
    for item in items:
        if item["id"] == item_id:
            return item
    raise WorkbenchError(f"item not found: {item_id}")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = args.cases_dir
    try:
        if args.command == "init":
            path = save_case(new_case(args.case_id, args.investigator, args.target_date), root)
            print(path)
            return 0
        if args.command == "dashboard":
            rows = []
            for path in sorted(cases_root(root).glob("*/workbench.json")):
                data = json.loads(path.read_text(encoding="utf-8"))
                result = audit_case(data)
                rows.append({"case_id": data["case_id"], "status": data["status"], "target_date": data["target_date"], **result["metrics"]})
            if args.json:
                print(json.dumps(rows, indent=2))
            else:
                print("CASE\tSTATUS\tAREAS\tOPEN INQUIRIES\tOPEN DISCREPANCIES\tTARGET")
                for row in rows:
                    print(f"{row['case_id']}\t{row['status']}\t{row['areas_complete']}/{row['areas_total']}\t{row['open_inquiries']}\t{row['open_discrepancies']}\t{row['target_date'] or '-'}")
            return 0
        if args.command == "serve":
            from .web import serve
            serve(args.host, args.port, root)
            return 0

        data = load_case(args.case_id, root)
        if args.command == "status":
            print(json.dumps({"case_id": data["case_id"], "status": data["status"], **audit_case(data)}, indent=2))
            return 0
        if args.command == "set-status":
            data["status"] = args.status
            append_activity(data, "case_status_changed", args.status)
        elif args.command == "add-inquiry":
            if args.follow_up_due:
                date.fromisoformat(args.follow_up_due)
            item = {"id": next_id(data["inquiries"], "INQ"), "area": args.area, "source_type": args.source_type, "source_label": args.source_label, "method": args.method, "status": "planned", "created_at": utc_now(), "sent_at": "", "follow_up_due": args.follow_up_due, "release_required": args.release_required, "release_attached": args.release_attached, "response_summary": ""}
            data["inquiries"].append(item)
            append_activity(data, "inquiry_added", item["id"])
            print(item["id"])
        elif args.command == "update-inquiry":
            item = find_item(data["inquiries"], args.inquiry_id)
            item["status"] = args.status
            if args.status == "sent" and not item["sent_at"]:
                item["sent_at"] = utc_now()
            if args.response_summary:
                item["response_summary"] = args.response_summary
            if args.follow_up_due:
                date.fromisoformat(args.follow_up_due)
                item["follow_up_due"] = args.follow_up_due
            if args.release_attached:
                item["release_attached"] = True
            append_activity(data, "inquiry_updated", item["id"])
        elif args.command == "add-source":
            item = {"id": next_id(data["sources"], "SRC"), "label": args.label, "kind": args.kind, "location": args.location, "notes": args.notes, "created_at": utc_now()}
            data["sources"].append(item)
            append_activity(data, "source_added", item["id"])
            print(item["id"])
        elif args.command == "add-discrepancy":
            item = {"id": next_id(data["discrepancies"], "DSC"), "title": args.title, "area": args.area, "candidate_statement": args.candidate_statement, "contrary_information": args.contrary_information, "source_ids": args.source_ids, "dimensions": args.dimensions, "status": "open", "candidate_response": "", "corroboration": "", "resolution": "", "created_at": utc_now()}
            data["discrepancies"].append(item)
            append_activity(data, "discrepancy_added", item["id"])
            print(item["id"])
        elif args.command == "resolve-discrepancy":
            item = find_item(data["discrepancies"], args.discrepancy_id)
            item.update(status=args.status, candidate_response=args.candidate_response or item["candidate_response"], corroboration=args.corroboration or item["corroboration"], resolution=args.resolution or item["resolution"])
            append_activity(data, "discrepancy_updated", item["id"])
        elif args.command == "add-interview":
            if args.date:
                date.fromisoformat(args.date)
            item = {"id": next_id(data["interviews"], "INT"), "kind": args.kind, "date": args.date or date.today().isoformat(), "participant_role": args.participant_role, "notes": args.notes, "recording_locator": args.recording_locator, "uploaded_to_esoph": args.uploaded_to_esoph, "created_at": utc_now()}
            data["interviews"].append(item)
            append_activity(data, "interview_added", item["id"])
            print(item["id"])
        elif args.command == "set-section":
            if args.type == "area":
                if args.key not in AREAS:
                    raise WorkbenchError("area section requires a valid --key")
                target = data["areas"][args.key]
                if args.status:
                    target["status"] = args.status
            elif args.type == "dimension":
                if args.key not in DIMENSIONS:
                    raise WorkbenchError("dimension section requires a valid --key")
                target = data["dimensions"][args.key]
            else:
                target = data["bias_relevant_findings"]
            target["narrative"] = args.narrative
            target["source_ids"] = args.source_ids
            append_activity(data, "section_updated", f"{args.type}:{args.key or 'bias'}")
        elif args.command == "audit":
            result = audit_case(data)
            print(json.dumps(result, indent=2))
            return 0 if result["ready"] else 2
        elif args.command == "report":
            text = render_report(data)
            if args.output:
                output = Path(args.output)
                output.write_text(text, encoding="utf-8")
                print(output)
            else:
                print(text, end="")
            return 0
        save_case(data, root)
        return 0
    except (WorkbenchError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
