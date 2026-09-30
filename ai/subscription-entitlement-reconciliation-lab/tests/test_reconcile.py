import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reconcile import InputError, reconcile


GOOD = {
    "payments": [{"payment_id": "pay-1", "subscription_id": "sub-1", "period": "2026-09",
                  "status": "CAPTURED", "amount_won": 9900}],
    "entitlements": [{"payment_id": "pay-1", "subscription_id": "sub-1", "period": "2026-09",
                      "status": "ACTIVE"}],
    "partner_acks": [{"payment_id": "pay-1", "subscription_id": "sub-1", "period": "2026-09",
                      "status": "CONFIRMED"}],
}


class ReconciliationTests(unittest.TestCase):
    def test_confirmed_cycle_is_eligible(self):
        result = reconcile(GOOD)
        self.assertEqual(result["decision"], "PASS")
        self.assertEqual(result["results"][0]["access_gate"], "ELIGIBLE")

    def test_declined_cycle_never_grants_access(self):
        data = deepcopy(GOOD)
        data["payments"][0]["status"] = "DECLINED"
        data["entitlements"] = []
        data["partner_acks"] = []
        result = reconcile(data)
        self.assertEqual(result["decision"], "PASS")
        self.assertEqual(result["results"][0]["access_gate"], "NOT_ELIGIBLE")

    def test_missing_partner_ack_requires_review(self):
        data = deepcopy(GOOD)
        data["partner_acks"] = []
        result = reconcile(data)
        self.assertEqual(result["results"][0]["access_gate"], "REVIEW")
        self.assertIn("PARTNER_ACK_MISSING", [x["issue"] for x in result["issues"]])

    def test_declined_payment_cannot_back_active_access(self):
        data = deepcopy(GOOD)
        data["payments"][0]["status"] = "DECLINED"
        self.assertEqual({x["issue"] for x in reconcile(data)["issues"]},
                         {"ACCESS_WITHOUT_PAYMENT", "PARTNER_CONFIRMED_DECLINE"})

    def test_wrong_payment_reference_and_period(self):
        data = deepcopy(GOOD)
        data["entitlements"][0]["payment_id"] = "other"
        self.assertIn("PAYMENT_REFERENCE_MISMATCH", [x["issue"] for x in reconcile(data)["issues"]])
        data = deepcopy(GOOD)
        data["entitlements"][0]["period"] = "2026-10"
        self.assertEqual(reconcile(data)["decision"], "REVIEW_REQUIRED")

    def test_duplicate_access_and_payment_id_rejected(self):
        data = deepcopy(GOOD)
        data["entitlements"].append(deepcopy(data["entitlements"][0]))
        self.assertIn("MULTIPLE_ENTITLEMENTS", [x["issue"] for x in reconcile(data)["issues"]])
        data = deepcopy(GOOD)
        data["payments"].append(deepcopy(data["payments"][0]))
        with self.assertRaisesRegex(InputError, "payment_id"):
            reconcile(data)

    def test_input_contract_rejects_invalid_month_and_boolean_amount(self):
        data = deepcopy(GOOD)
        data["payments"][0]["period"] = "2026-13"
        with self.assertRaisesRegex(InputError, "YYYY-MM"):
            reconcile(data)
        data = deepcopy(GOOD)
        data["payments"][0]["amount_won"] = True
        with self.assertRaisesRegex(InputError, "정수"):
            reconcile(data)

    def test_hash_ignores_row_order_but_changes_with_evidence(self):
        data = deepcopy(GOOD)
        data["payments"].append({"payment_id": "pay-2", "subscription_id": "sub-2",
                                 "period": "2026-09", "status": "DECLINED", "amount_won": 100})
        first = reconcile(data)["evidence_sha256"]
        data["payments"].reverse()
        self.assertEqual(first, reconcile(data)["evidence_sha256"])
        data["payments"][0]["amount_won"] = 101
        self.assertNotEqual(first, reconcile(data)["evidence_sha256"])

    def test_cli_exit_codes(self):
        cli = Path(__file__).resolve().parents[1] / "reconcile.py"
        with tempfile.TemporaryDirectory() as directory:
            sample = Path(directory) / "input.json"
            sample.write_text(json.dumps(GOOD), encoding="utf-8")
            self.assertEqual(subprocess.run([sys.executable, str(cli), str(sample)],
                                            capture_output=True).returncode, 0)
            data = deepcopy(GOOD)
            data["partner_acks"] = []
            sample.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(subprocess.run([sys.executable, str(cli), str(sample)],
                                            capture_output=True).returncode, 1)
            sample.write_text("{}", encoding="utf-8")
            self.assertEqual(subprocess.run([sys.executable, str(cli), str(sample)],
                                            capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
