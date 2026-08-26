from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


AREAS = (
    "employment_eligibility",
    "age_verification",
    "criminal_qualification_records",
    "driving_record",
    "education",
    "employment_history",
    "relatives_references",
    "marriage_dissolution",
    "neighborhood",
    "military_history",
    "credit_records",
    "social_media",
)

AREA_LABELS = {
    "employment_eligibility": "Employment Eligibility",
    "age_verification": "Age Verification",
    "criminal_qualification_records": "Criminal and Other Qualification Records Checks - Local, State, and National",
    "driving_record": "Driving Record Check",
    "education": "Education Verification",
    "employment_history": "Employment History Checks",
    "relatives_references": "Relatives and Personal References Checks",
    "marriage_dissolution": "Dissolution of Marriage Check",
    "neighborhood": "Neighborhood Checks",
    "military_history": "Military History Check",
    "credit_records": "Credit Records Check",
    "social_media": "Social Media Check",
}

DIMENSIONS = (
    "integrity",
    "impulse_control_attention_to_safety",
    "substance_abuse_other_risk_taking",
    "stress_tolerance",
    "overcoming_adversity",
    "conscientiousness",
    "interpersonal_skills",
    "decision_making_judgment",
    "learning_ability",
    "communication_skills",
)

DIMENSION_LABELS = {
    "integrity": "Integrity",
    "impulse_control_attention_to_safety": "Impulse Control and Attention to Safety",
    "substance_abuse_other_risk_taking": "Substance Abuse and Other Risk-Taking Behavior",
    "stress_tolerance": "Stress Tolerance",
    "overcoming_adversity": "Confronting and Overcoming Problems, Obstacles, and Adversity",
    "conscientiousness": "Conscientiousness",
    "interpersonal_skills": "Interpersonal Skills",
    "decision_making_judgment": "Decision-Making and Judgment",
    "learning_ability": "Learning Ability",
    "communication_skills": "Communication Skills",
}

INQUIRY_STATUSES = ("planned", "sent", "received", "declined", "nonresponsive", "not_applicable")
DISCREPANCY_STATUSES = ("open", "candidate_response_received", "corroboration_pending", "resolved", "unresolved")
CASE_STATUSES = ("intake", "investigating", "pii_complete", "reporting", "quality_review", "closed")
TIMELINE_CATEGORIES = ("employment", "residence", "education", "military", "relationship", "legal", "other")
TIMELINE_CATEGORY_LABELS = {
    "employment": "Employment",
    "residence": "Residence",
    "education": "Education",
    "military": "Military",
    "relationship": "Relationship",
    "legal": "Legal",
    "other": "Other",
}
DOCUMENT_STATUSES = ("needed", "requested", "received", "verified", "returned", "not_applicable")
DOCUMENT_STATUS_LABELS = {
    "needed": "Needed",
    "requested": "Requested",
    "received": "Received",
    "verified": "Verified",
    "returned": "Returned",
    "not_applicable": "Not applicable",
}
INTERVIEW_PLAN_STATUSES = ("planned", "scheduled", "completed", "canceled", "held")
INTERVIEW_PLAN_STATUS_LABELS = {
    "planned": "Planned",
    "scheduled": "Scheduled",
    "completed": "Completed",
    "canceled": "Canceled",
    "held": "Held",
}
INQUIRY_TEMPLATES = (
    {
        "id": "employment_verification",
        "label": "Employment verification",
        "area": "employment_history",
        "source_type": "Employer",
        "method": "Records request",
        "release_required": True,
        "follow_up_days": 7,
    },
    {
        "id": "education_verification",
        "label": "Education verification",
        "area": "education",
        "source_type": "School or registrar",
        "method": "Records request",
        "release_required": True,
        "follow_up_days": 10,
    },
    {
        "id": "residence_verification",
        "label": "Residence verification",
        "area": "neighborhood",
        "source_type": "Landlord or resident contact",
        "method": "Address verification",
        "release_required": False,
        "follow_up_days": 5,
    },
    {
        "id": "reference_verification",
        "label": "Personal reference verification",
        "area": "relatives_references",
        "source_type": "Reference contact",
        "method": "Reference interview",
        "release_required": False,
        "follow_up_days": 5,
    },
    {
        "id": "court_record_verification",
        "label": "Court record verification",
        "area": "criminal_qualification_records",
        "source_type": "Court or records office",
        "method": "Records request",
        "release_required": False,
        "follow_up_days": 10,
    },
    {
        "id": "driving_record_verification",
        "label": "Driving record verification",
        "area": "driving_record",
        "source_type": "DMV or licensing office",
        "method": "Records request",
        "release_required": False,
        "follow_up_days": 10,
    },
)


class WorkbenchError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def validate_case_id(case_id: str) -> str:
    value = case_id.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", value):
        raise WorkbenchError("case ID must use 1-80 letters, numbers, dots, underscores, or hyphens")
    return value


