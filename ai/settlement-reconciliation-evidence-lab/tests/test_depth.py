"""경계값·불변조건·큰 합성 입력으로 기존 공개 API를 검증한다."""

import unittest

from reconcile import EvidenceError, reconcile


class DepthTests(unittest.TestCase):
    def test_absolute_exposure_prevents_net_zero_hiding(self):
        doc = {
            "postings": [
                {"id": "a", "merchant": "m", "amount_won": 100},
                {"id": "b", "merchant": "m", "amount_won": -100},
            ],
            "settlements": [],
        }
        result = reconcile(doc)
        self.assertEqual(result["merchant_totals"][0]["posting_won"], 0)
        self.assertEqual(result["unmatched_absolute_won"], 200)

    def test_large_matching_reference(self):
        rows = [
            {
                "id": str(i),
                "merchant": "m",
                "amount_won": (i + 1) * (-1 if i % 2 else 1),
            }
            for i in range(10000)
        ]
        result = reconcile({"postings": rows, "settlements": rows[::-1]})
        self.assertEqual(
            result["matched_absolute_won"], sum(abs(row["amount_won"]) for row in rows)
        )
        self.assertEqual(result["unmatched_absolute_won"], 0)

    def test_integer_overflow(self):
        with self.assertRaises(EvidenceError):
            reconcile(
                {
                    "postings": [{"id": "a", "merchant": "m", "amount_won": 2**63}],
                    "settlements": [],
                }
            )


if __name__ == "__main__":
    unittest.main()
