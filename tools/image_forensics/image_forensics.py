#!/usr/bin/env python3
"""
Image Forensics
================
Two things this helps verify about a photo found during a background
investigation:

1. **EXIF metadata** -- camera make/model, original capture timestamp, and
   GPS coordinates if present. Most social media platforms strip this on
   upload, so it mostly matters for originals a candidate provides directly
   (e.g. handed over during an interview, emailed, texted).

2. **Perceptual hashing** -- a "fuzzy" fingerprint of what an image looks
   like, robust to resizing/recompression/minor edits. Useful for:
   - catching a profile photo reused across multiple accounts/aliases
   - catching a stolen/stock photo (compare against a known image)
   - confirming two copies of "the same" photo actually are the same

Perceptual hashes are similarity fingerprints, not proof of identity or
authorship -- treat a hash match as a lead to document and corroborate, not
a conclusion on its own.

Requires Pillow (`pip install -r requirements.txt`).

Usage:
  python3 image_forensics.py inspect /path/to/photo.jpg
  python3 image_forensics.py inspect /path/to/photo.jpg --case 2026-0142 --examiner "J. Doe"
  python3 image_forensics.py compare /path/to/a.jpg /path/to/b.jpg
  python3 image_forensics.py report 2026-0142
"""
import argparse
import hashlib
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ExifTags

CASES_ROOT = Path(__file__).resolve().parent.parent.parent / "cases"

# Hamming distance thresholds for a 64-bit perceptual hash, applied to the
# average of the aHash and dHash distances. These are commonly used rules of
# thumb, not a certified standard -- use them to prioritize what to look at
# more closely, not as a pass/fail test.
SIMILARITY_BANDS = [
    (5, "Identical or near-identical"),
    (10, "Similar (possible re-compression/light edit of the same image)"),
    (20, "Some visual similarity"),
    (65, "Different images"),
]


def utc_now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def case_dir(case_id):
    return CASES_ROOT / case_id


def log_path(case_id):
    return case_dir(case_id) / "image_forensics_log.json"


def load_log(case_id):
    path = log_path(case_id)
    if not path.exists():
        return []
    with open(path, "r") as f:
        return json.load(f)


def save_log(case_id, entries):
    case_dir(case_id).mkdir(parents=True, exist_ok=True)
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


def dms_to_decimal(dms, ref):
    degrees, minutes, seconds = (float(v) for v in dms)
    decimal = degrees + minutes / 60.0 + seconds / 3600.0
    if ref in ("S", "W"):
        decimal = -decimal
    return decimal


def extract_exif(img):
    """Return a flat dict of human-readable EXIF tags, or {} if none present."""
    raw = img.getexif()
    if not raw:
        return {}

    tags = {}
    for tag_id, value in raw.items():
        name = ExifTags.TAGS.get(tag_id, str(tag_id))
        tags[name] = value

    # GPS lives in its own sub-IFD and needs separate decoding.
    gps_ifd = raw.get_ifd(ExifTags.IFD.GPSInfo) if hasattr(ExifTags, "IFD") else None
    if gps_ifd:
        gps = {ExifTags.GPSTAGS.get(k, str(k)): v for k, v in gps_ifd.items()}
        lat = gps.get("GPSLatitude")
        lat_ref = gps.get("GPSLatitudeRef")
        lon = gps.get("GPSLongitude")
        lon_ref = gps.get("GPSLongitudeRef")
        if lat and lat_ref and lon and lon_ref:
            tags["GPSLatitudeDecimal"] = round(dms_to_decimal(lat, lat_ref), 6)
            tags["GPSLongitudeDecimal"] = round(dms_to_decimal(lon, lon_ref), 6)

    # Keep only JSON-serializable, human-relevant fields.
    keep = [
        "Make", "Model", "Software", "DateTime", "DateTimeOriginal",
        "DateTimeDigitized", "Orientation", "LensModel",
        "GPSLatitudeDecimal", "GPSLongitudeDecimal",
    ]
    return {k: str(tags[k]) for k in keep if k in tags}