def cases_root(root: str | Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    configured = os.environ.get("BACKGROUNDS_CASES_DIR")
    return Path(configured) if configured else Path(__file__).resolve().parents[1] / "cases"


def case_path(case_id: str, root: str | Path | None = None) -> Path:
    return cases_root(root) / validate_case_id(case_id) / "workbench.json"


def new_case(case_id: str, investigator: str = "", target_date: str = "") -> dict[str, Any]:
    validate_case_id(case_id)
    if target_date:
        date.fromisoformat(target_date)
    now = utc_now()
    return normalize_case({
        "schema_version": 1,
        "case_id": case_id,
        "investigator": investigator,
        "status": "intake",
        "priority": "normal",
        "tags": [],
        "target_date": target_date,
        "created_at": now,
        "updated_at": now,
        "areas": {area: {"status": "not_started", "narrative": "", "source_ids": []} for area in AREAS},
        "dimensions": {dimension: {"narrative": "", "source_ids": []} for dimension in DIMENSIONS},
        "bias_relevant_findings": {"narrative": "", "source_ids": []},
        "inquiries": [],
        "discrepancies": [],
        "interviews": [],
        "sources": [],
        "timeline": [],
        "documents": [],
        "phs_changes": [],
        "interview_plans": [],
        "review": {"status": "not_submitted", "submitted_at": "", "decided_at": "", "comments": []},
        "activity": [{"at": now, "action": "case_created", "detail": "Local workbench case initialized"}],
    })


def load_case(case_id: str, root: str | Path | None = None) -> dict[str, Any]:
    path = case_path(case_id, root)
    if not path.exists():
        raise WorkbenchError(f"case not found: {case_id}")
    with path.open("r", encoding="utf-8") as handle:
        return normalize_case(json.load(handle))


def save_case(data: dict[str, Any], root: str | Path | None = None) -> Path:
    data["updated_at"] = utc_now()
    path = case_path(data["case_id"], root)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp_name = tempfile.mkstemp(prefix=".workbench-", suffix=".json", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return path


def append_activity(data: dict[str, Any], action: str, detail: str) -> None:
    data["activity"].append({"at": utc_now(), "action": action, "detail": detail})


def next_id(items: list[dict[str, Any]], prefix: str) -> str:
    existing = {item["id"] for item in items}
    number = 1
    while f"{prefix}-{number:04d}" in existing:
        number += 1
    return f"{prefix}-{number:04d}"


def _string_list(value: Any) -> list[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def _normalize_structured_item(item: Any, defaults: dict[str, Any]) -> dict[str, Any]:
    data = dict(defaults)
    if isinstance(item, dict):
        data.update(item)
    return data


def normalize_case(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise WorkbenchError("case data must be a JSON object")
    normalized = json.loads(json.dumps(data))
    normalized["schema_version"] = int(normalized.get("schema_version", 1) or 1)
    normalized["case_id"] = str(normalized.get("case_id", "")).strip()
    if normalized["case_id"]:
        validate_case_id(normalized["case_id"])
    normalized["investigator"] = str(normalized.get("investigator", ""))
    normalized["status"] = normalized.get("status", "intake") or "intake"
    normalized["priority"] = normalized.get("priority", "normal") or "normal"
    normalized["tags"] = _string_list(normalized.get("tags", []))
    normalized["target_date"] = str(normalized.get("target_date", ""))
    normalized["created_at"] = str(normalized.get("created_at", ""))
    normalized["updated_at"] = str(normalized.get("updated_at", ""))
    normalized["areas"] = {
        key: _normalize_structured_item(normalized.get("areas", {}).get(key, {}), {"status": "not_started", "narrative": "", "source_ids": []})
        for key in AREAS
    }
    for key in AREAS:
        normalized["areas"][key]["status"] = normalized["areas"][key].get("status", "not_started") or "not_started"
        normalized["areas"][key]["narrative"] = str(normalized["areas"][key].get("narrative", ""))
        normalized["areas"][key]["source_ids"] = _string_list(normalized["areas"][key].get("source_ids", []))
    normalized["dimensions"] = {
        key: _normalize_structured_item(normalized.get("dimensions", {}).get(key, {}), {"narrative": "", "source_ids": []})
        for key in DIMENSIONS
    }
    for key in DIMENSIONS:
        normalized["dimensions"][key]["narrative"] = str(normalized["dimensions"][key].get("narrative", ""))
        normalized["dimensions"][key]["source_ids"] = _string_list(normalized["dimensions"][key].get("source_ids", []))
    normalized["bias_relevant_findings"] = _normalize_structured_item(normalized.get("bias_relevant_findings", {}), {"narrative": "", "source_ids": []})
    normalized["bias_relevant_findings"]["narrative"] = str(normalized["bias_relevant_findings"].get("narrative", ""))
    normalized["bias_relevant_findings"]["source_ids"] = _string_list(normalized["bias_relevant_findings"].get("source_ids", []))
    inquiries = []
    for item in normalized.get("inquiries", []):
        if not isinstance(item, dict):
            continue
        inquiry = {
            "id": str(item.get("id", "")).strip(),
            "area": str(item.get("area", "")),
            "source_type": str(item.get("source_type", "")),
            "source_label": str(item.get("source_label", "")),
            "method": str(item.get("method", "")),
            "status": str(item.get("status", "planned")),
            "created_at": str(item.get("created_at", "")),
            "sent_at": str(item.get("sent_at", "")),
            "follow_up_due": str(item.get("follow_up_due", "")),
            "release_required": bool(item.get("release_required")),
            "release_attached": bool(item.get("release_attached")),
            "response_summary": str(item.get("response_summary", "")),
            "template_id": str(item.get("template_id", "")),
        }
        if not inquiry["id"]:
            inquiry["id"] = next_id(inquiries, "INQ")
        if inquiry["area"] not in AREAS:
            inquiry["area"] = AREAS[0]
        if inquiry["status"] not in INQUIRY_STATUSES:
            inquiry["status"] = "planned"
        inquiries.append(inquiry)
    normalized["inquiries"] = inquiries
    normalized["discrepancies"] = [dict(item) for item in normalized.get("discrepancies", []) if isinstance(item, dict)]
    normalized["interviews"] = [dict(item) for item in normalized.get("interviews", []) if isinstance(item, dict)]
    normalized["sources"] = [dict(item) for item in normalized.get("sources", []) if isinstance(item, dict)]
    timeline_items = []
    for item in normalized.get("timeline", []):
        if not isinstance(item, dict):
            continue
        timeline_item = {
            "id": item.get("id", ""),
            "category": item.get("category", "other") if item.get("category", "other") in TIMELINE_CATEGORIES else "other",
            "label": str(item.get("label", "")).strip(),
            "start_date": str(item.get("start_date", "")),
            "end_date": str(item.get("end_date", "")),
            "source_ids": _string_list(item.get("source_ids", [])),
            "notes": str(item.get("notes", "")),
            "created_at": str(item.get("created_at", "")),
            "updated_at": str(item.get("updated_at", "")),
        }
        if not timeline_item["id"]:
            timeline_item["id"] = next_id(timeline_items, "TIM")
        timeline_items.append(timeline_item)
    normalized["timeline"] = timeline_items
    documents = []
    for item in normalized.get("documents", []):
        if not isinstance(item, dict):
            continue
        document = {
            "id": item.get("id", ""),
            "title": str(item.get("title", "")).strip(),
            "status": item.get("status", "needed") if item.get("status", "needed") in DOCUMENT_STATUSES else "needed",
            "due_date": str(item.get("due_date", "")),
            "received_at": str(item.get("received_at", "")),
            "verified_at": str(item.get("verified_at", "")),
            "returned_at": str(item.get("returned_at", "")),
            "source_locator": str(item.get("source_locator", "")),
            "notes": str(item.get("notes", "")),
            "required_original": bool(item.get("required_original")),
            "created_at": str(item.get("created_at", "")),
            "updated_at": str(item.get("updated_at", "")),
        }
        if not document["id"]:
            document["id"] = next_id(documents, "DOC")
        documents.append(document)
    normalized["documents"] = documents
    phs_changes = []
    for item in normalized.get("phs_changes", []):
        if not isinstance(item, dict):
            continue
        phs_change = {
            "id": item.get("id", "") or next_id(phs_changes, "PHS"),
            "field_label": str(item.get("field_label", "")).strip(),
            "prior_value": str(item.get("prior_value", "")),
            "current_value": str(item.get("current_value", "")),
            "reported_at": str(item.get("reported_at", "")),
            "source_ids": _string_list(item.get("source_ids", [])),
            "disposition": str(item.get("disposition", "")),
        }
        phs_changes.append(phs_change)
    normalized["phs_changes"] = phs_changes
    interview_plans = []
    for item in normalized.get("interview_plans", []):
        if not isinstance(item, dict):
            continue
        interview_plan = {
            "id": item.get("id", "") or next_id(interview_plans, "PLN"),
            "subject": str(item.get("subject", "")).strip(),
            "question": str(item.get("question", "")).strip(),
            "status": str(item.get("status", "planned")) if item.get("status", "planned") in INTERVIEW_PLAN_STATUSES else "planned",
            "notes": str(item.get("notes", "")),
            "source_ids": _string_list(item.get("source_ids", [])),
            "discrepancy_ids": _string_list(item.get("discrepancy_ids", [])),
            "recording_locator": str(item.get("recording_locator", "")),
            "created_at": str(item.get("created_at", "")),
            "updated_at": str(item.get("updated_at", "")),
        }
        interview_plans.append(interview_plan)
    normalized["interview_plans"] = interview_plans
    review = _normalize_structured_item(normalized.get("review", {}), {"status": "not_submitted", "submitted_at": "", "decided_at": "", "comments": []})
    review["status"] = str(review.get("status", "not_submitted"))
    review["submitted_at"] = str(review.get("submitted_at", ""))
    review["decided_at"] = str(review.get("decided_at", ""))
    review["comments"] = [dict(item) for item in review.get("comments", []) if isinstance(item, dict)]
    normalized["review"] = review
    normalized["activity"] = [dict(item) for item in normalized.get("activity", []) if isinstance(item, dict)]
    return normalized


def phs_findings(changes: list[dict[str, Any]]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for change in changes:
        if not isinstance(change, dict):
            continue
        field_label = change.get("field_label", "PHS field")
        change_id = change.get("id", "PHS")
        if change.get("prior_value", "") == change.get("current_value", ""):
            continue
        if not str(change.get("reported_at", "")).strip():
            findings.append({"kind": "missing_date", "message": f"Review {change_id} for {field_label}; reported date is missing."})
        if not _string_list(change.get("source_ids", [])):
            findings.append({"kind": "missing_source", "message": f"Review {change_id} for {field_label}; add a source locator."})
        if not str(change.get("disposition", "")).strip():
            findings.append({"kind": "missing_disposition", "message": f"Review {change_id} for {field_label}; add an investigator disposition."})
    return findings


def discrepancy_matrix(discrepancies: list[dict[str, Any]]) -> list[dict[str, str]]:
    matrix: list[dict[str, str]] = []
    for item in discrepancies:
        if not isinstance(item, dict):
            continue
        matrix.append({
            "id": str(item.get("id", "")),
            "title": str(item.get("title", "")),
            "area": str(item.get("area", "")),
            "candidate_statement": str(item.get("candidate_statement", "")),
            "contrary_information": str(item.get("contrary_information", "")),
            "candidate_response": str(item.get("candidate_response", "")),
            "corroboration": str(item.get("corroboration", "")),
            "resolution": str(item.get("resolution", "")),
            "status": str(item.get("status", "")),
        })
    return matrix


def template_lookup() -> dict[str, dict[str, Any]]:
    return {item["id"]: dict(item) for item in INQUIRY_TEMPLATES}


def inquiry_template_preview(template_ids: list[str], follow_up_due: str = "") -> list[dict[str, Any]]:
    templates = template_lookup()
    selected: list[dict[str, Any]] = []
    due_override = follow_up_due.strip()
    if due_override:
        date.fromisoformat(due_override)
    for template_id in template_ids:
        template = templates.get(template_id)
        if not template:
            continue
        due_date = due_override
        if not due_date:
            due_date = (date.today() + timedelta(days=int(template["follow_up_days"]))).isoformat()
        selected.append(
            {
                "template_id": template["id"],
                "label": template["label"],
                "area": template["area"],
                "source_type": template["source_type"],
                "method": template["method"],
                "release_required": bool(template["release_required"]),
                "follow_up_due": due_date,
            }
        )
    return selected


def build_inquiries_from_templates(case_data: dict[str, Any], template_ids: list[str], follow_up_due: str = "") -> list[dict[str, Any]]:
    preview = inquiry_template_preview(template_ids, follow_up_due)
    selected: list[dict[str, Any]] = []
    for item in preview:
        if any(existing.get("template_id") == item["template_id"] for existing in case_data.get("inquiries", [])):
            continue
        inquiry = {
            "id": next_id(selected, "INQ"),
            "area": item["area"],
            "source_type": item["source_type"],
            "source_label": item["label"],
            "method": item["method"],
            "status": "planned",
            "created_at": utc_now(),
            "sent_at": "",
            "follow_up_due": item["follow_up_due"],
            "release_required": item["release_required"],
            "release_attached": False,
            "response_summary": "",
            "template_id": item["template_id"],
        }
        selected.append(inquiry)
    return selected


def source_trace_map(data: dict[str, Any]) -> dict[str, Any]:
    sources: dict[str, dict[str, Any]] = {}
    orphans: set[str] = set()

    def register(source_ids: Any, reference: str) -> None:
        for source_id in _string_list(source_ids):
            if source_id in sources:
                sources[source_id]["references"].append(reference)
            else:
                orphans.add(source_id)

    for item in data.get("sources", []):
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("id", "")).strip()
        if not source_id:
            continue
        sources[source_id] = {
            "source_id": source_id,
            "label": str(item.get("label", "")).strip() or source_id,
            "kind": str(item.get("kind", "")).strip(),
            "location": str(item.get("location", "")).strip(),
            "references": [],
        }

    for key, section in data.get("dimensions", {}).items():
        if isinstance(section, dict):
            register(section.get("source_ids", []), f"POST dimension: {DIMENSION_LABELS.get(key, key)}")
    for key, section in data.get("areas", {}).items():
        if isinstance(section, dict):
            register(section.get("source_ids", []), f"Area narrative: {AREA_LABELS.get(key, key)}")

    register(data.get("bias_relevant_findings", {}).get("source_ids", []), "Bias-relevant findings")

    for item in data.get("inquiries", []):
        if isinstance(item, dict):
            register(item.get("source_ids", []), f"Inquiry: {str(item.get('source_label', 'Inquiry')).strip() or 'Inquiry'}")
    for item in data.get("interviews", []):
        if isinstance(item, dict):
            register(item.get("source_ids", []), f"Interview: {str(item.get('kind', 'interview')).replace('_', ' ').title()}")
    for item in data.get("discrepancies", []):
        if isinstance(item, dict):
            register(item.get("source_ids", []), f"Discrepancy: {str(item.get('title', 'Discrepancy')).strip() or 'Discrepancy'}")
    for item in data.get("timeline", []):
        if isinstance(item, dict):
            register(item.get("source_ids", []), f"Timeline: {str(item.get('label', 'Timeline entry')).strip() or 'Timeline entry'}")
    for item in data.get("phs_changes", []):
        if isinstance(item, dict):
            register(item.get("source_ids", []), f"PHS change: {str(item.get('field_label', 'PHS field')).strip() or 'PHS field'}")
    for item in data.get("interview_plans", []):
        if isinstance(item, dict):
            register(item.get("source_ids", []), f"Interview plan: {str(item.get('subject', 'Interview plan')).strip() or 'Interview plan'}")

    for entry in sources.values():
        entry["references"] = sorted(set(entry["references"]))
    return {
        "sources": sorted(sources.values(), key=lambda item: item["source_id"]),
        "orphan_source_ids": sorted(orphans),
    }


def interview_plan_findings(plans: list[dict[str, Any]]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for item in plans:
        if not isinstance(item, dict):
            continue
        plan_id = item.get("id", "PLN")
        if not str(item.get("subject", "")).strip():
            findings.append({"kind": "missing_subject", "message": f"Review {plan_id}; interview subject is missing."})
        if not str(item.get("question", "")).strip():
            findings.append({"kind": "missing_question", "message": f"Review {plan_id}; interview question is missing."})
        if not _string_list(item.get("source_ids", [])):
            findings.append({"kind": "missing_source", "message": f"Review {plan_id}; add source identifiers linked to the planned interview."})
        if not str(item.get("recording_locator", "")).strip():
            findings.append({"kind": "missing_locator", "message": f"Review {plan_id}; add an approved recording locator or note that none exists."})
    return findings


def daily_queue(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    today = date.today()
    items: list[dict[str, Any]] = []
    for case in cases:
        case_id = case["case_id"]
        for inquiry in case.get("inquiries", []):
            due = inquiry.get("follow_up_due", "")
            try:
                due_date = date.fromisoformat(due) if due else None
            except ValueError:
                due_date = None
            if inquiry.get("release_required") and not inquiry.get("release_attached"):
                items.append({
                    "kind": "missing_release",
                    "priority": "high",
                    "case_id": case_id,
                    "record_id": inquiry["id"],
                    "title": inquiry.get("source_label", inquiry["id"]),
                    "detail": "Release required but not attached.",
                    "due_date": due or "",
                    "status": inquiry.get("status", ""),
                })
            if due_date and inquiry.get("status") not in {"received", "declined", "not_applicable"}:
                if due_date < today:
                    items.append({
                        "kind": "overdue_follow_up",
                        "priority": "high",
                        "case_id": case_id,
                        "record_id": inquiry["id"],
                        "title": inquiry.get("source_label", inquiry["id"]),
                        "detail": "Follow-up is overdue.",
                        "due_date": due,
                        "status": inquiry.get("status", ""),
                    })
                elif (due_date - today).days <= 3:
                    items.append({
                        "kind": "due_soon_follow_up",
                        "priority": "normal",
                        "case_id": case_id,
                        "record_id": inquiry["id"],
                        "title": inquiry.get("source_label", inquiry["id"]),
                        "detail": "Follow-up is due soon.",
                        "due_date": due,
                        "status": inquiry.get("status", ""),
                    })
            if inquiry.get("status") == "sent" and not inquiry.get("response_summary"):
                items.append({
                    "kind": "pending_source_response",
                    "priority": "normal",
                    "case_id": case_id,
                    "record_id": inquiry["id"],
                    "title": inquiry.get("source_label", inquiry["id"]),
                    "detail": "No response summary is recorded yet.",
                    "due_date": due or "",
                    "status": inquiry.get("status", ""),
                })
        if case.get("review", {}).get("status") == "corrections_requested":
            items.append({
                "kind": "supervisor_return",
                "priority": "high",
                "case_id": case_id,
                "record_id": case_id,
                "title": case_id,
                "detail": "Supervisor corrections are pending.",
                "due_date": case.get("target_date", ""),
                "status": case.get("review", {}).get("status", ""),
            })
    items.sort(key=lambda item: (0 if item["priority"] == "high" else 1, item["due_date"] or "9999-12-31", item["case_id"], item["record_id"]))
    return items


def timeline_findings(events: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Return neutral review prompts for dated life-history entries, never conclusions."""
    grouped: dict[str, list[dict[str, Any]]] = {category: [] for category in TIMELINE_CATEGORIES}
    for event in events:
        if not isinstance(event, dict):
            continue
        category = event.get("category", "other")
        if category not in grouped:
            category = "other"
        if event.get("start_date"):
            grouped[category].append(event)
    findings: list[dict[str, str]] = []
    for category, items in grouped.items():
        ordered = sorted(items, key=lambda event: event["start_date"])
        for previous, current in zip(ordered, ordered[1:]):
            previous_end = previous.get("end_date", "")
            current_start = current.get("start_date", "")
            if previous_end and previous_end < current_start:
                findings.append({"kind": "gap", "category": category, "message": f"Review gap in {TIMELINE_CATEGORY_LABELS[category].lower()} between {previous.get('label', 'timeline entry')} and {current.get('label', 'timeline entry')}."})
            if previous_end and previous_end > current_start:
                findings.append({"kind": "overlap", "category": category, "message": f"Review overlap in {TIMELINE_CATEGORY_LABELS[category].lower()} between {previous.get('label', 'timeline entry')} and {current.get('label', 'timeline entry')}."})
    return findings


def validate_case_package(value: Any) -> dict[str, Any]:
    """Accept only a complete Investigator Workbench case package, never a database snapshot."""
    if not isinstance(value, dict):
        raise WorkbenchError("case package must be a JSON object")
    data = json.loads(json.dumps(value))
    case_id = validate_case_id(str(data.get("case_id", "")))
    required = {"areas", "dimensions", "bias_relevant_findings", "inquiries", "discrepancies", "interviews", "sources", "timeline", "documents", "phs_changes", "interview_plans", "review"}
    if not required.issubset(data):
        raise WorkbenchError("case package is missing required workbench sections")
    if set(data["areas"]) != set(AREAS) or set(data["dimensions"]) != set(DIMENSIONS):
        raise WorkbenchError("case package does not match the current investigation structure")
    for area in data["areas"].values():
        if not isinstance(area, dict) or area.get("status") not in {"not_started", "in_progress", "complete", "not_applicable"} or not isinstance(area.get("narrative"), str) or not isinstance(area.get("source_ids"), list):
            raise WorkbenchError("case package contains an invalid investigation area")
    for dimension in data["dimensions"].values():
        if not isinstance(dimension, dict) or not isinstance(dimension.get("narrative"), str) or not isinstance(dimension.get("source_ids"), list):
            raise WorkbenchError("case package contains an invalid POST dimension")
    if not isinstance(data["bias_relevant_findings"], dict) or not isinstance(data["bias_relevant_findings"].get("narrative"), str) or not isinstance(data["bias_relevant_findings"].get("source_ids"), list):
        raise WorkbenchError("case package contains invalid bias findings")
    if any(not isinstance(data[name], list) or any(not isinstance(item, dict) for item in data[name]) for name in ("inquiries", "discrepancies", "interviews", "sources", "timeline", "documents", "phs_changes", "interview_plans")):
        raise WorkbenchError("case package contains invalid records")
    if data.get("status") not in CASE_STATUSES:
        raise WorkbenchError("case package contains an invalid case status")
    data["case_id"] = case_id
    data.pop("record_meta", None)
    return data


def due_state(value: str) -> str:
    if not value:
        return "none"
    try:
        due = date.fromisoformat(value)
    except ValueError:
        return "invalid"
    today = date.today()
    if due < today:
        return "overdue"
    if (due - today).days <= 3:
        return "due_soon"
    return "scheduled"


def audit_case(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    open_inquiries = []
    for inquiry in data["inquiries"]:
        if inquiry["status"] in {"planned", "sent", "nonresponsive"}:
            open_inquiries.append(inquiry["id"])
        if inquiry["status"] == "sent" and not inquiry.get("sent_at"):
            errors.append(f"{inquiry['id']}: sent inquiry has no sent date")
        if inquiry["status"] == "received" and not inquiry.get("response_summary"):
            warnings.append(f"{inquiry['id']}: received inquiry has no response summary")
        if inquiry.get("release_required") and not inquiry.get("release_attached"):
            errors.append(f"{inquiry['id']}: required release is not marked attached")
        if due_state(inquiry.get("follow_up_due", "")) == "overdue" and inquiry["status"] not in {"received", "declined", "not_applicable"}:
            warnings.append(f"{inquiry['id']}: follow-up is overdue")

    open_discrepancies = [item["id"] for item in data["discrepancies"] if item["status"] not in {"resolved"}]
    for item in data["discrepancies"]:
        if not item.get("candidate_statement") or not item.get("contrary_information"):
            errors.append(f"{item['id']}: discrepancy requires both sides of the conflict")
        if item["status"] == "resolved" and not item.get("resolution"):
            errors.append(f"{item['id']}: resolved discrepancy has no resolution")

    trace = source_trace_map(data)
    timeline_prompts = timeline_findings(data["timeline"])
    document_prompts = []
    for item in data["documents"]:
        if item.get("status") in {"needed", "requested"} and item.get("due_date") and due_state(item["due_date"]) == "overdue":
            document_prompts.append({"kind": "document", "message": f"Review overdue document request {item.get('id', 'document')} for {item.get('title', 'document')}.", "category": item.get("status", "needed")})
        if item.get("status") == "returned":
            document_prompts.append({"kind": "document", "message": f"Review returned document {item.get('id', 'document')} for {item.get('title', 'document')}.", "category": item.get("status", "returned")})
    phs_prompts = phs_findings(data["phs_changes"])
    plan_prompts = interview_plan_findings(data["interview_plans"])

    if trace["orphan_source_ids"]:
        errors.append(f"unregistered source identifiers referenced: {', '.join(trace['orphan_source_ids'])}")

    missing_areas = [AREA_LABELS[key] for key in AREAS if data["areas"][key]["status"] not in {"complete", "not_applicable"}]
    empty_dimensions = [DIMENSION_LABELS[key] for key in DIMENSIONS if not data["dimensions"][key]["narrative"].strip()]
    if data["status"] in {"quality_review", "closed"}:
        if missing_areas:
            errors.append(f"required investigation areas incomplete: {', '.join(missing_areas)}")
        if empty_dimensions:
            errors.append(f"POST dimension narratives missing: {', '.join(empty_dimensions)}")
        if open_inquiries:
            errors.append(f"open inquiries remain: {', '.join(open_inquiries)}")
        if open_discrepancies:
            errors.append(f"unresolved discrepancies remain: {', '.join(open_discrepancies)}")
        if not any(item["kind"] == "pre_investigatory" for item in data["interviews"]):
            errors.append("no Pre-Investigatory Interview is documented")
        if plan_prompts:
            errors.extend(item["message"] for item in plan_prompts)

    complete_areas = sum(1 for key in AREAS if data["areas"][key]["status"] in {"complete", "not_applicable"})
    written_dimensions = sum(1 for key in DIMENSIONS if data["dimensions"][key]["narrative"].strip())
    checklist = [
        {"key": "case_opened", "label": "Confirm assignment and target date", "complete": bool(data.get("investigator") and data.get("target_date"))},
        {"key": "pre_interview", "label": "Document the Pre-Investigatory Interview", "complete": any(item["kind"] == "pre_investigatory" for item in data["interviews"])},
        {"key": "sources", "label": "Register approved-system source locators", "complete": bool(data["sources"])},
        {"key": "traceability", "label": "Link source identifiers through the trace map", "complete": not trace["orphan_source_ids"], "detail": f"{len(trace['orphan_source_ids'])} unregistered references" if trace["orphan_source_ids"] else f"{len(trace['sources'])} sources mapped"},
        {"key": "coverage", "label": "Complete the twelve required investigation areas", "complete": complete_areas == len(AREAS), "detail": f"{complete_areas} of {len(AREAS)} complete"},
        {"key": "narrative", "label": "Write POST dimensions and bias-relevant findings", "complete": written_dimensions == len(DIMENSIONS) and bool(data["bias_relevant_findings"]["narrative"].strip()), "detail": f"{written_dimensions} of {len(DIMENSIONS)} dimensions drafted"},
        {"key": "resolve", "label": "Resolve inquiries and discrepancies", "complete": not open_inquiries and not open_discrepancies, "detail": f"{len(open_inquiries)} inquiries · {len(open_discrepancies)} discrepancies open"},
    ]
    return {
        "case_id": data["case_id"],
        "ready": not errors,
        "errors": errors,
        "warnings": warnings,
        "timeline_findings": timeline_prompts,
        "document_findings": document_prompts,
        "phs_findings": phs_prompts,
        "interview_plan_findings": plan_prompts,
        "source_trace_map": trace,
        "metrics": {
            "areas_complete": complete_areas,
            "areas_total": len(AREAS),
            "open_inquiries": len(open_inquiries),
            "open_discrepancies": len(open_discrepancies),
            "interviews": len(data["interviews"]),
            "sources": len(data["sources"]),
            "timeline_items": len(data["timeline"]),
            "documents": len(data["documents"]),
            "phs_changes": len(data["phs_changes"]),
            "interview_plans": len(data["interview_plans"]),
        },
        "checklist": checklist,
    }


def render_report(data: dict[str, Any]) -> str:
    lines = [
        f"# Background Investigation Narrative - {data['case_id']}",
        "",
        "> Working draft. Verify every statement against the cited source and approved CDCR policy before use.",
        "",
        "## Background Investigation Dimensions",
        "",
    ]
    for key in DIMENSIONS:
        section = data["dimensions"][key]
        lines.extend([f"### {DIMENSION_LABELS[key]}", "", section["narrative"] or "[No narrative entered]", "", _source_line(section["source_ids"])])
    lines.extend(["", "## Bias-Relevant Findings", "", data["bias_relevant_findings"]["narrative"] or "[No narrative entered]", "", _source_line(data["bias_relevant_findings"]["source_ids"]), "", "## Required Areas of Investigation", ""])
    for key in AREAS:
        section = data["areas"][key]
        lines.extend([f"### {AREA_LABELS[key]}", "", f"Status: {section['status']}", "", section["narrative"] or "[No narrative entered]", "", _source_line(section["source_ids"]), ""])
    lines.extend(["## Life History Timeline", ""])
    if not data["timeline"]:
        lines.append("No timeline entries recorded.")
    else:
        for category in TIMELINE_CATEGORIES:
            entries = [item for item in data["timeline"] if item.get("category", "other") == category]
            if not entries:
                continue
            lines.extend([f"### {TIMELINE_CATEGORY_LABELS[category]}", ""])
            for item in entries:
                period = " to ".join(part for part in (item.get("start_date", ""), item.get("end_date", "")) if part) or "Date not set"
                lines.extend([f"- {item.get('label', 'Timeline entry')} ({period})", f"  {item.get('notes', '') or '[No notes entered]'}", f"  {_source_line(item.get('source_ids', []))}"])
            lines.append("")
    lines.extend(["## Document Control Log", ""])
    if not data["documents"]:
        lines.append("No document control entries recorded.")
    else:
        for item in data["documents"]:
            parts = [item.get("title", "Document"), item.get("status", "needed")]
            if item.get("due_date"):
                parts.append(f"due {item['due_date']}")
            if item.get("source_locator"):
                parts.append(item["source_locator"])
            lines.append(f"- {item.get('id', 'DOC')}: " + " · ".join(parts))
    lines.append("")
    lines.extend(["## PHS Change Ledger", ""])
    if not data["phs_changes"]:
        lines.append("No PHS changes recorded.")
    else:
        for item in data["phs_changes"]:
            lines.extend([
                f"- {item.get('id', 'PHS')}: {item.get('field_label', 'PHS field')}",
                f"  Prior: {item.get('prior_value', '[Not entered]')}",
                f"  Current: {item.get('current_value', '[Not entered]')}",
                f"  Reported: {item.get('reported_at', '') or '[Not entered]'}",
                f"  Disposition: {item.get('disposition', '') or '[Not entered]'}",
                f"  {_source_line(item.get('source_ids', []))}",
            ])
            lines.append("")
    lines.extend(["## Interview Planning Packets", ""])
    if not data["interview_plans"]:
        lines.append("No interview planning packets recorded.")
    else:
        for item in data["interview_plans"]:
            lines.extend([
                f"- {item.get('id', 'PLN')}: {item.get('subject', 'Interview plan')} ({item.get('status', 'planned')})",
                f"  Question: {item.get('question', '[Not entered]')}",
                f"  Locator: {item.get('recording_locator', '') or '[Not entered]'}",
                f"  {_source_line(item.get('source_ids', []))}",
                f"  Discrepancies: {', '.join(item.get('discrepancy_ids', [])) or '[None linked]'}",
            ])
            lines.append("")
    trace = source_trace_map(data)
    lines.extend(["## Source Trace Map", ""])
    if not trace["sources"]:
        lines.append("No registered sources recorded.")
    else:
        for item in trace["sources"]:
            lines.extend([
                f"- {item['source_id']}: {item['label']}",
                f"  Kind: {item['kind'] or '[Not entered]'}",
                f"  Location: {item['location'] or '[Not entered]'}",
                f"  References: {', '.join(item['references']) or '[None linked]'}",
            ])
            lines.append("")
    if trace["orphan_source_ids"]:
        lines.extend(["Unregistered source identifiers referenced:", ", ".join(trace["orphan_source_ids"]), ""])
    lines.extend(["## Discrepancy Matrix", ""])
    if not data["discrepancies"]:
        lines.append("No discrepancies recorded.")
    else:
        for item in discrepancy_matrix(data["discrepancies"]):
            lines.extend([
                f"- {item['id']}: {item['title']} ({item['status']})",
                f"  Candidate: {item['candidate_statement'] or '[Not entered]'}",
                f"  Contrary: {item['contrary_information'] or '[Not entered]'}",
                f"  Response: {item['candidate_response'] or '[Not entered]'}",
                f"  Corroboration: {item['corroboration'] or '[Not entered]'}",
                f"  Resolution: {item['resolution'] or '[Not entered]'}",
            ])
            lines.append("")
    lines.extend(["## Unresolved Matters", ""])
    unresolved = [item for item in data["discrepancies"] if item["status"] != "resolved"]
    if not unresolved:
        lines.append("None recorded.")
    else:
        for item in unresolved:
            lines.append(f"- {item['id']}: {item['title']} ({item['status']})")
    return "\n".join(lines).rstrip() + "\n"


def _source_line(source_ids: list[str]) -> str:
    return "Sources: " + (", ".join(source_ids) if source_ids else "[None cited]")
