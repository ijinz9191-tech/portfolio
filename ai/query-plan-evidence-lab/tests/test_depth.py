import sqlite3
import unittest

from planlab import EvidenceError
from planlab.model import cursor_rows, reproduce


class CursorTraversalTests(unittest.TestCase):
    def test_all_fixture_pages_verified_in_public_reproducer(self):
        result = reproduce()
        self.assertTrue(result["full_cursor_match"])
        self.assertGreater(result["full_cursor_rows"], 40)

    def test_page_size_one_and_tied_timestamp_no_gaps_or_duplicates(self):
        with sqlite3.connect(":memory:") as db:
            db.execute(
                "CREATE TABLE synthetic_orders (order_id INTEGER PRIMARY KEY, tenant_id TEXT, status TEXT, created_at INTEGER)"
            )
            rows = [(i, "tenant-07", "PENDING", 200 + i // 4) for i in range(1, 38)]
            db.executemany(
                "INSERT INTO synthetic_orders VALUES (?,?,?,?)", list(reversed(rows))
            )
            for size in (1, 2, 7, 20, 1000):
                self.assertEqual(list(cursor_rows(db, page_size=size)), rows)
            self.assertEqual(
                list(cursor_rows(db, parameters=("absent", "PENDING", 200))), []
            )

    def test_page_size_rejects_ambiguous_values(self):
        with sqlite3.connect(":memory:") as db:
            for invalid in (True, 0, 1001, "20"):
                with self.assertRaises(EvidenceError):
                    list(cursor_rows(db, page_size=invalid))
