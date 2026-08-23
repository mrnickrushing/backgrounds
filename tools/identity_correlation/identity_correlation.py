#!/usr/bin/env python3
"""
Identity Correlation Worksheet
===============================
Helps document *why* you believe (or don't believe) a social media account
belongs to a background investigation candidate, by recording the known
identifiers for the candidate alongside what you actually found on each
account, and producing a consistent, weighted overlap score.

IMPORTANT: The score is a documentation aid, not a determination. It exists
so your reasoning is written down consistently across accounts and cases --
the final "is/isn't this person" call is still yours, made per your agency's
policy and standards of evidence.

This tool does not look anything up for you. You supply what you observed;
it organizes and scores it.

Storage layout (all local, all gitignored):
  cases/<CASE_ID>/identity_worksheet.json
  cases/<CASE_ID>/files/   -- shared with evidence_logger for saved photos

Usage:
  python3 identity_correlation.py new CASE_ID --name "Jane Q. Candidate" --dob 1990-01-01
  python3 identity_correlation.py set-candidate CASE_ID --alias "jqcandidate" \\
      --address "123 Main St, Sacramento, CA" --employer "Acme Corp" \\
      --phone "555-123-4567" --email "jane@example.com" --school "Sac State" \\
      --associate "John Smith"
  python3 identity_correlation.py add-account CASE_ID --platform Instagram \\
      --username jqcandidate90 --url https://instagram.com/jqcandidate90 \\
      --examiner "J. Doe" --matched-alias "jqcandidate90 is a known handle variant" \\
      --location "Sacramento, CA" --employer-mention "Acme Corp" \\
      --associate "John Smith" --photo /path/to/profile.jpg --notes "Bio matches"
  python3 identity_correlation.py report CASE_ID
"""
import argparse
import hashlib
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

CASES_ROOT = Path(__file__).resolve().parent.parent.parent / "cases"

WEIGHTS = {
    "name_or_alias": 30,
    "dob_or_age": 15,
    "location": 20,
    "employer": 20,
    "associate": 15,
}
MAX_SCORE = sum(WEIGHTS.values())

BANDS = [
    (75, "Strong correlation"),
    (50, "Moderate correlation"),
    (20, "Weak correlation"),
    (0, "Insufficient correlation"),
]


def utc_now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def case_dir(case_id):
    return CASES_ROOT / case_id


def worksheet_path(case_id):
    return case_dir(case_id) / "identity_worksheet.json"


def load_worksheet(case_id):
    path = worksheet_path(case_id)
    if not path.exists():
        raise SystemExit(f"No worksheet found at {path}. Run `new {case_id}` first.")
    with open(path, "r") as f:
        return json.load(f)


def save_worksheet(case_id, data):
    with open(worksheet_path(case_id), "w") as f:
        json.dump(data, f, indent=2)


def cmd_new(args):
    cdir = case_dir(args.case_id)
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "files").mkdir(exist_ok=True)
    path = worksheet_path(args.case_id)
    if path.exists():
        print(f"Worksheet for '{args.case_id}' already exists at {path}")
        return
    data = {
        "case_id": args.case_id,
        "created_utc": utc_now_iso(),
        "candidate": {
            "full_name": args.name,
            "dob": args.dob,
            "aliases": [],
            "addresses": [],
            "employers": [],
            "phones": [],
            "emails": [],
            "schools": [],
            "associates": [],
        },
        "accounts": [],
    }
    save_worksheet(args.case_id, data)
    print(f"Created identity worksheet for '{args.name}' in case '{args.case_id}'")


def cmd_set_candidate(args):
    data = load_worksheet(args.case_id)
    c = data["candidate"]
    field_map = {
        "alias": "aliases",
        "address": "addresses",
        "employer": "employers",
        "phone": "phones",
        "email": "emails",
        "school": "schools",
        "associate": "associates",
    }
    for arg_name, field in field_map.items():
        values = getattr(args, arg_name.replace("-", "_"))
        if values:
            for v in values:
                if v not in c[field]:
                    c[field].append(v)
    if args.name:
        c["full_name"] = args.name
    if args.dob:
        c["dob"] = args.dob
    save_worksheet(args.case_id, data)
    print(f"Updated candidate record for case '{args.case_id}'")


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_score(found):
    total = 0
    breakdown = []
    for key, weight in WEIGHTS.items():
        hit = bool(found.get(key))
        if hit:
            total += weight
        breakdown.append((key, weight, hit))
    band = next(label for threshold, label in BANDS if total >= threshold)
    return total, band, breakdown


def cmd_add_account(args):
    data = load_worksheet(args.case_id)

    photo_ref = None
    photo_sha256 = None
    if args.photo:
        src = Path(args.photo)
        if not src.exists():
            raise SystemExit(f"Photo not found: {src}")
        photo_sha256 = sha256_of(src)
        dest_dir = case_dir(args.case_id) / "files"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_name = f"{uuid.uuid4().hex}_{src.name}"
        shutil.copy2(src, dest_dir / dest_name)
        photo_ref = f"files/{dest_name}"

    found = {
        "name_or_alias": args.matched_alias or None,
        "dob_or_age": args.dob_match or None,
        "location": ", ".join(args.location) if args.location else None,
        "employer": ", ".join(args.employer_mention) if args.employer_mention else None,
        "associate": ", ".join(args.associate) if args.associate else None,
    }
    score, band, breakdown = compute_score(found)

    account = {
        "id": str(uuid.uuid4()),
        "reviewed_utc": utc_now_iso(),
        "examiner": args.examiner,
        "platform": args.platform,
        "username": args.username,
        "url": args.url,
        "display_name": args.display_name,
        "bio": args.bio,
        "found": found,
        "photo_ref": photo_ref,
        "photo_sha256": photo_sha256,
        "notes": args.notes or "",
        "score": score,
        "score_max": MAX_SCORE,
        "score_band": band,
    }
    data["accounts"].append(account)
    save_worksheet(args.case_id, data)
    print(f"Added account @{args.username} ({args.platform}) -- score {score}/{MAX_SCORE}: {band}")


