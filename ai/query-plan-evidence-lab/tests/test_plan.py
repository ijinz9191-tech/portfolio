import json
import subprocess
import sys
import unittest

from planlab import EvidenceError, reproduce
from planlab.model import verify


class QueryPlanTests(unittest.TestCase):
    def test_before_scan_after_covering_index_with_same_tenant_rows(self):
        result = reproduce()
        self.assertEqual(result["decision"], "INDEX_PLAN_VERIFIED")
        self.assertEqual(result["fixture_rows"], 4000)
        self.assertTrue(result["results_equal"] and result["tenant_isolated"])
        self.assertGreater(result["result_rows"], 0)

    def test_result_change_rejects_evidence(self):
        with self.assertRaisesRegex(EvidenceError, "changed"):
            verify([(1, "tenant-07", 200)], [], ["SCAN synthetic_orders"],
                   ["SEARCH synthetic_orders USING COVERING INDEX idx_orders_tenant_status_created_order"])

    def test_cross_tenant_row_rejects_evidence(self):
        with self.assertRaisesRegex(EvidenceError, "cross-tenant"):
            verify([(1, "tenant-01", 200)], [(1, "tenant-01", 200)], ["SCAN synthetic_orders"],
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


if __name__ == "__main__":
    unittest.main()
