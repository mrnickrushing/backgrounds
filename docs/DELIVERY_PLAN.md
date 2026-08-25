# Production Delivery Plan

Status: application-controlled work completed and released on 2026-08-25. Owner-gated integrations remain intentionally disabled as described below.

This plan turns the Investigator Workbench prototype into a safer operational application. Each wave is independently releasable and must pass its gates before merge and deployment.

## Wave 1 - Identity, durable data, and auditability

Files: `workbench/store.py`, `workbench/security.py`, `workbench/web.py`, login/account UI, tests, deployment configuration.

- SQLite WAL database on the mounted `/data` volume, with transactional case writes and migration of existing JSON case files.
- Individual accounts with scrypt password hashes, administrator/investigator/supervisor/reviewer roles, disabled-account enforcement, and bootstrap administration.
- Signed server-side sessions, idle and absolute expiry, session revocation, login throttling, optional TOTP MFA, and password changes.
- Append-only audit events for authentication, case creation, reads of exports, and every mutation.
- Database snapshot backup and restore validation commands.

Gates: schema migration tests, password/session/TOTP tests, concurrent write tests, authentication browser walkthrough, backup/restore round trip, live health and unauthorized-route checks.

## Wave 2 - Case operations and supervision

Files: schema migration, `workbench/web.py`, dashboard and case UI, tests, desk guide.

- Assignment, supervisor review states, review comments, return-for-correction, and approval.
- Global search, status/assignee/due-state filters, sorting, and paginated queues.
- Follow-up calendar, overdue/approaching deadlines, notification inbox, reusable templates, and bulk follow-up scheduling.
- Archive/restore and retention metadata without destructive automatic deletion.

Gates: permission matrix tests, workflow-transition tests, query/filter tests, desktop/mobile browser walkthrough.

## Wave 3 - Controlled records and exports

Files: attachment service, export service, API/UI, tests, documentation.

- Attachment metadata and binary storage outside the web root, strict limits, allowlist, hash verification, safe download headers, and audit events.
- Narrative exports to DOCX and PDF plus a complete JSON case package and validated import preview.
- No direct eSOPH automation without an agency-approved API; retain locator and upload-status workflows.

Gates: malicious filename/type tests, authorization tests, hash round trip, valid DOCX/PDF signatures, import validation.

## Wave 4 - Operations and recovery

Files: CI workflow, health/readiness endpoints, runbooks, Railway configuration, release notes.

- CI for unit tests, syntax, packaging, security checks, and Docker smoke testing.
- Structured privacy-safe logs, health/readiness/version endpoints, request identifiers, and backup status.
- Backup, restore, incident response, retention, acceptable-use, staging, and recovery runbooks.
- Railway production deployment verification and documented owner-gated CDCR approval boundary.

Gates: green CI, container health, authentication boundary, persistent-write smoke test, backup status, rollback documentation, clean main branch.

## Owner-gated integrations

Real eSOPH/CDCR identity, records, email, and document-system integrations require agency-provided APIs, credentials, contracts, and written authorization. The workbench will expose documented adapter boundaries and safe manual workflows until those inputs exist.
