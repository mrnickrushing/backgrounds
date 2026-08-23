# Identity Correlation Worksheet

Documents *why* an account is believed to belong to a candidate, by
recording known candidate identifiers alongside what was actually observed
on each reviewed account, and producing a consistent weighted score. No
dependencies beyond the Python 3 standard library.

**The score is a documentation aid, not a determination.** It exists so
your reasoning is written down the same way every time — the final call is
still the investigator's, per agency policy.

## Commands

```bash
# Start a worksheet for a candidate
python3 identity_correlation.py new CASE_ID --name "Jane Q. Candidate" --dob 1990-01-01

# Record known identifiers (each flag is repeatable)
python3 identity_correlation.py set-candidate CASE_ID \
  --alias "jqcandidate" \
  --address "123 Main St, Sacramento, CA" \
  --employer "Acme Corp" \
  --phone "555-123-4567" \
  --email "jane@example.com" \
  --school "Sac State" \
  --associate "John Smith"

# Log a reviewed account and what matched
python3 identity_correlation.py add-account CASE_ID \
  --platform Instagram --username jqcandidate90 \
  --url https://instagram.com/jqcandidate90 \
  --examiner "J. Doe" \
  --matched-alias "handle is a known variant of candidate's name" \
  --location "Sacramento, CA" \
  --employer-mention "Acme Corp" \
  --associate "John Smith" \
  --photo /path/to/profile.jpg \
  --notes "Bio and tagged photos consistent with application"

# Generate a Markdown report for the case file
python3 identity_correlation.py report CASE_ID
```

Case data is written to `../../cases/CASE_ID/` (gitignored — never commit
case data).
