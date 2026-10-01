"""부분 쓰기·ACK 손실·재접속에 대한 DB 상태를 검증한다."""

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ledger import LedgerError, InjectedFailure, connect, seed, transfer, deliver, demo


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.db = connect()
        self.consumer = connect()
        self.addCleanup(self.db.close)
        self.addCleanup(self.consumer.close)
        seed(self.db, {"A": 100, "B": 10})

    def test_commit_and_exact_retry(self):
        self.assertEqual(transfer(self.db, "T1", "A", "B", 30), "COMMITTED")
        self.assertEqual(transfer(self.db, "T1", "A", "B", 30), "ALREADY_COMMITTED")
        self.assertEqual(dict(self.db.execute("SELECT * FROM accounts")), {"A": 70, "B": 40})
        self.assertEqual(self.db.execute("SELECT COUNT(*), SUM(delta_won) FROM postings").fetchone(), (2, 0))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0], 1)

    def test_each_partial_write_is_rolled_back(self):
        for stage in ("after_debit", "before_outbox", "before_commit"):
            with self.subTest(stage=stage), self.assertRaises(InjectedFailure):
                transfer(self.db, "T1", "A", "B", 30, fail_at=stage)
            self.assertEqual(dict(self.db.execute("SELECT * FROM accounts")), {"A": 100, "B": 10})
            for table in ("transfers", "postings", "outbox"):
                self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
        self.assertEqual(transfer(self.db, "T1", "A", "B", 30), "COMMITTED")

    def test_changed_payload_same_key_rejected(self):
        transfer(self.db, "T1", "A", "B", 30)
        with self.assertRaises(LedgerError):
            transfer(self.db, "T1", "A", "B", 31)
        self.assertEqual(self.db.execute("SELECT balance_won FROM accounts WHERE id='A'").fetchone()[0], 70)

    def test_overdraft_and_unknown_account_are_atomic(self):
        for target, amount in (("B", 101), ("C", 1)):
            with self.assertRaises(LedgerError):
                transfer(self.db, "T1", "A", target, amount)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM transfers").fetchone()[0], 0)

    def test_boolean_self_transfer_and_bad_injection_rejected(self):
        for source, target, amount, stage in (("A", "B", True, None), ("A", "A", 1, None), ("A", "B", 1, "bad")):
            with self.assertRaises(LedgerError):
                transfer(self.db, "T1", source, target, amount, fail_at=stage)

    def test_ack_loss_does_not_apply_consumer_twice(self):
        transfer(self.db, "T1", "A", "B", 30)
        self.assertEqual(deliver(self.db, self.consumer, lose_ack=True), 1)
        self.assertEqual(self.db.execute("SELECT delivered FROM outbox").fetchone()[0], 0)
        self.assertEqual(deliver(self.db, self.consumer), 0)
        self.assertEqual(dict(self.consumer.execute("SELECT * FROM projections")), {"A": -30, "B": 30})
        self.assertEqual(self.db.execute("SELECT delivered FROM outbox").fetchone()[0], 1)

    def test_consumer_conflicting_event_keeps_ack_pending(self):
        transfer(self.db, "T1", "A", "B", 30)
        self.consumer.execute("INSERT INTO inbox VALUES ('T1', 'different')")
        with self.assertRaises(LedgerError):
            deliver(self.db, self.consumer)
        self.assertEqual(self.db.execute("SELECT delivered FROM outbox").fetchone()[0], 0)
        self.assertEqual(self.consumer.execute("SELECT COUNT(*) FROM projections").fetchone()[0], 0)

    def test_reopen_preserves_committed_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.sqlite"
            db = connect(path)
            seed(db, {"A": 100, "B": 0})
            transfer(db, "T1", "A", "B", 30)
            db.close()
            db = connect(path)
            try:
                self.assertEqual(transfer(db, "T1", "A", "B", 30), "ALREADY_COMMITTED")
                self.assertEqual(dict(db.execute("SELECT * FROM accounts")), {"A": 70, "B": 30})
            finally:
                db.close()

    def test_credit_overflow_is_rejected(self):
        self.db.execute("UPDATE accounts SET balance_won=? WHERE id='B'", (2**63 - 1,))
        with self.assertRaises(LedgerError):
            transfer(self.db, "T1", "A", "B", 1)

    def test_demo_reports_rollback_and_recovery(self):
        result = demo()
        self.assertEqual(result["rollback_balances_won"], {"A": 10000, "B": 0})
        self.assertEqual(result["committed_balances_won"], {"A": 7000, "B": 3000})
        self.assertEqual((result["consumer_first_applied"], result["consumer_retry_applied"]), (1, 0))


if __name__ == "__main__":
    unittest.main()
