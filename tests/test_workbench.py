import tempfile
import unittest
from pathlib import Path

from workbench.core import AREAS, DIMENSIONS, audit_case, load_case, new_case, render_report, save_case
from workbench.security import hash_password, totp_code, verify_password, verify_totp
from workbench.store import WorkbenchStore
from workbench.web import case_summary, create_session, valid_session


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
