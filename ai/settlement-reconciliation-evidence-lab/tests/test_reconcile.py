import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reconcile import EvidenceError, reconcile


GOOD = {"postings": [{"id": "c-1", "merchant": "m-1", "amount_won": 1200},
                     {"id": "r-1", "merchant": "m-1", "amount_won": -300}],
        "settlements": [{"id": "r-1", "merchant": "m-1", "amount_won": -300},
                        {"id": "c-1", "merchant": "m-1", "amount_won": 1200}]}


class ReconcileTests(unittest.TestCase):
    def test_matching_postings(self):
        result = reconcile(GOOD)
        self.assertEqual(result["decision"], "MATCH")
        self.assertEqual(result["matched_ids"], ["c-1", "r-1"])
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["merchant_totals"], [{"merchant": "m-1", "posting_won": 900,
                                                      "settlement_won": 900, "delta_won": 0}])

    def test_offsetting_mismatches_remain_visible(self):
        data = {"postings": [{"id": "a", "merchant": "m", "amount_won": 100},
                             {"id": "b", "merchant": "m", "amount_won": -100}],
                "settlements": [{"id": "a", "merchant": "m", "amount_won": 90},
                                {"id": "b", "merchant": "m", "amount_won": -90}]}
        result = reconcile(data)
        self.assertEqual(result["merchant_totals"][0]["delta_won"], 0)
        self.assertEqual(result["decision"], "REVIEW_REQUIRED")
        self.assertEqual(len(result["issues"]), 2)

    def test_missing_and_orphan_settlement(self):
        data = {"postings": GOOD["postings"], "settlements": [
            GOOD["settlements"][0], {"id": "other", "merchant": "m-1", "amount_won": 9}]}
        self.assertEqual([i["issue"] for i in reconcile(data)["issues"]],
                         ["MISSING_SETTLEMENT", "UNMATCHED_SETTLEMENT"])

    def test_amount_and_merchant_mismatch(self):
        for changed in ({"id": "c-1", "merchant": "m-1", "amount_won": 1199},
                        {"id": "c-1", "merchant": "m-2", "amount_won": 1200}):
            data = {"postings": GOOD["postings"], "settlements": [changed, GOOD["settlements"][0]]}
            self.assertEqual(reconcile(data)["issues"][0]["issue"], "MERCHANT_OR_AMOUNT_MISMATCH")

    def test_duplicate_and_float_rejected(self):
        with self.assertRaisesRegex(EvidenceError, "duplicate"):
            reconcile({"postings": GOOD["postings"] * 2, "settlements": []})
        bad = {"postings": [{"id": "x", "merchant": "m", "amount_won": 1.0}], "settlements": []}
        with self.assertRaisesRegex(EvidenceError, "integer"):
            reconcile(bad)

    def test_hash_order_independent_and_tamper_sensitive(self):
        first = reconcile(GOOD)["evidence_sha256"]
        reordered = {"postings": list(reversed(GOOD["postings"])),
                     "settlements": list(reversed(GOOD["settlements"]))}
        self.assertEqual(first, reconcile(reordered)["evidence_sha256"])
        reordered["postings"][0] = {**reordered["postings"][0], "amount_won": -301}
        self.assertNotEqual(first, reconcile(reordered)["evidence_sha256"])

    def test_valid_reversal_link(self):
        data = {"postings": [{"id": "sale", "merchant": "m", "amount_won": 100},
                             {"id": "refund", "merchant": "m", "amount_won": -100,
                              "reversal_of": "sale"}],
                "settlements": [{"id": "sale", "merchant": "m", "amount_won": 100},
                                {"id": "refund", "merchant": "m", "amount_won": -100}]}
        self.assertEqual(reconcile(data)["decision"], "MATCH")

    def test_wrong_and_duplicate_reversal_links(self):
        data = {"postings": [{"id": "sale", "merchant": "m", "amount_won": 100},
                             {"id": "refund1", "merchant": "m", "amount_won": -90,
                              "reversal_of": "sale"},
                             {"id": "refund2", "merchant": "m", "amount_won": -100,
                              "reversal_of": "sale"}],
                "settlements": [{"id": "sale", "merchant": "m", "amount_won": 100},
                                {"id": "refund1", "merchant": "m", "amount_won": -90},
                                {"id": "refund2", "merchant": "m", "amount_won": -100}]}
        self.assertEqual({x["issue"] for x in reconcile(data)["issues"]},
                         {"INVALID_REVERSAL_LINK", "MULTIPLE_REVERSALS"})

    def test_reversal_reference_validation(self):
        with self.assertRaisesRegex(EvidenceError, "reversal_of"):
            reconcile({"postings": [{"id": "x", "merchant": "m", "amount_won": -1,
                                     "reversal_of": 3}], "settlements": []})

    def test_cli_exit_status(self):
        cli = Path(__file__).resolve().parents[1] / "reconcile.py"
        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "sample.json"
            sample.write_text(json.dumps(GOOD), encoding="utf-8")
            ok = subprocess.run([sys.executable, str(cli), str(sample)], capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertEqual(json.loads(ok.stdout)["decision"], "MATCH")
            sample.write_text(json.dumps({"postings": GOOD["postings"], "settlements": []}), encoding="utf-8")
            gap = subprocess.run([sys.executable, str(cli), str(sample)], capture_output=True, text=True)
            self.assertEqual(gap.returncode, 1)


if __name__ == "__main__":
    unittest.main()
