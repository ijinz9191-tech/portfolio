from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .evaluator import EvaluationResult
from .models import EvaluationCase, RunTrace


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def migrate(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS cases(
              case_id TEXT PRIMARY KEY, suite TEXT NOT NULL, payload TEXT NOT NULL, digest TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs(
              run_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(case_id),
              payload TEXT NOT NULL, digest TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS results(
              run_id TEXT PRIMARY KEY REFERENCES runs(run_id), case_id TEXT NOT NULL,
              passed INTEGER NOT NULL, score REAL NOT NULL, payload TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def put_case(self, case: EvaluationCase) -> bool:
        payload = case.as_dict()
        digest = _digest(payload)
        row = self.connection.execute("SELECT digest FROM cases WHERE case_id=?", (case.case_id,)).fetchone()
        if row:
            if row["digest"] != digest:
                raise ValueError("case_id already exists with different content")
            return False
        self.connection.execute(
            "INSERT INTO cases(case_id,suite,payload,digest) VALUES(?,?,?,?)",
            (case.case_id, case.suite, _canonical(payload), digest),
        )
        self.connection.commit()
        return True

    def get_case(self, case_id: str) -> EvaluationCase | None:
        row = self.connection.execute("SELECT payload FROM cases WHERE case_id=?", (case_id,)).fetchone()
        return EvaluationCase.from_dict(json.loads(row["payload"])) if row else None

    def put_run(self, run: RunTrace) -> bool:
        if not self.get_case(run.case_id):
            raise KeyError(f"unknown case_id: {run.case_id}")
        payload = run.as_dict()
        digest = _digest(payload)
        row = self.connection.execute("SELECT digest FROM runs WHERE run_id=?", (run.run_id,)).fetchone()
        if row:
            if row["digest"] != digest:
                raise ValueError("run_id already exists with different content")
            return False
        self.connection.execute(
            "INSERT INTO runs(run_id,case_id,payload,digest) VALUES(?,?,?,?)",
            (run.run_id, run.case_id, _canonical(payload), digest),
        )
        self.connection.commit()
        return True

    def put_result(self, result: EvaluationResult) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO results(run_id,case_id,passed,score,payload) VALUES(?,?,?,?,?)",
            (result.run_id, result.case_id, int(result.passed), result.score, _canonical(result.as_dict())),
        )
        self.connection.commit()

    def get_run_report(self, run_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT r.payload AS run_payload, e.payload AS result_payload FROM runs r LEFT JOIN results e ON e.run_id=r.run_id WHERE r.run_id=?",
            (run_id,),
        ).fetchone()
        if not row:
            return None
        return {"run": json.loads(row["run_payload"]), "evaluation": json.loads(row["result_payload"]) if row["result_payload"] else None}

    def results_for_suite(self, suite: str) -> list[EvaluationResult]:
        rows = self.connection.execute(
            "SELECT e.payload FROM results e JOIN cases c ON c.case_id=e.case_id WHERE c.suite=? ORDER BY e.run_id",
            (suite,),
        ).fetchall()
        return [EvaluationResult(**{**json.loads(row["payload"]), "violations": tuple(json.loads(row["payload"])["violations"])}) for row in rows]

    def load_cases(self, cases: Iterable[EvaluationCase]) -> int:
        return sum(1 for case in cases if self.put_case(case))
