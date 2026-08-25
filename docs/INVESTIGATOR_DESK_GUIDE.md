# Investigator Workbench desk guide

This guide is a workflow aid, not CDCR policy, legal advice, or POST-certified training. Current CDCR directives, local procedures, supervisor direction, and approved systems control.

## Case opening

1. Confirm assignment and applicable candidate type.
2. Create the local case using a non-PII case identifier.
3. Set the target date and current stage.
4. Review the complete eSOPH PHS and releases.
5. Build an inquiry for every disclosed employer, school, residence, law-enforcement jurisdiction, court, reference, and other required source.
6. Mark whether each inquiry requires a release and confirm it is attached before sending.
7. Register source locators, not duplicate sensitive source contents, when the approved system already retains the record.

## Pre-Investigatory Interview

### Before

- Compare the PHS for missing dates, unexplained gaps, overlapping addresses or employment, incomplete dispositions, and internal contradictions.
- Prepare questions for every open issue without assuming deception.
- Confirm the approved recording procedure and equipment.
- Do not include prohibited pre-offer medical, disability, psychological, or family medical inquiries.

### During

- Explain the process and continuing disclosure obligation according to current policy.
- Address the PHS systematically.
- Distinguish a new disclosure from clarification of an existing disclosure.
- Record exact facts, dates, sources, and the candidate's explanation.
- Avoid promising a result.

### After

- Register the interview and recording locator.
- Confirm the required eSOPH upload.
- Add each unresolved conflict to the discrepancy matrix.
- Add all newly identified sources and secondary references as inquiries.
- Update the case stage and next actions.

## Inquiry cycle

Every inquiry should show:

- Required investigation area
- Source type and label
- Approved contact method
- Release requirement and attachment state
- Date sent
- Follow-up date
- Response state
- Concise response summary
- Approved-system or local evidence locator

Document unsuccessful attempts. A nonresponse is a work item until resolved under current policy; it is not adverse evidence by itself.

## Discrepancy handling

Record separately:

1. Candidate statement
2. Contrary information
3. Source identifiers
4. Relevant investigation area
5. Potentially relevant POST dimensions
6. Candidate response
7. Independent corroboration
8. Resolution or reason it remains unresolved

The tool never calculates credibility or suitability. Those remain investigator and hiring-authority judgments under approved standards.

## Report preparation

The generated Markdown is a working draft. Review it line by line and ensure:

- Material information appears where readers will find it.
- Fact, allegation, source statement, investigator observation, and candidate explanation remain distinguishable.
- Each material assertion is supported by a registered source.
- Unsupported impressions and conclusory language are removed.
- Findings relevant to the ten dimensions are summarized neutrally.
- Bias-relevant facts are documented without performing the psychologist's assessment.
- The twelve required areas remain in mandated order.
- Withholding recommendations identify the applicable authority and supporting facts under current CDCR procedure.

## Closing quality check

Run `python3 -m workbench audit CASE_ID`. Resolve every error and review every warning. The audit is intentionally conservative and cannot confirm compliance with nonpublic CDCR procedures.

## Privacy and handling

- Never commit `cases/` or exported reports containing candidate information.
- Use a case identifier rather than a candidate name in filenames and terminal commands.
- Keep recordings and source records only in approved storage.
- Do not paste candidate information into public AI services.
- Do not use the workbench to scrape accounts, contact subjects through pretext, infer protected characteristics, or perform facial recognition.
- Follow CDCR retention, access, disclosure, and incident-reporting procedures.
