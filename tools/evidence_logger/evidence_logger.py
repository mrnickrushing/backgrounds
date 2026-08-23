#!/usr/bin/env python3
"""
Evidence Logger
================
A case-scoped, tamper-evident log for documenting social media / OSINT
findings during a background investigation.

Every entry is timestamped (UTC), hashed, and chained to the previous
entry's hash (like a minimal blockchain ledger). This makes silent
after-the-fact edits to the log detectable via `verify`, which matters
if the log ever has to support a finding in an investigative file.

This tool does NOT scrape, log into, or interact with any platform.
It only records what you, the investigator, observed and where you saved
supporting files (e.g. a screenshot you took yourself).

Storage layout (all local, all gitignored):
  cases/<CASE_ID>/evidence_log.json   -- the append-only ledger
  cases/<CASE_ID>/files/              -- copies of hashed supporting files

Usage:
  python3 evidence_logger.py init CASE_ID
  python3 evidence_logger.py add CASE_ID --examiner "J. Doe" \\
      --url "https://example.com/profile/123" \\
      --description "Public Instagram profile, appears to match candidate" \\
      --file /path/to/screenshot.png --notes "Bio lists same employer as app" \\
      --archive
  python3 evidence_logger.py hash /path/to/file
  python3 evidence_logger.py report CASE_ID
  python3 evidence_logger.py verify CASE_ID
"""
import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
import uuid

CASES_ROOT = Path(__file__).resolve().parent.parent.parent / "cases"
GENESIS_HASH = "0" * 64


def utc_now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def case_dir(case_id):
    return CASES_ROOT / case_id


def log_path(case_id):
    return case_dir(case_id) / "evidence_log.json"


def load_log(case_id):
    path = log_path(case_id)
    if not path.exists():
        raise SystemExit(f"No case found at {path}. Run `init {case_id}` first.")
    with open(path, "r") as f:
        return json.load(f)


def save_log(case_id, entries):
    with open(log_path(case_id), "w") as f:
        json.dump(entries, f, indent=2)


def file_hashes(path):
    sha256 = hashlib.sha256()
    md5 = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
            md5.update(chunk)
    return sha256.hexdigest(), md5.hexdigest()


def canonical_entry_hash(entry_without_hash, prev_hash):
    payload = json.dumps(entry_without_hash, sort_keys=True) + prev_hash
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cmd_init(args):
    cdir = case_dir(args.case_id)
    (cdir / "files").mkdir(parents=True, exist_ok=True)
    path = log_path(args.case_id)
    if path.exists():
        print(f"Case '{args.case_id}' already exists at {cdir}")
        return
    save_log(args.case_id, [])
    print(f"Initialized case '{args.case_id}' at {cdir}")


