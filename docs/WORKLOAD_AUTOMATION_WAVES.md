# Workload Automation Waves

Purpose: reduce administrative load in CDCR background-investigation work without replacing eSOPH, agency policy, investigator judgment, or approved systems. All examples and tests use fictional, non-PII data.

Status as of 2026-08-27: Waves 1 through 11 are merged to `main`. Wave 12 adds a case handoff brief and is pending merge.

- Wave 1 / 2 / 3 merged in PR #12, merge commit `588dc00`
- Wave 4 merged in PR #13, merge commit `0a638ef`
- Wave 5 merged in PR #14, merge commit `810b109`
- Wave 6 merged in PR #16, merge commit `2cdfb16`
- Wave 7 merged in PR #17, merge commit `1d58cdc`
- Wave 8 merged in PR #18, merge commit `83525c7`
- Wave 9 merged in PR #19, merge commit `aebe2c5`
- Wave 10 merged in PR #20, merge commit `8bb8e45`
- Wave 11 merged in PR #22, merge commit `f9146a6`

## Wave 12 — Case handoff brief

- Copy or download a concise case brief that captures stage, target date, coverage, open work, and review prompts.
- Keep the brief grounded in the existing audit and checklist data so investigators can paste it into handoff notes or shift summaries.
- Gates: browser walkthrough, clipboard/download round-trip, audit-summary formatting, mobile-width check.

## Wave 11 — Bulk queue triage

- Select visible cases from the queue table for batch work without leaving the dashboard.
- Copy selected case IDs, export selected rows, or update the selected cases to a new stage, priority, or target date in one action.
- Clear or rebuild the visible selection as filters change so the batch action matches the current queue slice.
- Gates: browser walkthrough, checkbox selection, bulk export, bulk status update, mobile-width check.

## Wave 10 — Current-queue export

- Export the current filtered case queue to CSV for offline follow-up, note taking, or external review.
- Keep the export aligned with the active dashboard filters so the download matches what the investigator is seeing.
- Add a keyboard shortcut and help entry so the export path is fast to discover in daily work.
- Gates: browser walkthrough, CSV round-trip, empty-state handling, mobile-width check.

## Wave 9 — Portable saved views

- Export the command-center filters and saved views to JSON so the current workload slice can move between browsers or machines.
- Import exported views from a file or pasted JSON, merging them into local storage with duplicate suppression.
- Optional filter restore during import so a transferred dashboard can reopen on the same queue slice when needed.
- Gates: browser walkthrough, export/import round-trip, duplicate suppression, mobile-width check.

## Wave 8 — Dashboard keyboard shortcuts

- Keyboard shortcuts for search focus, saved views, copy-link, lens switching, and clearing filters.
- A shortcut help modal so investigators can discover the commands without reading source.
- The shortcuts ignore typed input and only activate on the dashboard shell.
- Gates: browser walkthrough, keybinding suppression in inputs, modal help, mobile-width check.

## Wave 7 — Shareable dashboard links

- URL-backed command-center filters for search, stage, due state, and open-only views.
- Copyable dashboard links that reopen the same queue slice in another browser or device.
- Local saved views still handle frequently used queue slices, with delete support and mobile-friendly wrapping.
- Gates: browser walkthrough, saved-view persistence, URL-sync assertions, mobile-width check.

## Wave 6 — Saved views and fast filters

- Persisted command-center filters for search, stage, due state, and open-only views.
- Quick lenses for all cases, open cases, overdue work, and due-soon work.
- Local saved views for frequently used queue slices, with delete support and mobile-friendly wrapping.
- Gates: browser walkthrough, saved-view persistence, filter-sync assertions, mobile-width check.

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

## Remaining follow-on work

- Final report-template alignment once the approved CDCR form is uploaded.
- Any integration work that touches live systems remains gated on written authorization and a supported interface.
