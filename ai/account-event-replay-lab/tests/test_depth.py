"""경계값·불변조건·큰 합성 입력으로 기존 공개 API를 검증한다."""

import unittest

from replay import ReplayError, replay


class DepthTests(unittest.TestCase):
    def test_overflow_fail_closed(self):
        doc = {
            "account": "A",
            "opening_won": 2**63 - 1,
            "expected_won": 2**63 - 1,
            "events": [{"id": "1", "version": 1, "delta_won": 1}],
        }
        result = replay(doc)
        self.assertEqual(result["balance_won"], None)
        self.assertEqual(result["issues"][0]["kind"], "BALANCE_OVERFLOW")

    def test_bounded_integer(self):
        with self.assertRaises(ReplayError):
            replay(
                {"account": "A", "opening_won": 2**63, "expected_won": 0, "events": []}
            )

    def test_large_reference_replay_and_retry(self):
        events = [
            {"id": str(i), "version": i, "delta_won": 1 if i % 2 else -1}
            for i in range(1, 20001)
        ]
        result = replay(
            {
                "account": "A",
                "opening_won": 10,
                "expected_won": 10,
                "events": events[::-1] + events[:100],
            }
        )
        self.assertEqual(result["balance_won"], 10)
        self.assertEqual(result["idempotent_duplicates"], 100)
        self.assertEqual(len(result["trace"]), len(events))
        balance = 10
        for row, event in zip(result["trace"], events):
            balance += event["delta_won"]
            self.assertEqual(row["balance_won"], balance)


if __name__ == "__main__":
    unittest.main()
