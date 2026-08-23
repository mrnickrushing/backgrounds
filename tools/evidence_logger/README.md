# Evidence Logger

A case-scoped, tamper-evident log for documenting social media / OSINT
findings. No dependencies beyond the Python 3 standard library.

Each entry is timestamped and hash-chained to the one before it, so any
after-the-fact edit to the log file is detectable with `verify`.

## Commands

```bash
# Start a new case
python3 evidence_logger.py init CASE_ID

# Log a finding (all local files get copied + hashed; --archive is optional
# and calls the public Internet Archive "Save Page Now" service)
python3 evidence_logger.py add CASE_ID \
  --examiner "J. Doe" \
  --url "https://example.com/profile/123" \
  --description "Public profile, appears to match candidate" \
  --file /path/to/screenshot.png \
  --notes "Bio lists same employer as application" \
  --archive

# Hash any file on its own (e.g. to double-check a copy)
python3 evidence_logger.py hash /path/to/file

# Check the log hasn't been altered
python3 evidence_logger.py verify CASE_ID

# Generate a Markdown report for the case file
python3 evidence_logger.py report CASE_ID
```

Case data is written to `../../cases/CASE_ID/` (gitignored — never commit
case data).
