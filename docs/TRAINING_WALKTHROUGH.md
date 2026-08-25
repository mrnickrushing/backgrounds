# Investigator Workbench Training Walkthrough

Use only fictional, non-identifying training data. This walkthrough teaches the workbench sequence; controlling agency policy, supervisor direction, and approved systems control the actual investigation.

1. Create a case with a non-PII training identifier such as `TRAINING-2026-002`, an assigned investigator, and a target date.
2. Open the case Overview. Treat the Guided case plan as a progress aid, not a substitute for a case checklist required by the agency.
3. Register an approved-system source locator. Do not paste sensitive source material into the workbench.
4. Add one fictional inquiry, including the required release state and follow-up date. Update it when a fictional response is received.
5. Add a fictional pre-investigatory interview and record only the approved recording locator.
6. Draft each required-area narrative and POST-dimension narrative using fictional source identifiers.
7. Add a fictional discrepancy with both accounts, then record the candidate response, corroboration, and resolution.
8. Review the checklist and quality warnings. Open the print preview and verify citations before requesting supervisory review.
9. Submit for review. A review alert is created. A supervisor can approve or return the case with a comment; mark alerts read after acting on them.
10. Export the fictional case package from Files as JSON. An administrator can import that package only into a new identifier; import never overwrites an existing case and does not include attachments.

## Recovery boundaries

- The Account screen creates an integrity-checked SQLite backup on the protected application volume. It is a recovery artifact, not an attachment or email export.
- A JSON case-package import is intentionally separate from a database restore. It cannot replace users, sessions, audit history, attachments, or an existing case.
- Test import and restoration procedures with fictional data before relying on them operationally.
