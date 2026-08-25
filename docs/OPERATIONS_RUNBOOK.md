# Operations and Recovery Runbook

## Service checks

- Liveness: `GET /healthz` returns the deployed version and no case information.
- Readiness: `GET /readyz` performs a database quick check and returns 503 if storage is unhealthy.
- Authenticated administrators can inspect `/api/system` for active record counts and the latest verified snapshot name.
- Railway logs are structured JSON and exclude request bodies, credentials, case contents, and query strings.

## Backups

The service creates an integrity-checked SQLite snapshot every 24 hours and retains the latest 14 under `/data/backups`. Administrators can trigger an additional snapshot with `POST /api/backups`. Railway volume-level backups should also be enabled in the Railway project when the account plan supports them; application snapshots on the same volume do not replace off-volume disaster recovery.

Restore exercise:

1. Stop writes or deploy a maintenance copy.
2. Download the intended snapshot through an approved administrative channel.
3. Run `sqlite3 snapshot.db 'PRAGMA integrity_check'` and require `ok`.
4. Preserve the current database before replacement.
5. Replace `/data/workbench.db`, start the service, and verify `/readyz`, authentication, case counts, an attachment hash, and an export.
6. Record the operator, timestamps, source snapshot, and verification results.

## Incident response

1. Disable public access or rotate the Railway domain if exposure is suspected.
2. Rotate `WORKBENCH_PASSWORD`, `WORKBENCH_SESSION_SECRET`, and any affected user credentials.
3. Preserve Railway and audit logs; do not modify suspected records.
4. Determine affected users, cases, attachments, and time window.
5. Follow agency reporting and evidence-preservation requirements.
6. Restore only from a verified snapshot and document every action.

## Deployment and rollback

Every change must pass GitHub CI, merge through a pull request, deploy to Railway, reach `SUCCESS`, and pass liveness, readiness, unauthorized-route, login, persistence, and content-type checks. Roll back by redeploying the last known-good Railway deployment; schema changes are additive so earlier application versions retain readable data.

## Owner-gated controls

Before real applicant information is entered, obtain written approval for hosting, identity, retention, backup location, incident handling, and any eSOPH or CDCR integration. The application does not claim CJIS/CDCR authorization by itself.
