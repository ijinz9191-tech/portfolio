"""Offline, deterministic latency attribution for synthetic request traces."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path


class TraceError(ValueError):
    pass


def _union_ms(intervals: list[tuple[int, int]]) -> int:
    total = 0
    end = -1
    for start, stop in sorted(intervals):
        total += max(0, stop - max(start, end))
        end = max(end, stop)
    return total


def analyze(document: dict) -> dict:
    if not isinstance(document, dict) or set(document) != {"scenario", "traces"}:
        raise TraceError("scenario and traces are required")
    if (
        not isinstance(document["scenario"], str)
        or not document["scenario"].strip()
        or len(document["scenario"]) > 80
    ):
        raise TraceError("scenario must be a bounded string")
    traces = document["traces"]
    if not isinstance(traces, list) or not 2 <= len(traces) <= 1000:
        raise TraceError("2 to 1000 traces are required for a latency percentile")
    seen = set()
    normalized = []
    requests = []
    for trace in traces:
        if not isinstance(trace, dict) or set(trace) != {"id", "spans"}:
            raise TraceError("every trace needs id and spans")
        trace_id, spans = trace["id"], trace["spans"]
        if (
            not isinstance(trace_id, str)
            or not trace_id.strip()
            or len(trace_id) > 80
            or trace_id in seen
        ):
            raise TraceError("trace ids must be unique bounded strings")
        seen.add(trace_id)
        if not isinstance(spans, list) or not 1 <= len(spans) <= 10000:
            raise TraceError("each trace needs 1 to 10000 spans")
        by_id = {}
        for span in spans:
            if not isinstance(span, dict) or set(span) != {
                "id",
                "service",
                "parent",
                "start_ms",
                "duration_ms",
            }:
                raise TraceError("span fields are incomplete")
            span_id, service, parent = span["id"], span["service"], span["parent"]
            start, duration = span["start_ms"], span["duration_ms"]
            if (
                not isinstance(span_id, str)
                or not span_id.strip()
                or len(span_id) > 80
                or span_id in by_id
            ):
                raise TraceError("span ids must be unique bounded strings")
            if not isinstance(service, str) or not service.strip() or len(service) > 80:
                raise TraceError("service must be a bounded string")
            if parent is not None and (
                not isinstance(parent, str) or not parent.strip()
            ):
                raise TraceError("parent must be a span id or null")
            if (
                type(start) is not int
                or type(duration) is not int
                or not 0 <= start <= 1_000_000
                or not 1 <= duration <= 1_000_000
            ):
                raise TraceError(
                    "start and duration must be bounded integer milliseconds"
                )
            if start + duration > 1_000_000:
                raise TraceError("span end exceeds limit")
            by_id[span_id] = span
        roots = [span for span in spans if span["parent"] is None]
        if len(roots) != 1:
            raise TraceError("exactly one root span is required")
        root = roots[0]
        if root["start_ms"] != 0:
            raise TraceError("root must start at zero")
        children_by_id = {key: [] for key in by_id}
        for span in spans:
            parent_id = span["parent"]
            if parent_id is None:
                continue
            if parent_id not in by_id or parent_id == span["id"]:
                raise TraceError("unknown or self parent")
            parent = by_id[parent_id]
            if (
                span["start_ms"] < parent["start_ms"]
                or span["start_ms"] + span["duration_ms"]
                > parent["start_ms"] + parent["duration_ms"]
            ):
                raise TraceError("child lies outside parent interval")
            children_by_id[parent_id].append(span)
        # 한 루트에서 모든 노드에 도달해야 하므로 분리된 순환도 거절한다.
        reached = set()
        pending = [root["id"]]
        while pending:
            node = pending.pop()
            if node in reached:
                raise TraceError("parent cycle")
            reached.add(node)
            pending.extend(child["id"] for child in children_by_id[node])
        if len(reached) != len(spans):
            raise TraceError("parent cycle or disconnected span")
        exclusive = {}
        for span in spans:
            children = [
                (child["start_ms"], child["start_ms"] + child["duration_ms"])
                for child in children_by_id[span["id"]]
            ]
            exclusive[span["id"]] = span["duration_ms"] - _union_ms(children)
        top = min(spans, key=lambda span: (-exclusive[span["id"]], span["id"]))
        requests.append(
            {
                "trace_id": trace_id,
                "root_duration_ms": root["duration_ms"],
                "largest_exclusive_span": top["id"],
                "service": top["service"],
                "exclusive_ms": exclusive[top["id"]],
            }
        )
        normalized.append(
            {"id": trace_id, "spans": sorted(spans, key=lambda span: span["id"])}
        )
    durations = sorted(row["root_duration_ms"] for row in requests)
    p95 = durations[(95 * len(durations) + 99) // 100 - 1]
    slow = [row for row in requests if row["root_duration_ms"] >= p95]
    canonical = {
        "scenario": document["scenario"],
        "traces": sorted(normalized, key=lambda row: row["id"]),
    }
    digest = hashlib.sha256(
        json.dumps(
            canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    return {
        "scenario": document["scenario"],
        "sample_count": len(requests),
        "p95_root_latency_ms": p95,
        "slow_trace_candidates": sorted(slow, key=lambda row: row["trace_id"]),
        "evidence_sha256": digest,
        "limits": "Synthetic trace spans only. Exclusive wall time identifies review candidates, not proven bottlenecks or production latency.",
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python latency.py TRACES.json", file=sys.stderr)
        return 2
    try:
        result = analyze(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TraceError) as exc:
        print(f"REJECTED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
