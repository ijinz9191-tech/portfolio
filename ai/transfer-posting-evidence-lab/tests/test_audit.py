import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit import AuditError, audit


BASE = {"accounts": [{"id": "A", "opening_won": 100, "expected_won": 70},
                     {"id": "B", "opening_won": 10, "expected_won": 40}],
        "transfers": [{"id": "T1", "sequence": 1, "from": "A", "to": "B", "amount_won": 30}],
        "postings": [{"transfer_id": "T1", "account": "A", "delta_won": -30},
                     {"transfer_id": "T1", "account": "B", "delta_won": 30}]}


class AuditTests(unittest.TestCase):
    def test_balanced_transfer_and_retry(self):
        one = audit(BASE)
        copy_input = copy.deepcopy(BASE)
        copy_input["transfers"].append(copy_input["transfers"][0])
        copy_input["postings"] = [copy_input["postings"][1], copy_input["postings"][0],
                                  copy_input["postings"][0]]
        two = audit(copy_input)
        self.assertEqual(one["balances_won"], {"A": 70, "B": 40})
        self.assertEqual((two["transfer_retries"], two["posting_retries"]), (1, 1))
        self.assertEqual(one["evidence_sha256"], two["evidence_sha256"])

    def test_missing_credit_does_not_publish_balances(self):
        data = {**BASE, "postings": BASE["postings"][:1]}
        result = audit(data)
        self.assertEqual(result["issues"][0]["kind"], "POSTING_INCOMPLETE")
        self.assertIsNone(result["balances_won"])

    def test_wrong_leg_detected_even_when_sum_looks_plausible(self):
        data = {**BASE, "postings": [BASE["postings"][0],
                                     {"transfer_id": "T1", "account": "B", "delta_won": 29}]}
        result = audit(data)
        self.assertEqual(result["issues"][0]["kind"], "POSTING_INCOMPLETE")
        self.assertTrue(result["issues"][0]["unexpected"])

    def test_overdraft_and_expected_balance_mismatch(self):
        poor = copy.deepcopy(BASE)
        poor["accounts"][0]["opening_won"] = 20
        self.assertEqual(audit(poor)["issues"][0]["kind"], "OVERDRAFT")
        wrong = copy.deepcopy(BASE)
        wrong["accounts"][1]["expected_won"] = 41
        self.assertEqual(audit(wrong)["issues"][0]["kind"], "EXPECTED_MISMATCH")

    def test_conflicting_retry_and_sequence_reuse_rejected(self):
        conflict = copy.deepcopy(BASE)
        conflict["transfers"].append({**conflict["transfers"][0], "amount_won": 31})
        with self.assertRaises(AuditError):
            audit(conflict)
        reused = copy.deepcopy(BASE)
        reused["transfers"].append({**reused["transfers"][0], "id": "T2"})
        with self.assertRaises(AuditError):
            audit(reused)

    def test_orphan_posting_and_invalid_type_rejected(self):
        orphan = copy.deepcopy(BASE)
        orphan["postings"].append({"transfer_id": "T2", "account": "A", "delta_won": -1})
        with self.assertRaises(AuditError):
            audit(orphan)
        boolean = copy.deepcopy(BASE)
        boolean["transfers"][0]["amount_won"] = True
        with self.assertRaises(AuditError):
            audit(boolean)

    def test_two_transfers_follow_sequence_not_arrival_order(self):
        data = {"accounts": [{"id": "A", "opening_won": 100, "expected_won": 90},
                             {"id": "B", "opening_won": 10, "expected_won": 20}],
                "transfers": [{"id": "T2", "sequence": 2, "from": "B", "to": "A", "amount_won": 20},
                              {"id": "T1", "sequence": 1, "from": "A", "to": "B", "amount_won": 30}],
                "postings": [{"transfer_id": "T2", "account": "A", "delta_won": 20},
                             {"transfer_id": "T1", "account": "B", "delta_won": 30},
                             {"transfer_id": "T2", "account": "B", "delta_won": -20},
                             {"transfer_id": "T1", "account": "A", "delta_won": -30}]}
        result = audit(data)
        self.assertEqual(result["decision"], "CONSISTENT")
        self.assertEqual([row["transfer_id"] for row in result["trace"]], ["T1", "T2"])

    def test_cli_exit_codes(self):
        cli = Path(__file__).resolve().parents[1] / "audit.py"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            cases = [(BASE, 0), ({**BASE, "postings": BASE["postings"][:1]}, 1),
                     ({**BASE, "postings": "bad"}, 2)]
            for payload, code in cases:
                path.write_text(json.dumps(payload), encoding="utf-8")
                done = subprocess.run([sys.executable, str(cli), str(path)],
                                      capture_output=True, text=True)
                self.assertEqual(done.returncode, code, done.stderr)

    def test_failed_earlier_transfer_blocks_later_replay(self):
        data = copy.deepcopy(BASE)
        data["transfers"].append({"id": "T2", "sequence": 2, "from": "B", "to": "A", "amount_won": 5})
        data["postings"] = [BASE["postings"][0],
                            {"transfer_id": "T2", "account": "B", "delta_won": -5},
                            {"transfer_id": "T2", "account": "A", "delta_won": 5}]
        result = audit(data)
        self.assertEqual(result["trace"], [])
        self.assertEqual(result["issues"][1], {"kind": "REPLAY_BLOCKED", "transfer_id": "T2", "blocked_by": "T1"})
        self.assertIsNone(result["balances_won"])

    def test_verified_prefix_is_retained_without_hypothetical_suffix(self):
        data = copy.deepcopy(BASE)
        data["transfers"] += [{"id": "T2", "sequence": 2, "from": "B", "to": "A", "amount_won": 50},
                              {"id": "T3", "sequence": 3, "from": "A", "to": "B", "amount_won": 1}]
        data["postings"] += [{"transfer_id": "T2", "account": "B", "delta_won": -50},
                             {"transfer_id": "T2", "account": "A", "delta_won": 50},
                             {"transfer_id": "T3", "account": "A", "delta_won": -1},
                             {"transfer_id": "T3", "account": "B", "delta_won": 1}]
        result = audit(data)
        self.assertEqual([row["transfer_id"] for row in result["trace"]], ["T1"])
        self.assertEqual([row["kind"] for row in result["issues"]], ["OVERDRAFT", "REPLAY_BLOCKED"])


if __name__ == "__main__":
    unittest.main()
