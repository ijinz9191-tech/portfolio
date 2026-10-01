"""경계값·불변조건·큰 합성 입력으로 기존 공개 API를 검증한다."""

import unittest

from audit import EvidenceError, audit


class DepthTests(unittest.TestCase):
    def doc(self):
        return {
            "attempts": [
                {
                    "request_id": "r",
                    "key": "k",
                    "merchant": "m",
                    "amount_won": 10,
                    "attempt_no": 1,
                    "response": "ACK",
                }
            ],
            "provider_events": [
                {"event_id": "e", "key": "k", "status": "DECLINED", "amount_won": 10}
            ],
        }

    def test_ack_decline_conflict(self):
        result = audit(self.doc())
        self.assertEqual(result["results"][0]["entitlement_gate"], "REVIEW")
        self.assertIn(
            "RESPONSE_PROVIDER_CONFLICT", [i["issue"] for i in result["issues"]]
        )

    def test_timeout_decline_remains_consistent(self):
        doc = self.doc()
        doc["attempts"][0]["response"] = "TIMEOUT"
        self.assertEqual(audit(doc)["decision"], "PASS")

    def test_integer_boundary(self):
        doc = self.doc()
        doc["attempts"][0]["amount_won"] = 2**63
        with self.assertRaises(EvidenceError):
            audit(doc)


if __name__ == "__main__":
    unittest.main()