def ahash(img, hash_size=8):
    small = img.convert("L").resize((hash_size, hash_size), Image.LANCZOS)
    pixels = list(small.tobytes())
    avg = sum(pixels) / len(pixels)
    bits = "".join("1" if p >= avg else "0" for p in pixels)
    return f"{int(bits, 2):0{hash_size * hash_size // 4}x}"


def dhash(img, hash_size=8):
    small = img.convert("L").resize((hash_size + 1, hash_size), Image.LANCZOS)
    pixels = list(small.tobytes())
    bits = []
    for row in range(hash_size):
        row_start = row * (hash_size + 1)
        for col in range(hash_size):
            left = pixels[row_start + col]
            right = pixels[row_start + col + 1]
            bits.append("1" if left > right else "0")
    bits = "".join(bits)
    return f"{int(bits, 2):0{hash_size * hash_size // 4}x}"


def hamming_distance(hex_a, hex_b):
    int_a, int_b = int(hex_a, 16), int(hex_b, 16)
    return bin(int_a ^ int_b).count("1")


def similarity_band(distance):
    return next(label for threshold, label in SIMILARITY_BANDS if distance <= threshold)


def inspect_file(path):
    path = Path(path)
    if not path.exists():
        raise SystemExit(f"File not found: {path}")
    sha256_hex, md5_hex = file_hashes(path)
    with Image.open(path) as img:
        img.load()
        result = {
            "file": str(path),
            "format": img.format,
            "dimensions": f"{img.width}x{img.height}",
            "sha256": sha256_hex,
            "md5": md5_hex,
            "ahash": ahash(img),
            "dhash": dhash(img),
            "exif": extract_exif(img),
        }
    return result


def print_inspection(result):
    print(f"File:       {result['file']}")
    print(f"Format:     {result['format']}, {result['dimensions']}")
    print(f"SHA256:     {result['sha256']}")
    print(f"MD5:        {result['md5']}")
    print(f"aHash:      {result['ahash']}")
    print(f"dHash:      {result['dhash']}")
    if result["exif"]:
        print("EXIF metadata:")
        for k, v in result["exif"].items():
            print(f"  {k}: {v}")
    else:
        print("EXIF metadata: none found "
              "(common for images downloaded from social media, which "
              "typically strip metadata on upload)")


def cmd_inspect(args):
    result = inspect_file(args.file)
    print_inspection(result)

    if args.case:
        src = Path(args.file)
        dest_dir = case_dir(args.case) / "files"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_name = f"{uuid.uuid4().hex}_{src.name}"
        shutil.copy2(src, dest_dir / dest_name)

        entries = load_log(args.case)
        entries.append({
            "seq": len(entries) + 1,
            "id": str(uuid.uuid4()),
            "timestamp_utc": utc_now_iso(),
            "examiner": args.examiner,
            "type": "inspect",
            "file_ref": f"files/{dest_name}",
            "notes": args.notes or "",
            **result,
        })
        # avoid duplicating the original absolute path alongside file_ref
        entries[-1]["file"] = src.name
        save_log(args.case, entries)
        print(f"\nLogged to case '{args.case}' (files/{dest_name})")


def cmd_compare(args):
    result_a = inspect_file(args.file_a)
    result_b = inspect_file(args.file_b)

    dist_a = hamming_distance(result_a["ahash"], result_b["ahash"])
    dist_d = hamming_distance(result_a["dhash"], result_b["dhash"])
    avg_dist = (dist_a + dist_d) / 2
    band = similarity_band(avg_dist)

    print(f"A: {result_a['file']}")
    print(f"B: {result_b['file']}")
    print(f"SHA256 match:     {'YES (byte-for-byte identical file)' if result_a['sha256'] == result_b['sha256'] else 'no'}")
    print(f"aHash distance:   {dist_a}/64")
    print(f"dHash distance:   {dist_d}/64")
    print(f"Assessment:       {band}")

    if args.case:
        entries = load_log(args.case)
        entries.append({
            "seq": len(entries) + 1,
            "id": str(uuid.uuid4()),
            "timestamp_utc": utc_now_iso(),
            "examiner": args.examiner,
            "type": "compare",
            "file_a": result_a["file"],
            "file_b": result_b["file"],
            "sha256_match": result_a["sha256"] == result_b["sha256"],
            "ahash_distance": dist_a,
            "dhash_distance": dist_d,
            "assessment": band,
            "notes": args.notes or "",
        })
        save_log(args.case, entries)
        print(f"\nLogged to case '{args.case}'")


