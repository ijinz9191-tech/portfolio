"""Offline dependency triage for synthetic service incidents."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


class TriageError(ValueError):
    pass


def analyze(document: dict) -> dict:
    if not isinstance(document, dict) or set(document) != {"incident_id", "services"}:
        raise TriageError("incident_id and services are required")
    incident_id = document["incident_id"]
    if not isinstance(incident_id, str) or not 1 <= len(incident_id.strip()) <= 80:
        raise TriageError("incident_id must be a bounded string")
    services = document["services"]
    if not isinstance(services, list) or not 2 <= len(services) <= 100:
        raise TriageError("2 to 100 services are required")
    graph = {}
    for row in services:
        if not isinstance(row, dict) or set(row) != {"id", "depends_on", "healthy", "evidence"}:
            raise TriageError("every service needs id, depends_on, healthy and evidence")
        name, deps, healthy, evidence = (row[key] for key in ("id", "depends_on", "healthy", "evidence"))
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60 or name in graph:
            raise TriageError("service ids must be unique bounded strings")
        if not isinstance(deps, list) or len(deps) > 20 or any(not isinstance(dep, str) for dep in deps) or len(set(deps)) != len(deps):
            raise TriageError("dependencies must be a unique list of ids")
        if not isinstance(healthy, bool) or not isinstance(evidence, str) or not evidence.strip() or len(evidence) > 200:
            raise TriageError("health and evidence must be explicit")
        graph[name] = {"depends_on": deps, "healthy": healthy, "evidence": evidence}
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
    # A healthy observation downstream of a failed dependency is retained as
    # counterevidence; it must not be silently marked failed.
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
    digest = hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":")).encode()).hexdigest()
    return {"incident_id": incident_id, "decision": "TRIAGE" if failed else "NO_OBSERVED_FAILURE",
            "first_failed_candidates": roots, "observed_failed": failed,
            "dependency_first_review_order": failed,
            "healthy_downstream_counterevidence": counterevidence,
            "potentially_affected_by_candidate": downstream,
            "observed_failed_downstream": observed_downstream,
            "evidence_sha256": digest,
            "limits": "Synthetic health snapshots only. Candidates require human verification; no automated remediation or production root-cause claim."}


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
