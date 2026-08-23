# Image Forensics

EXIF metadata extraction and perceptual-hash comparison for verifying
photos found during a background investigation. Requires Pillow.

```bash
pip install -r requirements.txt
```

## What it's for

- **EXIF metadata** (`inspect`) — camera make/model, original capture
  timestamp, GPS coordinates if present. Most social platforms strip this
  on upload, so it's most useful on originals a candidate hands over
  directly (interview, email, text) rather than what you download from a
  profile.
- **Perceptual hashing** (`inspect` / `compare`) — a fingerprint of what an
  image *looks like*, robust to resizing/recompression, so you can:
  - catch the same profile photo reused across multiple accounts/aliases
  - catch a stolen/stock photo (compare against a known original)
  - confirm two copies claimed to be "the same photo" actually are

A hash match is a lead to document and corroborate, not proof on its own —
say so in your notes the same way you would for any other lead.

## Commands

```bash
# Inspect a single image
python3 image_forensics.py inspect /path/to/photo.jpg

# Inspect and log it against a case (copies + hashes the file, same
# pattern as the other tools; --examiner is required with --case)
python3 image_forensics.py inspect /path/to/photo.jpg \
  --case 2026-0142 --examiner "J. Doe" --notes "Profile photo from Instagram account"

# Compare two images for visual similarity
python3 image_forensics.py compare /path/to/a.jpg /path/to/b.jpg \
  --case 2026-0142 --examiner "J. Doe" --notes "Compare against LinkedIn profile photo"

# Generate a Markdown report for the case file
python3 image_forensics.py report 2026-0142
```

Case data is written to `../../cases/CASE_ID/` (gitignored — never commit
case data), consistent with `evidence_logger` and `identity_correlation`.
