from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_eval_control_plane.cli import demo  # noqa: E402
from agent_eval_control_plane.evaluator import evaluate_run, release_gate  # noqa: E402
from agent_eval_control_plane.models import EvaluationCase, RunTrace, ValidationError  # noqa: E402
from agent_eval_control_plane.service import make_server  # noqa: E402
from agent_eval_control_plane.storage import Store  # noqa: E402


def case_raw(**changes):
    value = {
        "case_id": "case-1",
        "suite": "suite-1",
        "prompt": "Resolve a synthetic booking incident.",
        "required_facts": ["timeout", "retry"],
        "forbidden_terms": ["real customer"],
        "allowed_tools": ["trace.lookup", "runbook.search"],
        "max_tool_calls": 2,
        "latency_budget_ms": 1000,
        "cost_budget_units": 0.3,
    }
    value.update(changes)
    return value


def run_raw(**changes):
    value = {
        "run_id": "run-1",
        "case_id": "case-1",
        "output": "The synthetic trace shows a timeout and the runbook recommends retry.",
        "latency_ms": 800,
        "cost_units": 0.2,
        "evidence_refs": ["fixture://trace/1"],
        "steps": [
            {"seq": 1, "kind": "retrieval", "name": "trace.lookup", "status": "ok", "duration_ms": 100},
            {"seq": 2, "kind": "tool", "name": "runbook.search", "status": "ok", "duration_ms": 100},
            {"seq": 3, "kind": "model", "name": "fixture-agent", "status": "ok", "duration_ms": 600},
        ],
    }
    value.update(changes)
    return value


class ModelTests(unittest.TestCase):
    def test_valid_case_and_run(self):
        self.assertEqual(EvaluationCase.from_dict(case_raw()).suite, "suite-1")
        self.assertEqual(RunTrace.from_dict(run_raw()).steps[-1].seq, 3)

    def test_malformed_case_rejected(self):
        with self.assertRaises(ValidationError):
            EvaluationCase.from_dict(case_raw(max_tool_calls=-1))

    def test_empty_trace_rejected(self):
        with self.assertRaises(ValidationError):
            RunTrace.from_dict(run_raw(steps=[]))

    def test_non_contiguous_steps_rejected(self):
        raw = run_raw()
        raw["steps"][1]["seq"] = 4
        with self.assertRaises(ValidationError):
            RunTrace.from_dict(raw)

    def test_unknown_step_kind_rejected(self):
        raw = run_raw()
        raw["steps"][0]["kind"] = "browser"
        with self.assertRaises(ValidationError):
            RunTrace.from_dict(raw)


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.case = EvaluationCase.from_dict(case_raw())

    def test_happy_path_passes(self):
        result = evaluate_run(self.case, RunTrace.from_dict(run_raw()))
        self.assertTrue(result.passed)
        self.assertEqual(result.score, 1.0)

    def test_required_fact_failure(self):
        result = evaluate_run(self.case, RunTrace.from_dict(run_raw(output="Only a timeout was observed.")))
        self.assertIn("required_facts", result.violations)

    def test_forbidden_term_is_safety_failure(self):
        result = evaluate_run(self.case, RunTrace.from_dict(run_raw(output="A real customer saw timeout and retry.")))
        self.assertIn("forbidden_terms", result.violations)

    def test_unapproved_tool_fails(self):
        raw = run_raw()
        raw["steps"][1]["name"] = "email.send"
        self.assertIn("tools_allowed", evaluate_run(self.case, RunTrace.from_dict(raw)).violations)

    def test_budget_failures_are_reported(self):
        result = evaluate_run(self.case, RunTrace.from_dict(run_raw(latency_ms=1001, cost_units=0.31)))
        self.assertEqual(set(result.violations), {"latency_budget", "cost_budget"})

    def test_failed_step_is_reported(self):
        raw = run_raw()
        raw["steps"][0]["status"] = "error"
        self.assertIn("steps_succeeded", evaluate_run(self.case, RunTrace.from_dict(raw)).violations)

    def test_missing_evidence_is_reported(self):
        self.assertIn("evidence_present", evaluate_run(self.case, RunTrace.from_dict(run_raw(evidence_refs=[]))).violations)

    def test_gate_requires_every_case(self):
        good = evaluate_run(self.case, RunTrace.from_dict(run_raw()))
        bad = evaluate_run(self.case, RunTrace.from_dict(run_raw(run_id="run-2", latency_ms=5000)))
        self.assertFalse(release_gate([good, bad])["passed"])
        self.assertTrue(release_gate([good])["passed"])

    def test_empty_gate_fails_closed(self):
        self.assertEqual(release_gate([])["reason"], "no_results")


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "eval.sqlite")
        self.store = Store(self.db)
        self.store.migrate()
        self.case = EvaluationCase.from_dict(case_raw())
        self.run = RunTrace.from_dict(run_raw())

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_idempotent_case_and_run(self):
        self.assertTrue(self.store.put_case(self.case))
        self.assertFalse(self.store.put_case(self.case))
        self.assertTrue(self.store.put_run(self.run))
        self.assertFalse(self.store.put_run(self.run))

    def test_conflicting_run_is_rejected(self):
        self.store.put_case(self.case)
        self.store.put_run(self.run)
        with self.assertRaises(ValueError):
            self.store.put_run(RunTrace.from_dict(run_raw(output="timeout retry changed")))

    def test_unknown_case_run_is_rejected(self):
        with self.assertRaises(KeyError):
            self.store.put_run(self.run)

    def test_transaction_survives_reopen(self):
        self.store.put_case(self.case)
        self.store.put_run(self.run)
        result = evaluate_run(self.case, self.run)
        self.store.put_result(result)
        self.store.close()
        self.store = Store(self.db)
        self.assertTrue(self.store.get_run_report("run-1")["evaluation"]["passed"])


class ServiceAndCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "eval.sqlite")
        demo(self.db)
        self.server = make_server(self.db)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tmp.cleanup()

    def get(self, path):
        with urlopen(self.base + path, timeout=2) as response:
            return response.status, json.loads(response.read())

    def test_health_and_run_report(self):
        self.assertEqual(self.get("/health")[1]["mode"], "read-only")
        status, report = self.get("/runs/demo-run-001")
        self.assertEqual(status, 200)
        self.assertTrue(report["evaluation"]["passed"])

    def test_suite_gate_endpoint(self):
        _, gate = self.get("/suites/booking-agent-v1/gate")
        self.assertTrue(gate["passed"])

    def test_post_is_blocked(self):
        request = Request(self.base + "/runs", data=b"{}", method="POST")
        with self.assertRaises(HTTPError) as error:
            urlopen(request, timeout=2)
        self.assertEqual(error.exception.code, 405)

    def test_cli_demo_and_gate(self):
        db = str(Path(self.tmp.name) / "cli.sqlite")
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        demo_result = subprocess.run(
            [sys.executable, "-m", "agent_eval_control_plane.cli", "demo", "--db", db],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertTrue(json.loads(demo_result.stdout)["gate"]["passed"])
        gate_result = subprocess.run(
            [sys.executable, "-m", "agent_eval_control_plane.cli", "gate", "--db", db, "--suite", "booking-agent-v1"],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(json.loads(gate_result.stdout)["pass_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
