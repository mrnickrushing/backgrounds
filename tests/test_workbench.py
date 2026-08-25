import tempfile
import unittest

from workbench.core import AREAS, DIMENSIONS, audit_case, load_case, new_case, render_report, save_case
from workbench.web import case_summary, create_session, valid_session


class WorkbenchTests(unittest.TestCase):
    def test_signed_session_expires_and_rejects_tampering(self):
        token = create_session("s" * 32, issued_at=1_000)
        self.assertTrue(valid_session(token, "s" * 32, now=1_001))
        self.assertFalse(valid_session(token, "s" * 32, now=50_000))
        self.assertFalse(valid_session(token + "x", "s" * 32, now=1_001))
    def test_case_round_trip_uses_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = save_case(new_case("2026-0001", "Investigator"), directory)
            self.assertEqual(load_case("2026-0001", directory)["case_id"], "2026-0001")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_new_case_contains_post_structure(self):
        data = new_case("CASE-1")
        self.assertEqual(tuple(data["areas"]), AREAS)
        self.assertEqual(tuple(data["dimensions"]), DIMENSIONS)

    def test_closed_case_requires_complete_work(self):
        data = new_case("CASE-2")
        data["status"] = "closed"
        result = audit_case(data)
        self.assertFalse(result["ready"])
        self.assertTrue(any("areas incomplete" in item for item in result["errors"]))
        self.assertTrue(any("Pre-Investigatory" in item for item in result["errors"]))

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
