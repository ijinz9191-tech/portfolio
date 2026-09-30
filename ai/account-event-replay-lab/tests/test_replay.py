import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from replay import ReplayError, replay


BASE = {"account": "가상", "opening_won": 100, "expected_won": 120,
        "events": [{"id": "a", "version": 1, "delta_won": 40},
                   {"id": "b", "version": 2, "delta_won": -20}]}


class ReplayTests(unittest.TestCase):
    def test_reordered_delivery_and_idempotent_retry(self):
        one = replay(BASE)
        duplicate = {**BASE, "events": [BASE["events"][1], BASE["events"][0], BASE["events"][0]]}
        two = replay(duplicate)
        self.assertEqual((one["decision"], one["balance_won"]), ("CONSISTENT", 120))
        self.assertEqual(two["idempotent_duplicates"], 1)
        self.assertEqual(one["evidence_sha256"], two["evidence_sha256"])

    def test_conflicting_retry_and_version_reuse_rejected(self):
        for extra in ({"id": "a", "version": 1, "delta_won": 41},
                      {"id": "c", "version": 1, "delta_won": 40}):
            with self.assertRaises(ReplayError):
                replay({**BASE, "events": BASE["events"] + [extra]})

    def test_gap_does_not_publish_partial_balance(self):
        payload = {**BASE, "events": [{"id": "a", "version": 1, "delta_won": 40},
                                       {"id": "b", "version": 3, "delta_won": -20}]}
        result = replay(payload)
        self.assertEqual(result["issues"][0]["kind"], "VERSION_GAP")
        self.assertIsNone(result["balance_won"])

    def test_negative_intermediate_balance_requires_review(self):
        payload = {**BASE, "events": [{"id": "a", "version": 1, "delta_won": -110},
                                       {"id": "b", "version": 2, "delta_won": 130}]}
        result = replay(payload)
        self.assertEqual(result["issues"][0]["kind"], "NEGATIVE_BALANCE")
        self.assertIsNone(result["balance_won"])

    def test_expected_balance_mismatch_and_digest_change(self):
        payload = {**BASE, "expected_won": 119}
        self.assertEqual(replay(payload)["issues"][0]["kind"], "EXPECTED_MISMATCH")
        self.assertNotEqual(replay(payload)["evidence_sha256"], replay(BASE)["evidence_sha256"])

    def test_intermediate_checkpoint_and_backward_compatibility(self):
        old = replay(BASE)
        checked = replay({**BASE, "checkpoints": [{"version": 1, "balance_won": 140}]})
        self.assertEqual((old["decision"], old["balance_won"]), ("CONSISTENT", 120))
        self.assertEqual((checked["decision"], checked["balance_won"]), ("CONSISTENT", 120))
        self.assertNotEqual(old["evidence_sha256"], checked["evidence_sha256"])

    def test_checkpoint_mismatch_hides_final_balance(self):
        result = replay({**BASE, "checkpoints": [{"version": 1, "balance_won": 141}]})
        self.assertEqual(result["issues"][0]["kind"], "CHECKPOINT_MISMATCH")
        self.assertIsNone(result["balance_won"])

    def test_invalid_checkpoint_rejected(self):
        for rows in ([{"version": 3, "balance_won": 120}],
                     [{"version": 1, "balance_won": 140}, {"version": 1, "balance_won": 140}],
                     [{"version": True, "balance_won": 140}]):
            with self.assertRaises(ReplayError):
                replay({**BASE, "checkpoints": rows})

    def test_bool_float_and_empty_event_rejected(self):
        for payload in ({**BASE, "opening_won": True}, {**BASE, "expected_won": 120.0},
                        {**BASE, "events": []}):
            with self.assertRaises(ReplayError):
                replay(payload)

    def test_cli_success_review_and_invalid(self):
        cli = Path(__file__).resolve().parents[1] / "replay.py"
        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "input.json"
            for payload, code in ((BASE, 0), ({**BASE, "expected_won": 5}, 1),
                                  ({**BASE, "opening_won": False}, 2)):
                sample.write_text(json.dumps(payload), encoding="utf-8")
                done = subprocess.run([sys.executable, str(cli), str(sample)],
                                      capture_output=True, text=True)
                self.assertEqual(done.returncode, code, done.stderr)


if __name__ == "__main__":
    unittest.main()
