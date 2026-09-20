from __future__ import annotations
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any
from .validator import Decision

class EvidenceStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS decisions (
                change_id TEXT PRIMARY KEY,
                evidence_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                payload TEXT NOT NULL,
                recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
            db.commit()

    def record(self, decision: Decision) -> str:
        payload = json.dumps(decision.to_dict(), ensure_ascii=False, sort_keys=True)
        with closing(self._connect()) as db:
            existing = db.execute(
                "SELECT evidence_hash FROM decisions WHERE change_id = ?",
                (decision.change_id,),
            ).fetchone()
            if existing:
                if existing["evidence_hash"] != decision.evidence_hash:
                    raise ValueError("change_id already exists with different evidence")
                return "IDEMPOTENT"
            db.execute(
                "INSERT INTO decisions(change_id,evidence_hash,status,payload) VALUES(?,?,?,?)",
                (decision.change_id, decision.evidence_hash, decision.status, payload),
            )
            db.commit()
        return "RECORDED"

    def get(self, change_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT payload, recorded_at FROM decisions WHERE change_id = ?",
                (change_id,),
            ).fetchone()
        if not row:
            return None
        value = json.loads(row["payload"])
        value["recorded_at"] = row["recorded_at"]
        return value

    def summary(self) -> dict[str, int]:
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT status, COUNT(*) AS count FROM decisions GROUP BY status"
            ).fetchall()
        result = {"APPROVED": 0, "BLOCKED": 0}
        result.update({row["status"]: row["count"] for row in rows})
        return result
