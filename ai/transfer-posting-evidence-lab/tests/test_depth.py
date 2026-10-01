"""경계값·불변조건·큰 합성 입력으로 기존 공개 API를 검증한다."""

import unittest

from audit import AuditError, audit


class DepthTests(unittest.TestCase):
    def test_credit_overflow_blocks_replay(self):
        doc = {
            "accounts": [
                {"id": "A", "opening_won": 10, "expected_won": 9},
                {"id": "B", "opening_won": 2**63 - 1, "expected_won": 2**63 - 1},
            ],
            "transfers": [
                {"id": "t", "sequence": 1, "from": "A", "to": "B", "amount_won": 1}
            ],
            "postings": [
                {"transfer_id": "t", "account": "A", "delta_won": -1},
                {"transfer_id": "t", "account": "B", "delta_won": 1},
            ],
        }
        result = audit(doc)
        self.assertIsNone(result["balances_won"])
        self.assertEqual(result["trace"], [])
        self.assertEqual(result["issues"][0]["kind"], "BALANCE_OVERFLOW")

    def test_reject_unbounded_account(self):
        with self.assertRaises(AuditError):
            audit(
                {
                    "accounts": [
                        {"id": "A", "opening_won": 2**63, "expected_won": 0},
                        {"id": "B", "opening_won": 0, "expected_won": 0},
                    ],
                    "transfers": [],
                    "postings": [],
                }
            )


if __name__ == "__main__":
    unittest.main()
