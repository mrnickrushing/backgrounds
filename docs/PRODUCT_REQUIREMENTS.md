# Investigator Workbench product requirements

## Purpose

Reduce administrative load during CDCR peace-officer background investigations without replacing eSOPH, agency policy, investigator judgment, or approved records systems.

## Confirmed workload addressed

The workbench supports the publicly documented OPOS Background Investigator duties:

- Inquiry initiation, response review, nonresponse follow-up, field contacts, and discrepancy development (40%).
- Evidence evaluation, file maintenance, legal/policy-aware documentation, clearance narratives, and withholding recommendations (25%).
- Recorded Pre-Investigatory Interviews and newly disclosed information (20%).
- Training, Duty Sergeant, staff supervision, hiring events, travel, timekeeping, and administrative work (15%).

Source: [CDCR Background Investigator duty statement, revised February 2025](https://calcareers.ca.gov/CalHrPublic/FileDownload.aspx?aid=27267922&name=BIUSGTCSC%282.2025%29OPOS.pdf).

## Product modules

1. Caseload dashboard and aging indicators.
2. Twelve-area completion tracker.
3. Inquiry and follow-up tracker.
4. Source register.
5. Discrepancy and corroboration matrix.
6. Interview register and preparation support.
7. Ten-dimension and bias-relevant narrative workspace.
8. POST-ordered narrative report assembler.
9. Pre-close quality-control audit.
10. Templates and desk guides.

## Implemented browser workspace

The local browser interface provides the caseload dashboard, required-area completion, inquiries, discrepancies, interviews, source locators, report narratives, readiness findings, and activity history. It binds to `127.0.0.1` by default and uses the same ignored, user-private case files as the CLI.

## Non-goals and safety boundaries

- No suitability score, automated hiring recommendation, or automated disqualification.
- No facial recognition, account scraping, pretexting, password collection, or private-account access.
- No replacement for eSOPH or direct integration without written CDCR authorization and a supported interface.
- No case data in Git. Local case files are ignored and created with user-only permissions.
- No medical or psychological inference. Information requiring professional evaluation must be routed according to agency policy.
- Generated narrative is always a draft requiring source-by-source human verification.

## Required report structure

The report workspace preserves the ten POST Background Investigation Dimensions, a separate bias-relevant findings section, and the twelve areas of investigation in the order required by Commission Regulation 1953.

Source: [POST Background Investigation Manual](https://post.ca.gov/portals/0/post_docs/publications/background-investigation-manual/Background_Investigation.pdf).
