"""Strict contracts, atomic event ingestion and reproducible metric materializations."""
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

MAX_EVENTS = 1000
MAX_BYTES = 1_048_576
MAX_RANGE_DAYS = 31
ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}\Z")
AGGREGATIONS = {"event_count", "distinct_users", "sum_amount_cents"}
EVENT_TYPES = {"read", "purchase"}


class ValidationError(ValueError):
    """Expected input/domain error; safe concise code returned to callers."""


def packed(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(packed(value).encode("utf-8")).hexdigest()


def utc(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise ValidationError("TIMESTAMP_MUST_BE_UTC_SECONDS")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValidationError("INVALID_TIMESTAMP") from exc


def day(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValidationError("INVALID_DAY")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValidationError("INVALID_DAY") from exc


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValidationError("INVALID_IDENTIFIER")
    return value


def clock(value=None):
    return value or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(filename):
    with open(filename, "rb") as stream:
        body = stream.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValidationError("INPUT_TOO_LARGE")
    try:
        def pairs(items):
            obj = {}
            for key, value in items:
                if key in obj:
                    raise ValidationError("DUPLICATE_JSON_KEY")
                obj[key] = value
            return obj
        return json.loads(body, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValidationError("NONFINITE_JSON")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError("INVALID_JSON") from exc


SCHEMA = """
CREATE TABLE IF NOT EXISTS contracts (
 metric_id TEXT NOT NULL, version INTEGER NOT NULL, body TEXT NOT NULL,
 content_hash TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(metric_id, version)
);
CREATE TABLE IF NOT EXISTS events (
 event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL, occurred_at TEXT NOT NULL,
 event_day TEXT NOT NULL, actor_id TEXT NOT NULL, amount_cents INTEGER NOT NULL,
 content_hash TEXT NOT NULL, received_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_day_type ON events(event_day, event_type);
CREATE TABLE IF NOT EXISTS day_revisions (event_day TEXT PRIMARY KEY, revision INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS batches (
 batch_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, summary TEXT NOT NULL, received_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS metric_runs (
 run_id INTEGER PRIMARY KEY AUTOINCREMENT, metric_id TEXT NOT NULL, version INTEGER NOT NULL,
 event_day TEXT NOT NULL, value INTEGER NOT NULL, input_count INTEGER NOT NULL,
 day_revision INTEGER NOT NULL, source_hash TEXT NOT NULL, contract_hash TEXT NOT NULL, built_at TEXT NOT NULL,
 FOREIGN KEY(metric_id, version) REFERENCES contracts(metric_id, version)
);
CREATE TABLE IF NOT EXISTS metric_heads (
 metric_id TEXT NOT NULL, version INTEGER NOT NULL, event_day TEXT NOT NULL, run_id INTEGER NOT NULL,
 PRIMARY KEY(metric_id, version, event_day), FOREIGN KEY(run_id) REFERENCES metric_runs(run_id)
);
CREATE TRIGGER IF NOT EXISTS immutable_contract_update BEFORE UPDATE ON contracts
 BEGIN SELECT RAISE(ABORT, 'immutable contract'); END;
CREATE TRIGGER IF NOT EXISTS immutable_contract_delete BEFORE DELETE ON contracts
 BEGIN SELECT RAISE(ABORT, 'immutable contract'); END;
CREATE TRIGGER IF NOT EXISTS immutable_event_update BEFORE UPDATE ON events
 BEGIN SELECT RAISE(ABORT, 'immutable event'); END;
CREATE TRIGGER IF NOT EXISTS immutable_event_delete BEFORE DELETE ON events
 BEGIN SELECT RAISE(ABORT, 'immutable event'); END;
CREATE TRIGGER IF NOT EXISTS immutable_run_update BEFORE UPDATE ON metric_runs
 BEGIN SELECT RAISE(ABORT, 'immutable run'); END;
CREATE TRIGGER IF NOT EXISTS immutable_run_delete BEFORE DELETE ON metric_runs
 BEGIN SELECT RAISE(ABORT, 'immutable run'); END;
"""


class Store:
    def __init__(self, filename, readonly=False):
        self.readonly = readonly
        if readonly:
            uri = Path(filename).resolve().as_uri() + "?mode=ro"
            self.db = sqlite3.connect(uri, uri=True, timeout=5)
            self.db.execute("PRAGMA query_only=ON")
        else:
            self.db = sqlite3.connect(filename, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        if not readonly:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    def _begin(self):
        if self.readonly:
            raise ValidationError("READ_ONLY")
        self.db.execute("BEGIN IMMEDIATE")

    def register(self, contract, at=None):
        expected = {"metric_id", "version", "name", "description", "owner", "event_type", "aggregation"}
        if not isinstance(contract, dict) or set(contract) != expected:
            raise ValidationError("CONTRACT_FIELDS")
        identifier(contract["metric_id"])
        if type(contract["version"]) is not int or not 1 <= contract["version"] <= 1000:
            raise ValidationError("CONTRACT_VERSION")
        for field in ("name", "description", "owner"):
            if not isinstance(contract[field], str) or not 1 <= len(contract[field]) <= 500:
                raise ValidationError("CONTRACT_TEXT")
        if (not isinstance(contract["event_type"], str)
                or not isinstance(contract["aggregation"], str)
                or contract["event_type"] not in EVENT_TYPES
                or contract["aggregation"] not in AGGREGATIONS):
            raise ValidationError("CONTRACT_OPERATION")
        if contract["aggregation"] == "sum_amount_cents" and contract["event_type"] != "purchase":
            raise ValidationError("AMOUNT_REQUIRES_PURCHASE")
        created = clock(at)
        utc(created)
        self._begin()
        try:
            previous = self.db.execute("SELECT content_hash FROM contracts WHERE metric_id=? AND version=?",
                                       (contract["metric_id"], contract["version"])).fetchone()
            if previous:
                if previous["content_hash"] != digest(contract):
                    raise ValidationError("IMMUTABLE_CONTRACT_VERSION")
                self.db.commit()
                return {"status": "UNCHANGED", "contract_hash": digest(contract)}
            maximum = self.db.execute("SELECT COALESCE(MAX(version),0) FROM contracts WHERE metric_id=?",
                                      (contract["metric_id"],)).fetchone()[0]
            if contract["version"] != maximum + 1:
                raise ValidationError("VERSION_MUST_INCREMENT")
            self.db.execute("INSERT INTO contracts VALUES (?, ?, ?, ?, ?)",
                            (contract["metric_id"], contract["version"], packed(contract), digest(contract), created))
            self.db.commit()
            return {"status": "REGISTERED", "contract_hash": digest(contract)}
        except Exception:
            self.db.rollback()
            raise

    def contracts(self):
        return [dict(json.loads(row["body"]), content_hash=row["content_hash"])
                for row in self.db.execute("SELECT body,content_hash FROM contracts ORDER BY metric_id,version")]

    def ingest(self, batch_id, events, at=None):
        if self.readonly:
            raise ValidationError("READ_ONLY")
        identifier(batch_id)
        if not isinstance(events, list) or not 1 <= len(events) <= MAX_EVENTS:
            raise ValidationError("BATCH_EVENT_LIMIT")
        if len(packed(events).encode("utf-8")) > MAX_BYTES:
            raise ValidationError("INPUT_TOO_LARGE")
        received = clock(at)
        instant = utc(received)
        payload_hash = digest(events)
        prior = self.db.execute("SELECT payload_hash,summary FROM batches WHERE batch_id=?", (batch_id,)).fetchone()
        if prior:
            if prior["payload_hash"] != payload_hash:
                raise ValidationError("BATCH_ID_CONFLICT")
            return dict(json.loads(prior["summary"]), replayed=True)
        # Validate the whole batch BEFORE changing storage. No partial acceptance.
        normalized = []
        for event in events:
            if not isinstance(event, dict) or set(event) != {"event_id", "event_type", "occurred_at", "actor_id", "amount_cents"}:
                raise ValidationError("EVENT_FIELDS")
            identifier(event["event_id"])
            identifier(event["actor_id"])
            if not isinstance(event["event_type"], str) or event["event_type"] not in EVENT_TYPES:
                raise ValidationError("EVENT_TYPE")
            occurred = utc(event["occurred_at"])
            if occurred > instant + timedelta(minutes=5):
                raise ValidationError("FUTURE_EVENT")
            if (instant.date() - occurred.date()).days > 7:
                raise ValidationError("LATE_WINDOW_EXCEEDED")
            amount = event["amount_cents"]
            if type(amount) is not int or not 0 <= amount <= 1_000_000_000:
                raise ValidationError("INVALID_AMOUNT")
            if event["event_type"] == "read" and amount != 0:
                raise ValidationError("READ_AMOUNT_MUST_BE_ZERO")
            normalized.append((event, occurred.strftime("%Y-%m-%d")))
        payload_hash = digest(events)
        self._begin()
        try:
            prior = self.db.execute("SELECT * FROM batches WHERE batch_id=?", (batch_id,)).fetchone()
            if prior:
                if prior["payload_hash"] != payload_hash:
                    raise ValidationError("BATCH_ID_CONFLICT")
                result = json.loads(prior["summary"])
                result["replayed"] = True
                self.db.commit()
                return result
            inserted = duplicates = late = 0
            touched = set()
            for event, event_day in normalized:
                existing = self.db.execute("SELECT content_hash FROM events WHERE event_id=?", (event["event_id"],)).fetchone()
                if existing:
                    if existing["content_hash"] != digest(event):
                        raise ValidationError("EVENT_ID_CONFLICT")
                    duplicates += 1
                    continue
                self.db.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                (event["event_id"], event["event_type"], event["occurred_at"], event_day,
                                 event["actor_id"], event["amount_cents"], digest(event), received))
                inserted += 1
                late += int(event_day < received[:10])
                touched.add(event_day)
            for event_day in sorted(touched):
                self.db.execute("INSERT INTO day_revisions VALUES (?,1) ON CONFLICT(event_day) DO UPDATE SET revision=revision+1",
                                (event_day,))
            summary = {"batch_id": batch_id, "inserted": inserted, "duplicates": duplicates,
                       "late": late, "affected_days": sorted(touched), "replayed": False}
            self.db.execute("INSERT INTO batches VALUES (?, ?, ?, ?)", (batch_id, payload_hash, packed(summary), received))
            self.db.commit()
            return summary
        except Exception:
            self.db.rollback()
            raise

    def materialize(self, event_day, at=None):
        day(event_day)
        built = clock(at)
        utc(built)
        self._begin()
        try:
            contracts = self.db.execute("""SELECT c.* FROM contracts c
              JOIN (SELECT metric_id,MAX(version) AS version FROM contracts GROUP BY metric_id) latest
              USING(metric_id,version) ORDER BY c.metric_id""").fetchall()
            if not contracts:
                raise ValidationError("NO_CONTRACTS")
            revision = self.db.execute("SELECT revision FROM day_revisions WHERE event_day=?", (event_day,)).fetchone()
            revision = revision[0] if revision else 0
            run_ids = []
            for row in contracts:
                contract = json.loads(row["body"])
                inputs = self.db.execute("SELECT event_id,content_hash,actor_id,amount_cents FROM events WHERE event_day=? AND event_type=? ORDER BY event_id",
                                         (event_day, contract["event_type"])).fetchall()
                # Operation is a validated enum; no user expression or SQL is executed.
                if contract["aggregation"] == "event_count":
                    value = len(inputs)
                elif contract["aggregation"] == "distinct_users":
                    value = len({item["actor_id"] for item in inputs})
                else:
                    value = sum(item["amount_cents"] for item in inputs)
                source_hash = digest([[item["event_id"], item["content_hash"]] for item in inputs])
                cursor = self.db.execute("""INSERT INTO metric_runs
                  (metric_id,version,event_day,value,input_count,day_revision,source_hash,contract_hash,built_at)
                  VALUES (?,?,?,?,?,?,?,?,?)""",
                  (row["metric_id"], row["version"], event_day, value, len(inputs), revision, source_hash, row["content_hash"], built))
                run_ids.append(cursor.lastrowid)
                self.db.execute("""INSERT INTO metric_heads VALUES (?,?,?,?)
                  ON CONFLICT(metric_id,version,event_day) DO UPDATE SET run_id=excluded.run_id""",
                  (row["metric_id"], row["version"], event_day, cursor.lastrowid))
            self.db.commit()
            return {"day": event_day, "run_ids": run_ids, "day_revision": revision}
        except Exception:
            self.db.rollback()
            raise

    def metrics(self, start, end, metric_id=None):
        first, last = day(start), day(end)
        if last < first or (last - first).days >= MAX_RANGE_DAYS:
            raise ValidationError("DATE_RANGE_LIMIT")
        if metric_id is not None:
            identifier(metric_id)
        rows = self.db.execute("""SELECT r.*,COALESCE(d.revision,0) AS current_revision FROM metric_heads h
          JOIN metric_runs r ON h.run_id=r.run_id LEFT JOIN day_revisions d ON r.event_day=d.event_day
          WHERE r.event_day BETWEEN ? AND ? AND (? IS NULL OR r.metric_id=?)
          ORDER BY r.event_day,r.metric_id,r.version LIMIT 1001""", (start, end, metric_id, metric_id)).fetchall()
        if len(rows) > 1000:
            raise ValidationError("RESULT_LIMIT")
        return [dict(row, freshness="FRESH" if row["day_revision"] == row["current_revision"] else "STALE") for row in rows]

    def quality(self):
        counts = self.db.execute("SELECT COUNT(*) AS events,COUNT(DISTINCT event_day) AS days FROM events").fetchone()
        stale = self.db.execute("""SELECT COUNT(*) FROM metric_heads h JOIN metric_runs r ON h.run_id=r.run_id
          LEFT JOIN day_revisions d ON d.event_day=r.event_day WHERE r.day_revision != COALESCE(d.revision,0)""").fetchone()[0]
        batches = [json.loads(row[0]) for row in self.db.execute("SELECT summary FROM batches")]
        return {"data_policy": "Synthetic inputs required; content is not classified automatically", "event_count": counts["events"], "event_days": counts["days"],
                "accepted_batches": len(batches), "duplicate_events": sum(b["duplicates"] for b in batches),
                "late_events": sum(b["late"] for b in batches), "stale_materializations": stale}

    def lineage(self, run_id):
        if type(run_id) is not int or run_id < 1:
            raise ValidationError("INVALID_RUN_ID")
        row = self.db.execute("SELECT * FROM metric_runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise ValidationError("RUN_NOT_FOUND")
        result = dict(row)
        result["contract"] = json.loads(self.db.execute("SELECT body FROM contracts WHERE metric_id=? AND version=?",
                                                       (row["metric_id"], row["version"])).fetchone()[0])
        result["source_table"] = "events"
        result["selection"] = {"day_utc": row["event_day"], "event_type": result["contract"]["event_type"]}
        result["lineage_kind"] = "immutable run with input set hash; raw actor IDs are not returned"
        return result
