import unittest

from test_store import AT, StoreTests, contract, event


class MaterializationDepthTests(unittest.TestCase):
    setUp = StoreTests.setUp
    values = StoreTests.values

    def test_input_scan_count_depends_on_event_types_not_contracts(self):
        for index in range(30):
            self.store.register(contract(f"reads_{index}", "event_count"), AT)
        self.store.ingest("first", [event()], AT)
        statements = []
        self.store.db.set_trace_callback(statements.append)
        self.store.materialize("2026-09-20", AT)
        self.store.db.set_trace_callback(None)
        scans = [
            statement
            for statement in statements
            if statement.startswith("SELECT event_id,content_hash")
        ]
        self.assertEqual(len(scans), 2)
        self.assertEqual(len(self.values()), 33)
        hashes = {
            self.store.lineage(row["run_id"])["source_hash"]
            for row in self.store.metrics("2026-09-20", "2026-09-20")
            if row["metric_id"] != "revenue"
        }
        self.assertEqual(len(hashes), 1)

    def test_cache_does_not_cross_transaction_revision(self):
        self.store.ingest("first", [event()], AT)
        self.store.materialize("2026-09-20", AT)
        self.store.ingest("second", [event("e2", "u2")], AT)
        self.store.materialize("2026-09-20", AT)
        self.assertEqual(self.values()["readers"], 2)
        self.assertEqual(self.values()["reads"], 2)
