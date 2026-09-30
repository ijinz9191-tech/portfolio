import json
import subprocess
import sys
import unittest

from planlab import EvidenceError, reproduce
from planlab.model import verify, verify_cursor_pages, verify_group_totals


class QueryPlanTests(unittest.TestCase):
    def test_before_scan_after_covering_index_with_same_tenant_rows(self):
        result = reproduce()
        self.assertEqual(result["decision"], "INDEX_PLAN_VERIFIED")
        self.assertEqual(result["fixture_rows"], 4000)
        self.assertTrue(result["results_equal"] and result["tenant_isolated"] and result["status_filtered"])
        self.assertTrue(result["cursor_pages_match"])
        self.assertTrue(result["group_totals_match"])
        self.assertGreater(result["group_count"], 0)
        self.assertGreater(result["result_rows"], 0)

    def test_result_change_rejects_evidence(self):
        with self.assertRaisesRegex(EvidenceError, "changed"):
            verify([(1, "tenant-07", "PENDING", 200)], [], ["SCAN synthetic_orders"],
                   ["SEARCH synthetic_orders USING COVERING INDEX idx_orders_tenant_status_created_order"])

    def test_cross_tenant_row_rejects_evidence(self):
        with self.assertRaisesRegex(EvidenceError, "cross-tenant"):
            verify([(1, "tenant-01", "PENDING", 200)], [(1, "tenant-01", "PENDING", 200)], ["SCAN synthetic_orders"],
                   ["SEARCH synthetic_orders USING COVERING INDEX idx_orders_tenant_status_created_order"])

    def test_missing_index_plan_rejects_evidence(self):
        with self.assertRaisesRegex(EvidenceError, "index"):
            verify([], [], ["SCAN synthetic_orders"], ["SCAN synthetic_orders"])

    def test_reproducible_hash_and_cli(self):
        first, second = reproduce(), reproduce()
        self.assertEqual(first["evidence_sha256"], second["evidence_sha256"])
        child = subprocess.run([sys.executable, "-B", "-m", "planlab"], capture_output=True, text=True)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertEqual(json.loads(child.stdout)["evidence_sha256"], first["evidence_sha256"])

    def test_duplicate_or_reordered_rows_reject_evidence(self):
        rows = [(2, "tenant-07", "PENDING", 201), (1, "tenant-07", "PENDING", 200)]
        plans = (["SCAN synthetic_orders"],
                 ["SEARCH synthetic_orders USING COVERING INDEX idx_orders_tenant_status_created_order"])
        with self.assertRaisesRegex(EvidenceError, "deterministic"):
            verify(rows, rows, *plans)
        rows = [(1, "tenant-07", "PENDING", 200), (1, "tenant-07", "PENDING", 200)]
        with self.assertRaisesRegex(EvidenceError, "unique"):
            verify(rows, rows, *plans)

    def test_time_window_violation_rejects_evidence(self):
        rows = [(1, "tenant-07", "PENDING", 199)]
        with self.assertRaisesRegex(EvidenceError, "time window"):
            verify(rows, rows, ["SCAN synthetic_orders"],
                   ["SEARCH synthetic_orders USING COVERING INDEX idx_orders_tenant_status_created_order"])

    def test_status_violation_rejects_evidence(self):
        rows = [(1, "tenant-07", "DONE", 200)]
        with self.assertRaisesRegex(EvidenceError, "wrong-status"):
            verify(rows, rows, ["SCAN synthetic_orders"],
                   ["SEARCH synthetic_orders USING COVERING INDEX idx_orders_tenant_status_created_order"])

    def test_cursor_gap_and_duplicate_reject_evidence(self):
        a = (1, "tenant-07", "PENDING", 200)
        b = (2, "tenant-07", "PENDING", 201)
        c = (3, "tenant-07", "PENDING", 202)
        with self.assertRaisesRegex(EvidenceError, "duplicate"):
            verify_cursor_pages([a], [a], [a, b])
        with self.assertRaisesRegex(EvidenceError, "gap"):
            verify_cursor_pages([a], [c], [a, b])

    def test_full_group_totals_reject_hidden_change(self):
        with self.assertRaisesRegex(EvidenceError, "group totals changed"):
            verify_group_totals([("tenant-07", "PENDING", 10)], [("tenant-07", "PENDING", 9)])
        with self.assertRaisesRegex(EvidenceError, "duplicate group key"):
            verify_group_totals([("tenant-07", "PENDING", 1), ("tenant-07", "PENDING", 2)],
                                [("tenant-07", "PENDING", 1), ("tenant-07", "PENDING", 2)])


if __name__ == "__main__":
    unittest.main()
