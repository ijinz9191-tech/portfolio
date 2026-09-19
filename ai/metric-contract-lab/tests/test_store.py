import json
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import quote

from metriclab.store import Store, ValidationError, read_json
from metriclab.api import make_server

AT = "2026-09-20T12:00:00Z"


def contract(metric="readers", operation="distinct_users", kind="read", version=1):
    return {"metric_id": metric, "version": version, "name": metric, "description": "Daily synthetic metric",
            "owner": "Content Analytics", "event_type": kind, "aggregation": operation}


def event(eid="e1", actor="u1", occurred="2026-09-20T10:00:00Z", kind="read", amount=0):
    return {"event_id": eid, "actor_id": actor, "occurred_at": occurred, "event_type": kind, "amount_cents": amount}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "metrics.sqlite"
        self.store = Store(self.path)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.store.close)
        self.store.register(contract(), AT)
        self.store.register(contract("reads", "event_count"), AT)
        self.store.register(contract("revenue", "sum_amount_cents", "purchase"), AT)

    def values(self, event_day="2026-09-20"):
        return {row["metric_id"]: row["value"] for row in self.store.metrics(event_day, event_day)}

    def test_exact_definitions_and_zero_value(self):
        self.store.ingest("first", [event(), event("e2"), event("e3", "u2"),
                                   event("p1", kind="purchase", amount=1299)], AT)
        self.store.materialize("2026-09-20", AT)
        self.assertEqual(self.values(), {"readers": 2, "reads": 3, "revenue": 1299})
        self.store.materialize("2026-09-19", AT)
        self.assertEqual(self.values("2026-09-19"), {"readers": 0, "reads": 0, "revenue": 0})

    def test_utc_day_boundary(self):
        self.store.ingest("boundary", [event("before", occurred="2026-09-19T23:59:59Z"),
                                      event("after", occurred="2026-09-20T00:00:00Z")], AT)
        for date in ("2026-09-19", "2026-09-20"):
            self.store.materialize(date, AT)
            self.assertEqual(self.values(date)["reads"], 1)

    def test_invalid_batch_is_atomic(self):
        with self.assertRaisesRegex(ValidationError, "INVALID_AMOUNT"):
            self.store.ingest("bad", [event("valid"), event("bad", amount=True)], AT)
        self.assertEqual(self.store.quality()["event_count"], 0)
        self.assertEqual(self.store.quality()["accepted_batches"], 0)

    def test_conflict_mid_batch_rolls_back_earlier_insert(self):
        self.store.ingest("first", [event()], AT)
        with self.assertRaisesRegex(ValidationError, "EVENT_ID_CONFLICT"):
            self.store.ingest("conflict", [event("new"), event(actor="different")], AT)
        self.assertEqual(self.store.quality()["event_count"], 1)
        self.assertEqual(self.store.quality()["accepted_batches"], 1)

    def test_duplicate_in_batch_and_replay(self):
        data = [event(), event()]
        result = self.store.ingest("first", data, AT)
        self.assertEqual((result["inserted"], result["duplicates"]), (1, 1))
        self.assertTrue(self.store.ingest("first", data, AT)["replayed"])
        self.assertEqual(self.store.quality()["accepted_batches"], 1)
        with self.assertRaisesRegex(ValidationError, "BATCH_ID_CONFLICT"):
            self.store.ingest("first", [event("new")], AT)

    def test_durable_receipt_replay_after_late_window(self):
        original = self.store.ingest("first", [event()], AT)
        reopened = Store(self.path)
        try:
            replay = reopened.ingest("first", [event()], "2026-10-20T12:00:00Z")
            self.assertEqual(replay, dict(original, replayed=True))
            self.assertEqual(reopened.quality()["event_count"], 1)
            with self.assertRaisesRegex(ValidationError, "BATCH_ID_CONFLICT"):
                reopened.ingest("first", [event("changed")], "2026-10-20T12:00:00Z")
            with self.assertRaisesRegex(ValidationError, "LATE_WINDOW_EXCEEDED"):
                reopened.ingest("new-batch", [event("new")], "2026-10-20T12:00:00Z")
        finally:
            reopened.close()

    def test_late_event_marks_stale_then_rebuild_keeps_prior_run(self):
        self.store.ingest("initial", [event("old", occurred="2026-09-19T10:00:00Z")], AT)
        run_ids = self.store.materialize("2026-09-19", AT)["run_ids"]
        before = self.store.lineage(run_ids[0])
        self.store.ingest("late", [event("late", actor="u2", occurred="2026-09-19T12:00:00Z")], AT)
        self.assertEqual(self.store.quality()["stale_materializations"], 3)
        self.assertTrue(all(row["freshness"] == "STALE" for row in self.store.metrics("2026-09-19", "2026-09-19")))
        self.store.materialize("2026-09-19", AT)
        self.assertEqual(self.values("2026-09-19")["readers"], 2)
        self.assertEqual(self.store.quality()["stale_materializations"], 0)
        self.assertEqual(self.store.lineage(run_ids[0]), before)

    def test_older_than_seven_days_and_future_rejected(self):
        for occurred, error in [("2026-09-12T23:59:59Z", "LATE_WINDOW_EXCEEDED"),
                                ("2026-09-20T12:05:01Z", "FUTURE_EVENT")]:
            with self.assertRaisesRegex(ValidationError, error):
                self.store.ingest("bad", [event(occurred=occurred)], AT)
        self.store.ingest("edge", [event(occurred="2026-09-13T00:00:00Z")], AT)
        self.assertEqual(self.store.quality()["event_count"], 1)

    def test_contract_version_immutable_and_previous_values_readable(self):
        self.store.ingest("first", [event(), event("e2")], AT)
        self.store.materialize("2026-09-20", AT)
        with self.assertRaisesRegex(ValidationError, "IMMUTABLE_CONTRACT_VERSION"):
            self.store.register(contract(operation="event_count"), AT)
        self.store.register(contract(operation="event_count", version=2), AT)
        self.store.materialize("2026-09-20", AT)
        values = {row["version"]: row["value"] for row in self.store.metrics("2026-09-20", "2026-09-20", "readers")}
        self.assertEqual(values, {1: 1, 2: 2})
        with self.assertRaisesRegex(ValidationError, "VERSION_MUST_INCREMENT"):
            self.store.register(contract(version=4), AT)

    def test_restart_preserves_receipts_and_queries(self):
        self.store.ingest("first", [event()], AT)
        self.store.materialize("2026-09-20", AT)
        reopened = Store(self.path)
        try:
            self.assertTrue(reopened.ingest("first", [event()], AT)["replayed"])
            self.assertEqual(reopened.metrics("2026-09-20", "2026-09-20", "readers")[0]["value"], 1)
        finally:
            reopened.close()

    def test_sql_injection_is_not_executed(self):
        for malicious in ["readers'; DROP TABLE events;--", "../secret", "u space"]:
            with self.assertRaises(ValidationError):
                self.store.metrics("2026-09-20", "2026-09-20", malicious)
        with self.assertRaisesRegex(ValidationError, "CONTRACT_OPERATION"):
            self.store.register(contract(operation="count(*); DROP TABLE events"), AT)
        self.assertEqual(self.store.quality()["event_count"], 0)

    def test_limits_and_extra_fields_reject(self):
        with self.assertRaisesRegex(ValidationError, "BATCH_EVENT_LIMIT"):
            self.store.ingest("huge", [event()] * 1001, AT)
        with self.assertRaisesRegex(ValidationError, "EVENT_FIELDS"):
            self.store.ingest("private", [dict(event(), email="synthetic@example.invalid")], AT)
        with self.assertRaisesRegex(ValidationError, "DATE_RANGE_LIMIT"):
            self.store.metrics("2026-01-01", "2026-12-31")
        with self.assertRaisesRegex(ValidationError, "TIMESTAMP_MUST_BE_UTC_SECONDS"):
            self.store.ingest("offset", [event(occurred="2026-09-20T19:00:00+09:00")], AT)

    def test_enum_fields_reject_non_string_json_values(self):
        for invalid in ([], {}, True, 1, None):
            bad_contract = contract(metric=f"bad_{type(invalid).__name__.lower()}")
            bad_contract["event_type"] = invalid
            with self.assertRaisesRegex(ValidationError, "CONTRACT_OPERATION"):
                self.store.register(bad_contract, AT)
            bad_contract = contract(metric=f"agg_{type(invalid).__name__.lower()}")
            bad_contract["aggregation"] = invalid
            with self.assertRaisesRegex(ValidationError, "CONTRACT_OPERATION"):
                self.store.register(bad_contract, AT)
            bad_event = event(eid=f"event_{type(invalid).__name__.lower()}")
            bad_event["event_type"] = invalid
            with self.assertRaisesRegex(ValidationError, "EVENT_TYPE"):
                self.store.ingest(f"batch_{type(invalid).__name__.lower()}", [bad_event], AT)

    def test_materialization_failure_rolls_back_and_recovers(self):
        self.store.ingest("first", [event()], AT)
        self.store.materialize("2026-09-20", AT)
        before = self.store.metrics("2026-09-20", "2026-09-20")
        # A temporary synthetic SQLite failure, not a weakened production assertion.
        self.store.db.executescript("""CREATE TRIGGER injected_failure BEFORE INSERT ON metric_runs
          WHEN NEW.metric_id='revenue' BEGIN SELECT RAISE(ABORT,'synthetic disk failure'); END;""")
        with self.assertRaisesRegex(sqlite3.DatabaseError, "synthetic disk failure"):
            self.store.materialize("2026-09-20", AT)
        self.assertEqual(self.store.metrics("2026-09-20", "2026-09-20"), before)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM metric_runs").fetchone()[0], 3)
        self.store.db.execute("DROP TRIGGER injected_failure")
        self.store.materialize("2026-09-20", AT)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM metric_runs").fetchone()[0], 6)

    def test_raw_evidence_is_immutable_and_readonly_store_blocks_write(self):
        self.store.ingest("first", [event()], AT)
        self.store.materialize("2026-09-20", AT)
        for statement in ["DELETE FROM events", "UPDATE contracts SET version=2", "DELETE FROM metric_runs"]:
            with self.assertRaisesRegex(sqlite3.DatabaseError, "immutable"):
                self.store.db.execute(statement)
            self.store.db.rollback()
        ro = Store(self.path, readonly=True)
        try:
            with self.assertRaisesRegex(ValidationError, "READ_ONLY"):
                ro.ingest("second", [event("e2")], AT)
        finally:
            ro.close()


