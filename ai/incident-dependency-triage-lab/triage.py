"""가상 서비스 장애의 의존 관계와 관측 근거를 오프라인으로 검사합니다."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path


class TriageError(ValueError):
    pass


def analyze(document: dict) -> dict:
    if not isinstance(document, dict) or set(document) not in (
        {"incident_id", "services"}, {"incident_id", "services", "evaluated_at"}
    ):
        raise TriageError("incident_id and services are required")
    freshness_checked = "evaluated_at" in document
    evaluated_at = _time(document["evaluated_at"]) if freshness_checked else None
    incident_id = document["incident_id"]
    if not isinstance(incident_id, str) or not 1 <= len(incident_id.strip()) <= 80:
        raise TriageError("incident_id must be a bounded string")
    services = document["services"]
    if not isinstance(services, list) or not 2 <= len(services) <= 100:
        raise TriageError("2 to 100 services are required")
    graph = {}
    for row in services:
        expected = {"id", "depends_on", "healthy", "evidence"}
        if freshness_checked:
            expected.add("observed_at")
        if not isinstance(row, dict) or set(row) != expected:
            raise TriageError("every service needs id, depends_on, healthy and evidence")
        name, deps, healthy, evidence = (row[key] for key in ("id", "depends_on", "healthy", "evidence"))
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60 or name in graph:
            raise TriageError("service ids must be unique bounded strings")
        if not isinstance(deps, list) or len(deps) > 20 or any(not isinstance(dep, str) for dep in deps) or len(set(deps)) != len(deps):
            raise TriageError("dependencies must be a unique list of ids")
        if not isinstance(healthy, bool) or not isinstance(evidence, str) or not evidence.strip() or len(evidence) > 200:
            raise TriageError("health and evidence must be explicit")
        graph[name] = {"depends_on": deps, "healthy": healthy, "evidence": evidence}
        if freshness_checked:
            observed_at = _time(row["observed_at"])
            age = evaluated_at - observed_at
            if not timedelta(0) <= age <= timedelta(minutes=5):
                raise TriageError("observation is stale or from the future")
            graph[name]["observed_at"] = row["observed_at"]
    for name, row in graph.items():
        if name in row["depends_on"] or any(dep not in graph for dep in row["depends_on"]):
            raise TriageError("self or unknown dependency")
    order, visiting, visited = [], set(), set()

    def visit(name: str) -> None:
        if name in visiting:
            raise TriageError("dependency cycle")
        if name in visited:
            return
        visiting.add(name)
        for dep in sorted(graph[name]["depends_on"]):
            visit(dep)
        visiting.remove(name)
        visited.add(name)
        order.append(name)

    for name in sorted(graph):
        visit(name)

    failed = [name for name in order if not graph[name]["healthy"]]
    roots = [name for name in failed if all(graph[dep]["healthy"] for dep in graph[name]["depends_on"])]
    # 실패한 의존 서비스 뒤의 정상 관측은 반증으로 보존하고 실패로 바꾸지 않습니다.
    counterevidence = [name for name in order if graph[name]["healthy"] and
                       any(not graph[dep]["healthy"] for dep in graph[name]["depends_on"])]
    downstream = {}
    observed_downstream = {}
    for root in roots:
        reached = {root}
        for name in order:
            if name not in reached and any(dep in reached for dep in graph[name]["depends_on"]):
                reached.add(name)
        downstream[root] = sorted(reached - {root})
        observed_downstream[root] = sorted(name for name in reached - {root}
                                           if not graph[name]["healthy"])
    canonical = {"incident_id": incident_id, "services": [
        {"id": name, **{**graph[name], "depends_on": sorted(graph[name]["depends_on"])}}
        for name in sorted(graph)]}
    if freshness_checked:
        canonical["evaluated_at"] = document["evaluated_at"]
    digest = hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":")).encode()).hexdigest()
    return {"incident_id": incident_id, "decision": "TRIAGE" if failed else "NO_OBSERVED_FAILURE",
            "first_failed_candidates": roots, "observed_failed": failed,
            "dependency_first_review_order": failed,
            "healthy_downstream_counterevidence": counterevidence,
            "observation_freshness": "CHECKED_5_MINUTES" if freshness_checked else "LEGACY_UNCHECKED",
            "potentially_affected_by_candidate": downstream,
            "observed_failed_downstream": observed_downstream,
            "evidence_sha256": digest,
            "limits": "가상 서비스 관측만 사용합니다. 원인 후보는 사람이 확인해야 하며 자동 복구나 운영 장애의 확정 원인을 주장하지 않습니다."}


def _time(value: str) -> datetime:
    if not isinstance(value, str):
        raise TriageError("timestamp must be an ISO-8601 string with timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TriageError("invalid observation timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TriageError("timestamp must include timezone")
    return parsed


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python triage.py SNAPSHOT.json", file=sys.stderr)
        return 2
    try:
        result = analyze(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TriageError) as exc:
        print(f"REJECTED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
