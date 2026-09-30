import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit import InputError, audit


def valid():
    return {
        "sessions": [{"session_id": "s", "order_id": "o", "merchant": "m", "amount_won": 100,
                      "nonce_sha256": hashlib.sha256(b"n").hexdigest()}],
        "returns": [{"return_id": "r", "session_id": "s", "order_id": "o", "nonce": "n", "result": "SUCCESS"}],
        "confirmations": [{"transaction_id": "t", "session_id": "s", "order_id": "o", "merchant": "m",
                           "amount_won": 100, "status": "AUTHORIZED"}],
    }


class AuditTests(unittest.TestCase):
    def test_confirmed_candidate(self):
        result = audit(valid())
        self.assertEqual(result["decision"], "PASS")
        self.assertEqual(result["results"][0]["decision"], "AUTHORIZATION_CANDIDATE")

    def test_browser_success_without_server_confirmation(self):
        data = valid()
        data["confirmations"] = []
        self.assertEqual(audit(data)["results"][0]["decision"], "REVIEW")

    def test_server_rejection_disagrees_with_browser(self):
        data = valid()
        data["confirmations"][0]["status"] = "REJECTED"
        self.assertIn("RETURN_SERVER_DISAGREEMENT", {x["issue"] for x in audit(data)["findings"]})

    def test_clean_rejection(self):
        data = valid()
        data["returns"][0]["result"] = "FAILURE"
        data["confirmations"][0]["status"] = "REJECTED"
        self.assertEqual(audit(data)["results"][0]["decision"], "REJECTED")

    def test_nonce_and_amount_mismatch(self):
        data = valid()
        data["returns"][0]["nonce"] = "wrong"
        data["confirmations"][0]["amount_won"] = 101
        self.assertEqual({x["issue"] for x in audit(data)["findings"]},
                         {"RETURN_NONCE_MISMATCH", "SERVER_DETAILS_MISMATCH"})

    def test_return_replay_and_unknown_session(self):
        data = valid()
        data["returns"].append(dict(data["returns"][0], return_id="r2"))
        data["confirmations"].append(dict(data["confirmations"][0], transaction_id="t2", session_id="other"))
        self.assertEqual({x["issue"] for x in audit(data)["findings"]},
                         {"RETURN_COUNT_MISMATCH", "UNKNOWN_SESSION"})

    def test_duplicate_and_bool_amount_rejected(self):
        data = valid()
        data["returns"].append(deepcopy(data["returns"][0]))
        with self.assertRaisesRegex(InputError, "return_id"):
            audit(data)
        data = valid()
        data["sessions"][0]["amount_won"] = True
        with self.assertRaisesRegex(InputError, "정수"):
            audit(data)

    def test_cli_and_sample(self):
        script = Path(__file__).resolve().parents[1] / "audit.py"
        sample = Path(__file__).resolve().parents[1] / "samples" / "authorized.json"
        result = subprocess.run([sys.executable, str(script), str(sample)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["results"][0]["decision"], "AUTHORIZATION_CANDIDATE")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.json"
            data = valid()
            data["confirmations"] = []
            path.write_text(json.dumps(data), encoding="utf-8")
            result = subprocess.run([sys.executable, str(script), str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