def submit_to_wayback(url):
    """Ask the Internet Archive's Save Page Now service to snapshot a URL
    and return the resulting archive.org snapshot URL, or None on failure."""
    save_url = "https://web.archive.org/save/" + url
    try:
        req = urllib.request.Request(save_url, headers={"User-Agent": "evidence-logger/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            content_location = resp.headers.get("Content-Location")
            if content_location:
                return "https://web.archive.org" + content_location
            return resp.geturl()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"  [!] Could not reach Wayback Machine ({e}). "
              f"Log entry saved without an archive link -- consider archiving manually.")
        return None


def cmd_add(args):
    entries = load_log(args.case_id)
    prev_hash = entries[-1]["entry_hash"] if entries else GENESIS_HASH

    file_ref = None
    sha256_hex = None
    md5_hex = None
    if args.file:
        src = Path(args.file)
        if not src.exists():
            raise SystemExit(f"File not found: {src}")
        sha256_hex, md5_hex = file_hashes(src)
        dest_dir = case_dir(args.case_id) / "files"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_name = f"{uuid.uuid4().hex}_{src.name}"
        shutil.copy2(src, dest_dir / dest_name)
        file_ref = f"files/{dest_name}"

    archive_url = None
    if args.archive:
        if not args.url:
            print("  [!] --archive requires --url; skipping archive step.")
        else:
            print(f"  Submitting to Wayback Machine: {args.url}")
            archive_url = submit_to_wayback(args.url)

    entry_body = {
        "seq": len(entries) + 1,
        "id": str(uuid.uuid4()),
        "timestamp_utc": utc_now_iso(),
        "examiner": args.examiner,
        "url": args.url,
        "description": args.description,
        "notes": args.notes or "",
        "file_ref": file_ref,
        "file_sha256": sha256_hex,
        "file_md5": md5_hex,
        "archive_url": archive_url,
        "prev_hash": prev_hash,
    }
    entry_hash = canonical_entry_hash(entry_body, prev_hash)
    entry = dict(entry_body)
    entry["entry_hash"] = entry_hash

    entries.append(entry)
    save_log(args.case_id, entries)
    print(f"Logged entry #{entry['seq']} for case '{args.case_id}' (hash {entry_hash[:12]}...)")


def cmd_hash(args):
    path = Path(args.file)
    if not path.exists():
        raise SystemExit(f"File not found: {path}")
    sha256_hex, md5_hex = file_hashes(path)
    print(f"File:   {path}")
    print(f"SHA256: {sha256_hex}")
    print(f"MD5:    {md5_hex}")


def cmd_verify(args):
    entries = load_log(args.case_id)
    prev_hash = GENESIS_HASH
    for entry in entries:
        body = {k: v for k, v in entry.items() if k != "entry_hash"}
        if body.get("prev_hash") != prev_hash:
            print(f"BROKEN CHAIN at entry #{entry['seq']}: prev_hash does not match preceding entry.")
            return
        recomputed = canonical_entry_hash(body, prev_hash)
        if recomputed != entry["entry_hash"]:
            print(f"TAMPERED entry #{entry['seq']}: stored hash does not match recomputed hash.")
            print(f"  stored:     {entry['entry_hash']}")
            print(f"  recomputed: {recomputed}")
            return
        prev_hash = entry["entry_hash"]
    print(f"OK: all {len(entries)} entries verified intact for case '{args.case_id}'.")


def cmd_report(args):
    entries = load_log(args.case_id)
    lines = [
        f"# Evidence Log -- Case {args.case_id}",
        "",
        f"Generated: {utc_now_iso()}",
        f"Total entries: {len(entries)}",
        "",
        "> Chain-of-custody note: each entry below is cryptographically chained "
        "to the one before it. Run `verify` on the source log before relying on "
        "this report; any edit after the fact will break the chain.",
        "",
    ]
    for e in entries:
        lines.append(f"## Entry #{e['seq']} -- {e['timestamp_utc']}")
        lines.append(f"- **Examiner:** {e['examiner']}")
        if e.get("url"):
            lines.append(f"- **URL:** {e['url']}")
        lines.append(f"- **Description:** {e['description']}")
        if e.get("notes"):
            lines.append(f"- **Notes:** {e['notes']}")
        if e.get("archive_url"):
            lines.append(f"- **Archived copy:** {e['archive_url']}")
        if e.get("file_ref"):
            lines.append(f"- **Saved file:** `{e['file_ref']}`")
            lines.append(f"  - SHA256: `{e['file_sha256']}`")
            lines.append(f"  - MD5: `{e['file_md5']}`")
        lines.append(f"- **Entry hash:** `{e['entry_hash']}`")
        lines.append("")

    out_path = Path(args.output) if args.output else case_dir(args.case_id) / "evidence_report.md"
    out_path.write_text("\n".join(lines))
    print(f"Report written to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Tamper-evident evidence logger for OSINT/social media findings.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Create a new case")
    p_init.add_argument("case_id")
    p_init.set_defaults(func=cmd_init)

    p_add = sub.add_parser("add", help="Add an evidence entry to a case")
    p_add.add_argument("case_id")
    p_add.add_argument("--examiner", required=True, help="Name/ID of the investigator logging this entry")
    p_add.add_argument("--url", help="URL of the profile/post/page observed")
    p_add.add_argument("--description", required=True, help="What was observed")
    p_add.add_argument("--notes", help="Additional context")
    p_add.add_argument("--file", help="Path to a local screenshot/file to hash and store a copy of")
    p_add.add_argument("--archive", action="store_true", help="Submit --url to the Wayback Machine")
    p_add.set_defaults(func=cmd_add)

    p_hash = sub.add_parser("hash", help="Print SHA256/MD5 of a file (standalone utility)")
    p_hash.add_argument("file")
    p_hash.set_defaults(func=cmd_hash)

    p_verify = sub.add_parser("verify", help="Verify the hash chain of a case's log")
    p_verify.add_argument("case_id")
    p_verify.set_defaults(func=cmd_verify)

    p_report = sub.add_parser("report", help="Generate a Markdown report for a case")
    p_report.add_argument("case_id")
    p_report.add_argument("--output", help="Output path (default: cases/<case_id>/evidence_report.md)")
    p_report.set_defaults(func=cmd_report)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
