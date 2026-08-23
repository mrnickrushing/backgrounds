# Backgrounds

Small, dependency-free tools for documenting social media / OSINT findings
during background investigations — built for use alongside, not instead of,
your agency's approved procedures and platforms.

They exist to solve one recurring problem: a social media account that
*looks* like it belongs to a candidate is only useful in an investigative
file if you can show, consistently and defensibly, what you found and why
you believe it's them. These tools structure that documentation so it holds
up.

## What's here

| Tool | Purpose |
|---|---|
| [`tools/evidence_logger`](tools/evidence_logger) | Tamper-evident, hash-chained log of findings (URLs, screenshots, notes). Detects after-the-fact edits and can archive a URL to the Wayback Machine. |
| [`tools/identity_correlation`](tools/identity_correlation) | Worksheet that records known candidate identifiers next to what was observed on a given account, and scores the overlap so the reasoning is written down the same way every time. |
| [`tools/image_forensics`](tools/image_forensics) | EXIF metadata extraction and perceptual-hash comparison, to check a photo's capture details and catch a reused/stolen profile photo across accounts. |

`evidence_logger` and `identity_correlation` are single-file Python 3
scripts using only the standard library — clone and run, nothing to
install. `image_forensics` additionally requires Pillow (`pip install -r
tools/image_forensics/requirements.txt`).

## Quick start

```bash
# Log a finding
python3 tools/evidence_logger/evidence_logger.py init 2026-0142
python3 tools/evidence_logger/evidence_logger.py add 2026-0142 \
  --examiner "J. Doe" --url "https://example.com/profile/123" \
  --description "Public profile, appears to match candidate" \
  --file /path/to/screenshot.png --archive

# Document the identity correlation
python3 tools/identity_correlation/identity_correlation.py new 2026-0142 --name "Jane Q. Candidate"
python3 tools/identity_correlation/identity_correlation.py set-candidate 2026-0142 \
  --employer "Acme Corp" --address "123 Main St, Sacramento, CA"
python3 tools/identity_correlation/identity_correlation.py add-account 2026-0142 \
  --platform Instagram --username jqcandidate90 --url https://instagram.com/jqcandidate90 \
  --examiner "J. Doe" --employer-mention "Acme Corp" --location "Sacramento, CA"

# Check a photo's EXIF data and compare it against another
python3 tools/image_forensics/image_forensics.py inspect /path/to/photo.jpg \
  --case 2026-0142 --examiner "J. Doe"
python3 tools/image_forensics/image_forensics.py compare /path/to/photo.jpg /path/to/other.jpg \
  --case 2026-0142 --examiner "J. Doe"

# Generate reports for the case file
python3 tools/evidence_logger/evidence_logger.py report 2026-0142
python3 tools/identity_correlation/identity_correlation.py report 2026-0142
python3 tools/image_forensics/image_forensics.py report 2026-0142
```

See each tool's README for the full command reference.

## How case data is handled

Everything either tool writes goes under `cases/<CASE_ID>/`, which is
`.gitignore`d. Case data contains candidate PII and must never be committed
to this repo — this repo is for the tooling, not the case files. Back up
`cases/` the same way you'd back up any other investigative record, per
your agency's retention policy.

## Read this before using either tool

These are documentation aids, not evidentiary authority and not automation:

- **They don't scrape, log in as, friend, or otherwise interact with any
  platform or account.** You do the looking; the tools only record what you
  saw. Automated collection or pretext accounts may violate platform Terms
  of Service and, depending on your agency's policy, may not be permitted
  investigative technique at all — when in doubt, ask your supervisor or
  agency counsel before doing anything beyond viewing public information.
- **The identity correlation score is not a determination.** It's a
  consistent way to write down which known identifiers matched what you
  found. Whether that adds up to "this is the candidate" is your judgment
  call, made per your agency's standards.
- **This does not replace agency-licensed OSINT/background platforms**
  (e.g. Skopenow, TLO, and similar) if your department already uses one.
  Use those for the actual investigative legwork where required; use these
  tools to keep your own documentation consistent and defensible.
- **Chain of custody still depends on you.** `verify` will catch a log file
  edited after the fact, but it can't prove the file wasn't swapped for a
  different one entirely — follow your agency's evidence handling process
  for anything that needs to hold up beyond your own working notes.

## Roadmap

Ideas for next tools, not yet built:

- PDF export of reports for direct inclusion in a case file.
- archive.today submission alongside the Wayback Machine.

## License

For personal/professional use. No warranty — verify tool output before
relying on it for anything that matters.