def cmd_report(args):
    data = load_worksheet(args.case_id)
    c = data["candidate"]
    lines = [
        f"# Identity Correlation Worksheet -- Case {args.case_id}",
        "",
        f"Generated: {utc_now_iso()}",
        "",
        "> Scores below document overlap between known candidate identifiers and "
        "what was observed on each account. They are a documentation aid, not an "
        "automated determination -- the investigator's judgment, per agency policy, "
        "governs the final finding.",
        "",
        "## Candidate",
        f"- **Name:** {c['full_name']}",
        f"- **DOB:** {c.get('dob') or 'n/a'}",
        f"- **Known aliases:** {', '.join(c['aliases']) or 'none recorded'}",
        f"- **Known addresses:** {', '.join(c['addresses']) or 'none recorded'}",
        f"- **Known employers:** {', '.join(c['employers']) or 'none recorded'}",
        f"- **Known phones:** {', '.join(c['phones']) or 'none recorded'}",
        f"- **Known emails:** {', '.join(c['emails']) or 'none recorded'}",
        f"- **Known schools:** {', '.join(c['schools']) or 'none recorded'}",
        f"- **Known associates:** {', '.join(c['associates']) or 'none recorded'}",
        "",
        "## Accounts Reviewed",
        "",
    ]
    if not data["accounts"]:
        lines.append("_No accounts reviewed yet._")
    for a in data["accounts"]:
        lines.append(f"### @{a['username']} on {a['platform']} -- {a['score']}/{a['score_max']} ({a['score_band']})")
        lines.append(f"- **URL:** {a['url']}")
        lines.append(f"- **Reviewed:** {a['reviewed_utc']} by {a['examiner']}")
        if a.get("display_name"):
            lines.append(f"- **Display name:** {a['display_name']}")
        if a.get("bio"):
            lines.append(f"- **Bio:** {a['bio']}")
        lines.append("- **Matched identifiers:**")
        for key, weight, hit in [(k, WEIGHTS[k], bool(a["found"].get(k))) for k in WEIGHTS]:
            mark = "x" if hit else " "
            detail = f" -- {a['found'][key]}" if hit else ""
            lines.append(f"  - [{mark}] {key.replace('_', ' ')} ({weight} pts){detail}")
        if a.get("photo_ref"):
            lines.append(f"- **Saved photo:** `{a['photo_ref']}` (SHA256: `{a['photo_sha256']}`)")
        if a.get("notes"):
            lines.append(f"- **Notes:** {a['notes']}")
        lines.append("")

    out_path = Path(args.output) if args.output else case_dir(args.case_id) / "identity_report.md"
    out_path.write_text("\n".join(lines))
    print(f"Report written to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Identity correlation worksheet for social media OSINT.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("new", help="Create a new worksheet for a candidate")
    p_new.add_argument("case_id")
    p_new.add_argument("--name", required=True, help="Candidate full name")
    p_new.add_argument("--dob", help="Candidate date of birth (YYYY-MM-DD)")
    p_new.set_defaults(func=cmd_new)

    p_set = sub.add_parser("set-candidate", help="Add known identifiers for the candidate")
    p_set.add_argument("case_id")
    p_set.add_argument("--name")
    p_set.add_argument("--dob")
    p_set.add_argument("--alias", action="append")
    p_set.add_argument("--address", action="append")
    p_set.add_argument("--employer", action="append")
    p_set.add_argument("--phone", action="append")
    p_set.add_argument("--email", action="append")
    p_set.add_argument("--school", action="append")
    p_set.add_argument("--associate", action="append")
    p_set.set_defaults(func=cmd_set_candidate)

    p_acc = sub.add_parser("add-account", help="Log a reviewed account and score its correlation")
    p_acc.add_argument("case_id")
    p_acc.add_argument("--examiner", required=True)
    p_acc.add_argument("--platform", required=True)
    p_acc.add_argument("--username", required=True)
    p_acc.add_argument("--url", required=True)
    p_acc.add_argument("--display-name")
    p_acc.add_argument("--bio")
    p_acc.add_argument("--photo", help="Path to a locally saved copy of the profile photo")
    p_acc.add_argument("--matched-alias", help="How the name/alias matched, if it did")
    p_acc.add_argument("--dob-match", help="How DOB/age evidence matched, if it did")
    p_acc.add_argument("--location", action="append", help="Location match(es) found; repeatable")
    p_acc.add_argument("--employer-mention", action="append", help="Employer match(es) found; repeatable")
    p_acc.add_argument("--associate", action="append", help="Associate match(es) found; repeatable")
    p_acc.add_argument("--notes")
    p_acc.set_defaults(func=cmd_add_account)

    p_report = sub.add_parser("report", help="Generate a Markdown report for a case")
    p_report.add_argument("case_id")
    p_report.add_argument("--output")
    p_report.set_defaults(func=cmd_report)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