class InterfaceTests(unittest.TestCase):
    def test_json_size_duplicate_keys_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "input.json"
            for content, error in [('{"key":1,"key":2}', "DUPLICATE_JSON_KEY"), ('[NaN]', "NONFINITE_JSON"),
                                   (" " * 1_048_577, "INPUT_TOO_LARGE")]:
                file.write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(ValidationError, error):
                    read_json(file)

    def test_actual_http_reads_filters_lineage_and_denies_mutations(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.sqlite"
            store = Store(path)
            store.register(contract(), AT)
            store.ingest("first", [event()], AT)
            run_id = store.materialize("2026-09-20", AT)["run_ids"][0]
            store.close()
            server = make_server(path)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                for route in ["/health", "/contracts", "/quality", "/metrics?start=2026-09-20&end=2026-09-20", f"/lineage/{run_id}"]:
                    with urlopen(base + route, timeout=3) as response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
                        body = json.load(response)
                        self.assertIsInstance(body, dict)
                        self.assertNotIn("actor_id", json.dumps(body))
                with urlopen(base + "/metrics?start=2026-09-20&end=2026-09-20", timeout=3) as response:
                    self.assertEqual(json.load(response)["metrics"][0]["value"], 1)
                for request, status in [
                    (Request(base + "/contracts", data=b"{}", method="POST"), 405),
                    (Request(base + "/quality", headers={"Host": "attacker.invalid"}), 403),
                    (Request(base + "/metrics?start=2026-09-20&end=2026-09-20&metric=" + quote("x'; DROP TABLE events")), 400),
                    (Request(base + "/metrics?start=2026-09-20&start=2026-09-19&end=2026-09-20"), 400),
                    (Request(base + "/../secret"), 404)]:
                    with self.assertRaises(HTTPError) as caught:
                        urlopen(request, timeout=3)
                    self.assertEqual(caught.exception.code, status)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_cli_init_contract_ingest_materialize_and_query(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            db = str(Path(directory) / "metrics.sqlite")
            definition = Path(directory) / "contract.json"
            data = Path(directory) / "events.json"
            definition.write_text(json.dumps(contract()), encoding="utf-8")
            data.write_text(json.dumps([event()]), encoding="utf-8")
            for args in [["init"], ["contract", str(definition)], ["ingest", "cli", str(data), "--at", AT],
                         ["materialize", "2026-09-20", "--at", AT], ["query", "2026-09-20", "2026-09-20"]]:
                result = subprocess.run([sys.executable, "-B", "-m", "metriclab", "--db", db, *args],
                                        cwd=root, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["metrics"][0]["value"], 1)


if __name__ == "__main__":
    unittest.main()
