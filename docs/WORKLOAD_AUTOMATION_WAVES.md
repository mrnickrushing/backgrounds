# Workload Automation Waves

Purpose: reduce administrative load in CDCR background-investigation work without replacing eSOPH, agency policy, investigator judgment, or approved systems. All examples and tests use fictional, non-PII data.

## Wave 1 — Life history and documents

- A chronological employment, residence, education, military, relationship, and legal-event timeline.
- Gap/overlap findings shown as prompts for investigator review, never as conclusions.
- Document requirement tracker for originals, copies, sealed records, releases, receipt, verification, and return status.
- Gates: schema validation, date-range tests, browser desktop/mobile walkthrough, no raw-document duplication.

## Wave 2 — Disclosure and discrepancy control

- PHS change ledger with prior value, new value, date reported, source locator, and investigator disposition.
- Candidate statement, contrary information, candidate response, corroboration, and resolution matrix.
- Gates: immutable history tests, role checks, report traceability tests.

## Wave 3 — Inquiries and daily workload

- Reusable inquiry templates, batch creation preview, release prerequisites, target due dates, and a daily action queue.
- Explicitly no email, eSOPH, records-system, or web-platform automation until written authorization and a supported interface exist.
- Gates: no-send guarantee, due-date calculation tests, filter and permission tests.

## Wave 4 — Interviews and source traceability

- Interview planning packets that link disclosed topics, discrepancies, source identifiers, and approved recording locators.
- Source-to-finding map across inquiries, interviews, discrepancies, area narratives, dimensions, and report sections.
- Gates: source-link validation, human-review language, browser walkthrough.

## Wave 5 — Caseload command center

- Today/this-week queue for overdue work, target-date risk, missing releases, pending source responses, and supervisor returns.
- Investigator and supervisor views with no automated suitability or hiring recommendation.
- Gates: role matrix, no-PII dashboard assertions, production health and browser verification.

## Owner-gated work

- Exact CDCR report template mapping begins only after the approved form is supplied.
- eSOPH, agency records, identity, email, and document-system integrations remain disabled pending written authorization, interfaces, and credentials.
