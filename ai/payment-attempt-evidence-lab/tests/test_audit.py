import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit import EvidenceError, audit


GOOD = {"attempts": [
    {"request_id": "r1", "key": "k1", "merchant": "m", "amount_won": 100,
     "attempt_no": 1, "response": "TIMEOUT"},
    {"request_id": "r1", "key": "k1", "merchant": "m", "amount_won": 100,
     "attempt_no": 2, "response": "ACK"}],
    "provider_events": [{"event_id": "e1", "key": "k1", "status": "CAPTURED", "amount_won": 100}]}


class AuditTests(unittest.TestCase):
    def test_timeout_then_confirmed_retry(self):
        result = audit(GOOD)
        self.assertEqual(result["decision"], "PASS")
        self.assertEqual(result["results"][0]["attempts"], 2)
        self.assertEqual(result["results"][0]["status"], "CAPTURED")
        self.assertEqual(result["results"][0]["entitlement_gate"], "ELIGIBLE")

    def test_ack_without_provider_evidence_remains_unknown(self):
        data = deepcopy(GOOD)
        data["provider_events"] = []
        result = audit(data)
        self.assertEqual(result["results"][0]["status"], "UNKNOWN")
        self.assertEqual(result["results"][0]["entitlement_gate"], "REVIEW")
        self.assertIn("PROVIDER_OUTCOME_UNKNOWN", [x["issue"] for x in result["issues"]])

    def test_key_payload_conflict(self):
        data = deepcopy(GOOD)
        data["attempts"][1]["amount_won"] = 101
        self.assertIn("IDEMPOTENCY_KEY_CONFLICT", [x["issue"] for x in audit(data)["issues"]])

    def test_provider_amount_and_outcome_conflict(self):
        data = deepcopy(GOOD)
        data["provider_events"].append({"event_id": "e2", "key": "k1", "status": "DECLINED", "amount_won": 99})
        self.assertEqual({x["issue"] for x in audit(data)["issues"]},
                         {"PROVIDER_AMOUNT_MISMATCH", "CONFLICTING_PROVIDER_OUTCOME"})
        self.assertEqual(audit(data)["results"][0]["entitlement_gate"], "REVIEW")

    def test_clean_decline_does_not_grant_access(self):
        data = deepcopy(GOOD)
        data["attempts"] = [dict(data["attempts"][0], response="DECLINED")]
        data["provider_events"] = [dict(data["provider_events"][0], status="DECLINED")]
        result = audit(data)
        self.assertEqual(result["decision"], "PASS")
        self.assertEqual(result["results"][0]["entitlement_gate"], "NOT_ELIGIBLE")

    def test_capture_with_amount_mismatch_needs_review_before_access(self):
        data = deepcopy(GOOD)
        data["provider_events"][0]["amount_won"] = 101
        result = audit(data)
        self.assertEqual(result["results"][0]["status"], "CAPTURED")
        self.assertEqual(result["results"][0]["entitlement_gate"], "REVIEW")

    def test_confirmed_reversal_removes_access_candidate(self):
        data = deepcopy(GOOD)
        data["provider_events"].append({"event_id": "e2", "key": "k1", "status": "REVERSED", "amount_won": 100})
        result = audit(data)
        self.assertEqual(result["decision"], "PASS")
        self.assertEqual(result["results"][0]["status"], "REVERSED")
        self.assertEqual(result["results"][0]["entitlement_gate"], "NOT_ELIGIBLE")

    def test_orphan_reversal_requires_review(self):
        data = deepcopy(GOOD)
        data["provider_events"][0]["status"] = "REVERSED"
        result = audit(data)
        self.assertEqual(result["results"][0]["entitlement_gate"], "REVIEW")
        self.assertIn("REVERSAL_EVIDENCE_CONFLICT", {x["issue"] for x in result["issues"]})

    def test_orphan_provider_event_and_sequence_gap(self):
        data = deepcopy(GOOD)
        data["attempts"][1]["attempt_no"] = 3
        data["provider_events"].append({"event_id": "e2", "key": "unknown", "status": "CAPTURED", "amount_won": 100})
        self.assertEqual({x["issue"] for x in audit(data)["issues"]},
                         {"ATTEMPT_SEQUENCE_GAP", "ORPHAN_PROVIDER_EVENT"})

    def test_duplicate_and_boolean_amount_rejected(self):
        data = deepcopy(GOOD)
        data["provider_events"].append(deepcopy(data["provider_events"][0]))
        with self.assertRaisesRegex(EvidenceError, "event_id"):
            audit(data)
        data = deepcopy(GOOD)
        data["attempts"][0]["amount_won"] = True
        with self.assertRaisesRegex(EvidenceError, "정수"):
            audit(data)

    def test_unhashable_response_and_multiple_capture(self):
        data = deepcopy(GOOD)
        data["attempts"][0]["response"] = []
        with self.assertRaisesRegex(EvidenceError, "response"):
            audit(data)
        data = deepcopy(GOOD)
        data["provider_events"].append({"event_id": "e2", "key": "k1", "status": "CAPTURED", "amount_won": 100})
        self.assertIn("CONFLICTING_PROVIDER_OUTCOME", [x["issue"] for x in audit(data)["issues"]])

    def test_hash_stable_under_input_order_and_sensitive_to_change(self):
        first = audit(GOOD)["evidence_sha256"]
        data = deepcopy(GOOD)
        data["attempts"].reverse()
        self.assertEqual(first, audit(data)["evidence_sha256"])
        data["attempts"][0]["response"] = "DECLINED"
        self.assertNotEqual(first, audit(data)["evidence_sha256"])

    def test_cli_success_and_review_exit(self):
        cli = Path(__file__).resolve().parents[1] / "audit.py"
        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "input.json"
            sample.write_text(json.dumps(GOOD), encoding="utf-8")
            ok = subprocess.run([sys.executable, str(cli), str(sample)], capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertEqual(json.loads(ok.stdout)["decision"], "PASS")
            data = deepcopy(GOOD)
            data["provider_events"] = []
            sample.write_text(json.dumps(data), encoding="utf-8")
            review = subprocess.run([sys.executable, str(cli), str(sample)], capture_output=True, text=True)
            self.assertEqual(review.returncode, 1)


if __name__ == "__main__":
    unittest.main()
