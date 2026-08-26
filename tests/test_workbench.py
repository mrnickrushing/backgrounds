import tempfile
import unittest
from pathlib import Path

from workbench.core import AREAS, DIMENSIONS, WorkbenchError, audit_case, build_inquiries_from_templates, command_center, daily_queue, discrepancy_matrix, inquiry_template_preview, interview_plan_findings, load_case, new_case, phs_findings, render_report, save_case, source_trace_map, timeline_findings, validate_case_package
from workbench.security import hash_password, totp_code, verify_password, verify_totp
from workbench.store import WorkbenchStore
from workbench.web import case_summary, create_session, valid_session
from workbench.exports import docx_export, html_report, json_export, pdf_export


class WorkbenchTests(unittest.TestCase):
    def test_signed_session_expires_and_rejects_tampering(self):
        token = create_session("s" * 32, issued_at=1_000)
        self.assertTrue(valid_session(token, "s" * 32, now=1_001))
        self.assertFalse(valid_session(token, "s" * 32, now=50_000))
        self.assertFalse(valid_session(token + "x", "s" * 32, now=1_001))

    def test_password_hash_and_totp(self):
        encoded = hash_password("a sufficiently long password")
        self.assertTrue(verify_password("a sufficiently long password", encoded))
        self.assertFalse(verify_password("the wrong password", encoded))
        secret = "JBSWY3DPEHPK3PXP"
        self.assertTrue(verify_totp(secret, totp_code(secret, at=1_000), at=1_000))

    def test_store_case_session_audit_and_backup_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            store = WorkbenchStore(directory)
            store.ensure_bootstrap_user("admin", "a sufficiently long password")
            user = store.authenticate("admin", "a sufficiently long password")
            self.assertEqual(user["role"], "admin")
            token = store.create_session(user["id"])
            self.assertEqual(store.session_user(token)["username"], "admin")
            store.save_case(new_case("DB-1"), user, "case_created")
            self.assertEqual(store.load_case("DB-1")["case_id"], "DB-1")
            self.assertEqual(store.audit_events("DB-1")[0]["action"], "case_created")
            backup = store.backup(Path(directory) / "snapshot.db")
            self.assertTrue(backup.is_file())
            store.revoke_session(token)
            self.assertIsNone(store.session_user(token))

    def test_case_package_validation_and_notifications(self):
        data = new_case("PACKAGE-1", "Investigator", "2026-12-01")
        package = validate_case_package(data)
        self.assertEqual(package["case_id"], "PACKAGE-1")
        package["areas"].pop(next(iter(package["areas"])))
        with self.assertRaises(WorkbenchError):
            validate_case_package(package)
        with tempfile.TemporaryDirectory() as directory:
            store = WorkbenchStore(directory)
            store.ensure_bootstrap_user("admin", "a sufficiently long password")
            user = store.authenticate("admin", "a sufficiently long password")
            store.add_notification(user["id"], "PACKAGE-1", "review_submitted", "Case submitted")
            notice = store.notifications(user["id"])[0]
            self.assertIsNone(notice["read_at"])
            store.mark_notification_read(notice["id"], user["id"])
            self.assertIsNotNone(store.notifications(user["id"])[0]["read_at"])

    def test_exports_have_valid_container_signatures(self):
        data = new_case("EXPORT-1")
        self.assertTrue(pdf_export(data).startswith(b"%PDF-1.4"))
        self.assertTrue(docx_export(data).startswith(b"PK"))
        self.assertIn(b'"case_id": "EXPORT-1"', json_export(data))
        rendered = html_report(data)
        self.assertIn("Background Investigation Report", rendered)
        self.assertIn("Case EXPORT-1", rendered)

    def test_attachment_allowlist_hash_and_path_safety(self):
        with tempfile.TemporaryDirectory() as directory:
            store = WorkbenchStore(directory)
            store.save_case(new_case("FILES-1"), None, "case_created")
            item = store.save_attachment("FILES-1", "../../record.pdf", "application/pdf", b"%PDF-1.4\nexample", None)
            self.assertEqual(item["filename"], "record.pdf")
            loaded, content = store.attachment(item["id"])
            self.assertEqual(content, b"%PDF-1.4\nexample")
            self.assertEqual(len(loaded["sha256"]), 64)
            with self.assertRaises(ValueError):
                store.save_attachment("FILES-1", "payload.exe", "application/octet-stream", b"MZ", None)

    def test_case_round_trip_uses_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = save_case(new_case("2026-0001", "Investigator"), directory)
            self.assertEqual(load_case("2026-0001", directory)["case_id"], "2026-0001")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_new_case_contains_post_structure(self):
        data = new_case("CASE-1")
        self.assertEqual(tuple(data["areas"]), AREAS)
        self.assertEqual(tuple(data["dimensions"]), DIMENSIONS)
        self.assertEqual(data["timeline"], [])
        self.assertEqual(data["documents"], [])

    def test_timeline_findings_are_neutral_review_prompts(self):
        findings = timeline_findings([
            {"category": "employment", "label": "Employer A", "start_date": "2025-01-01", "end_date": "2025-03-01"},
            {"category": "residence", "label": "Apartment A", "start_date": "2025-01-15", "end_date": "2025-02-15"},
            {"category": "employment", "label": "Employer B", "start_date": "2025-04-01", "end_date": ""},
        ])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["kind"], "gap")
        self.assertIn("employment", findings[0]["message"].lower())

    def test_phs_findings_flag_missing_supporting_details(self):
        findings = phs_findings([
            {"id": "PHS-0001", "field_label": "Employment", "prior_value": "Employer A", "current_value": "Employer B", "reported_at": "", "source_ids": [], "disposition": ""},
        ])
        self.assertTrue(any(item["kind"] == "missing_date" for item in findings))
        self.assertTrue(any(item["kind"] == "missing_source" for item in findings))
        self.assertTrue(any(item["kind"] == "missing_disposition" for item in findings))

    def test_discrepancy_matrix_preserves_response_columns(self):
        matrix = discrepancy_matrix([
            {"id": "DSC-1", "title": "Job dates", "area": "employment_history", "candidate_statement": "Worked 2020-2021", "contrary_information": "Employer says 2020 only", "candidate_response": "Explained mismatch", "corroboration": "HR note", "resolution": "Clarified", "status": "resolved"},
        ])
        self.assertEqual(matrix[0]["candidate_response"], "Explained mismatch")
        self.assertEqual(matrix[0]["resolution"], "Clarified")

    def test_inquiry_templates_preview_and_batch_creation(self):
        preview = inquiry_template_preview(["employment_verification", "education_verification"], "2026-09-01")
        self.assertEqual([item["template_id"] for item in preview], ["employment_verification", "education_verification"])
        self.assertTrue(all(item["follow_up_due"] == "2026-09-01" for item in preview))
        data = new_case("CASE-TEMPLATES")
        created = build_inquiries_from_templates(data, ["employment_verification", "education_verification"], "2026-09-01")
        self.assertEqual(len(created), 2)
        data["inquiries"].extend(created)
        duplicate = build_inquiries_from_templates(data, ["employment_verification"], "2026-09-01")
        self.assertEqual(duplicate, [])

    def test_daily_queue_flags_due_and_release_work(self):
        queue = daily_queue([
            {
                "case_id": "QUEUE-1",
                "inquiries": [
                    {"id": "INQ-1", "source_label": "Employer", "status": "sent", "follow_up_due": "2026-08-20", "release_required": True, "release_attached": False},
                ],
                "review": {"status": "corrections_requested"},
            }
        ])
        kinds = {item["kind"] for item in queue}
        self.assertIn("missing_release", kinds)
        self.assertIn("overdue_follow_up", kinds)
        self.assertIn("supervisor_return", kinds)

    def test_command_center_groups_work_by_time_and_role(self):
        center = command_center([
            {
                "case_id": "CENTER-1",
                "target_date": "2026-08-25",
                "review": {"status": "pending"},
                "inquiries": [
                    {"id": "INQ-1", "source_label": "Employer", "status": "sent", "follow_up_due": "2026-08-25", "release_required": True, "release_attached": False},
                ],
            }
        ], role="supervisor")
        self.assertEqual(center["role"], "supervisor")
        self.assertTrue(center["today"])
        self.assertTrue(center["this_week"])
        self.assertTrue(center["risk"])
        self.assertEqual(center["role_card"]["title"], "Supervisor view")

    def test_interview_plan_findings_and_source_trace_map(self):
        findings = interview_plan_findings([
            {"id": "PLN-1", "subject": "Reference packet", "question": "Clarify address history", "source_ids": [], "discrepancy_ids": [], "recording_locator": ""},
        ])
        self.assertTrue(any(item["kind"] == "missing_source" for item in findings))
        self.assertTrue(any(item["kind"] == "missing_locator" for item in findings))
        data = new_case("TRACE-1")
        data["sources"].append({"id": "SRC-1", "label": "Employer file", "kind": "record", "location": "SYS-1"})
        data["areas"]["employment_history"]["source_ids"] = ["SRC-1", "SRC-X"]
        trace = source_trace_map(data)
        self.assertEqual(trace["sources"][0]["references"], ["Area narrative: Employment History Checks"])
        self.assertEqual(trace["orphan_source_ids"], ["SRC-X"])

    def test_legacy_case_is_normalized_on_load(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_dir = root / "LEGACY-1"
            case_dir.mkdir()
            (case_dir / "workbench.json").write_text(
                '{"case_id":"LEGACY-1","areas":{},"dimensions":{},"bias_relevant_findings":{},"inquiries":[],"discrepancies":[],"interviews":[],"sources":[],"review":{}}',
                encoding="utf-8",
            )
            data = load_case("LEGACY-1", root)
            self.assertEqual(data["timeline"], [])
            self.assertEqual(data["documents"], [])
            self.assertEqual(data["phs_changes"], [])
            self.assertEqual(data["interview_plans"], [])

    def test_closed_case_requires_complete_work(self):
        data = new_case("CASE-2")
        data["status"] = "closed"
        result = audit_case(data)
        self.assertFalse(result["ready"])
        self.assertTrue(any("areas incomplete" in item for item in result["errors"]))
        self.assertTrue(any("Pre-Investigatory" in item for item in result["errors"]))
        self.assertTrue(any(item["key"] == "coverage" for item in result["checklist"]))

    def test_report_preserves_mandated_area_order(self):
        report = render_report(new_case("CASE-3"))
        from workbench.core import AREA_LABELS
        positions = [report.index(f"### {AREA_LABELS[key]}") for key in AREAS]
        self.assertEqual(positions, sorted(positions))

    def test_browser_summary_uses_audit_metrics(self):
        summary = case_summary(new_case("CASE-4", "Investigator", "2026-12-01"))
        self.assertEqual(summary["areas_total"], 12)
        self.assertEqual(summary["open_inquiries"], 0)
        self.assertEqual(summary["target_date"], "2026-12-01")


if __name__ == "__main__":
    unittest.main()
