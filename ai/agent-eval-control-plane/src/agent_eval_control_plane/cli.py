from __future__ import annotations

import argparse
import json
import threading
from pathlib import Path

from .evaluator import evaluate_run, release_gate
from .models import EvaluationCase, RunTrace
from .service import make_server
from .storage import Store


def _json(path: str) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def demo(db_path: str) -> dict:
    case = EvaluationCase.from_dict(
        {
            "case_id": "booking-refund-001",
            "suite": "booking-agent-v1",
            "prompt": "Explain a synthetic refund failure using the runbook evidence.",
            "required_facts": ["payment timeout", "retry queue"],
            "forbidden_terms": ["real customer"],
            "allowed_tools": ["runbook.search", "trace.lookup"],
            "max_tool_calls": 3,
            "latency_budget_ms": 3000,
            "cost_budget_units": 0.5,
        }
    )
    run = RunTrace.from_dict(
        {
            "run_id": "demo-run-001",
            "case_id": case.case_id,
            "output": "Synthetic evidence shows a payment timeout; the runbook routes it to the retry queue.",
            "latency_ms": 640,
            "cost_units": 0.08,
            "evidence_refs": ["fixture://trace/42", "fixture://runbook/refund"],
            "steps": [
                {"seq": 1, "kind": "retrieval", "name": "trace.lookup", "status": "ok", "duration_ms": 120},
                {"seq": 2, "kind": "tool", "name": "runbook.search", "status": "ok", "duration_ms": 90},
                {"seq": 3, "kind": "model", "name": "synthetic-agent", "status": "ok", "duration_ms": 430},
            ],
        }
    )
    with Store(db_path) as store:
        store.migrate()
        store.put_case(case)
        store.put_run(run)
        result = evaluate_run(case, run)
        store.put_result(result)
        return {"evaluation": result.as_dict(), "gate": release_gate([result])}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate synthetic AI-agent execution traces")
    sub = parser.add_subparsers(dest="command", required=True)
    p_demo = sub.add_parser("demo")
    p_demo.add_argument("--db", required=True)
    p_eval = sub.add_parser("evaluate")
    p_eval.add_argument("--db", required=True)
    p_eval.add_argument("--case", required=True)
    p_eval.add_argument("--trace", required=True)
    p_gate = sub.add_parser("gate")
    p_gate.add_argument("--db", required=True)
    p_gate.add_argument("--suite", required=True)
    p_serve = sub.add_parser("serve")
    p_serve.add_argument("--db", required=True)
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8080)
    args = parser.parse_args(argv)
    if args.command == "demo":
        payload = demo(args.db)
    elif args.command == "evaluate":
        case = EvaluationCase.from_dict(_json(args.case))
        trace = RunTrace.from_dict(_json(args.trace))
        with Store(args.db) as store:
            store.migrate()
            store.put_case(case)
            store.put_run(trace)
            result = evaluate_run(case, trace)
            store.put_result(result)
        payload = result.as_dict()
    elif args.command == "gate":
        with Store(args.db) as store:
            store.migrate()
            payload = release_gate(store.results_for_suite(args.suite))
    else:
        server = make_server(args.db, args.host, args.port)
        print(json.dumps({"listening": server.server_address}, ensure_ascii=False), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload.get("passed", payload.get("gate", {}).get("passed", True)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