def cmd_report(args):
    entries = load_log(args.case_id)
    lines = [
        f"# Image Forensics Log -- Case {args.case_id}",
        "",
        f"Generated: {utc_now_iso()}",
        f"Total entries: {len(entries)}",
        "",
        "> Perceptual hash matches indicate visual similarity, not proof of "
        "identity or authorship. Treat as a lead to corroborate, not a "
        "conclusion.",
        "",
    ]
    if not entries:
        lines.append("_No entries yet._")
    for e in entries:
        if e["type"] == "inspect":
            lines.append(f"## Entry #{e['seq']} -- Inspection -- {e['timestamp_utc']}")
            lines.append(f"- **Examiner:** {e['examiner']}")
            lines.append(f"- **File:** {e['file']} (saved as `{e['file_ref']}`)")
            lines.append(f"- **Format:** {e['format']}, {e['dimensions']}")
            lines.append(f"- **SHA256:** `{e['sha256']}`")
            lines.append(f"- **aHash:** `{e['ahash']}`   **dHash:** `{e['dhash']}`")
            if e["exif"]:
                lines.append("- **EXIF metadata:**")
                for k, v in e["exif"].items():
                    lines.append(f"  - {k}: {v}")
            else:
                lines.append("- **EXIF metadata:** none found")
            if e.get("notes"):
                lines.append(f"- **Notes:** {e['notes']}")
        else:
            lines.append(f"## Entry #{e['seq']} -- Comparison -- {e['timestamp_utc']}")
            lines.append(f"- **Examiner:** {e['examiner']}")
            lines.append(f"- **A:** {e['file_a']}")
            lines.append(f"- **B:** {e['file_b']}")
            lines.append(f"- **SHA256 match:** {'yes' if e['sha256_match'] else 'no'}")
            lines.append(f"- **aHash distance:** {e['ahash_distance']}/64   **dHash distance:** {e['dhash_distance']}/64")
            lines.append(f"- **Assessment:** {e['assessment']}")
            if e.get("notes"):
                lines.append(f"- **Notes:** {e['notes']}")
        lines.append("")

    out_path = Path(args.output) if args.output else case_dir(args.case_id) / "image_forensics_report.md"
    out_path.write_text("\n".join(lines))
    print(f"Report written to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="EXIF metadata and perceptual-hash tools for photo verification.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_inspect = sub.add_parser("inspect", help="Extract EXIF metadata and compute hashes for one image")
    p_inspect.add_argument("file")
    p_inspect.add_argument("--case", help="Case ID to log this inspection under")
    p_inspect.add_argument("--examiner", help="Required if --case is given")
    p_inspect.add_argument("--notes")
    p_inspect.set_defaults(func=cmd_inspect)

    p_compare = sub.add_parser("compare", help="Compare two images for visual similarity")
    p_compare.add_argument("file_a")
    p_compare.add_argument("file_b")
    p_compare.add_argument("--case", help="Case ID to log this comparison under")
    p_compare.add_argument("--examiner", help="Required if --case is given")
    p_compare.add_argument("--notes")
    p_compare.set_defaults(func=cmd_compare)

    p_report = sub.add_parser("report", help="Generate a Markdown report for a case")
    p_report.add_argument("case_id")
    p_report.add_argument("--output")
    p_report.set_defaults(func=cmd_report)

    args = parser.parse_args()
    if getattr(args, "case", None) and not args.examiner:
        parser.error("--examiner is required when --case is given")
    args.func(args)


if __name__ == "__main__":
    main()
