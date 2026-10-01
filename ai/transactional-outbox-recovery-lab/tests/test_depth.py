"""경계값·불변조건·큰 합성 입력으로 기존 공개 API를 검증한다."""

import json
import unittest

from ledger import LedgerError, connect, deliver, seed, transfer


class DepthTests(unittest.TestCase):
    def test_invalid_delivery_is_atomic(self):
        for body in (
            {"source": "A", "target": "A", "amount_won": 1},
            {"source": "A", "target": "B", "amount_won": True},
            {"source": "A", "target": "B", "amount_won": 2**63},
        ):
            with connect() as producer, connect() as consumer:
                seed(producer, {"A": 10, "B": 0})
                transfer(producer, "t", "A", "B", 1)
                producer.execute("UPDATE outbox SET payload=?", (json.dumps(body),))
                with self.assertRaises(LedgerError):
                    deliver(producer, consumer)
                self.assertEqual(
                    consumer.execute("SELECT COUNT(*) FROM inbox").fetchone()[0], 0
                )
                self.assertEqual(
                    producer.execute("SELECT delivered FROM outbox").fetchone()[0], 0
                )

    def test_projection_overflow_rolls_back_all_sides(self):
        with connect() as producer, connect() as consumer:
            seed(producer, {"A": 10, "B": 0})
            transfer(producer, "t", "A", "B", 1)
            consumer.execute("INSERT INTO projections VALUES ('B', ?)", (2**63 - 1,))
            with self.assertRaises(LedgerError):
                deliver(producer, consumer)
            self.assertEqual(
                dict(consumer.execute("SELECT * FROM projections")), {"B": 2**63 - 1}
            )
            self.assertEqual(
                consumer.execute("SELECT COUNT(*) FROM inbox").fetchone()[0], 0
            )

    def test_seed_boundary(self):
        with connect() as db:
            with self.assertRaises(LedgerError):
                seed(db, {"A": 2**63})


if __name__ == "__main__":
    unittest.main()
