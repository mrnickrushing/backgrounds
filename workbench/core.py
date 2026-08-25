from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import date, datetime, timezone
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
    return {
        "schema_version": 1,
        "case_id": case_id,
        "investigator": investigator,
        "status": "intake",
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
        "activity": [{"at": now, "action": "case_created", "detail": "Local workbench case initialized"}],
    }


def load_case(case_id: str, root: str | Path | None = None) -> dict[str, Any]:
    path = case_path(case_id, root)
    if not path.exists():
        raise WorkbenchError(f"case not found: {case_id}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


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


def due_state(value: str) -> str:
    if not value:
        return "none"
    due = date.fromisoformat(value)
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

    return {
        "case_id": data["case_id"],
        "ready": not errors,
        "errors": errors,
        "warnings": warnings,
        "metrics": {
            "areas_complete": sum(1 for key in AREAS if data["areas"][key]["status"] in {"complete", "not_applicable"}),
            "areas_total": len(AREAS),
            "open_inquiries": len(open_inquiries),
            "open_discrepancies": len(open_discrepancies),
            "interviews": len(data["interviews"]),
            "sources": len(data["sources"]),
        },
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
