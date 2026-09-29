"""Offline handoff and deadline evidence audit for synthetic deliveries."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


class AuditError(ValueError):
    pass


STAGES = ("created", "assigned", "picked_up", "completed")


def audit(document: dict) -> dict:
    if not isinstance(document, dict) or set(document) != {"scenario", "now_min", "deliveries"}:
        raise AuditError("scenario, now_min and deliveries are required")
    scenario, now, deliveries = document["scenario"], document["now_min"], document["deliveries"]
    if not isinstance(scenario, str) or not scenario.strip() or len(scenario) > 80:
        raise AuditError("scenario must be a bounded string")
    if type(now) is not int or not 0 <= now <= 1_000_000:
        raise AuditError("now_min must be a bounded integer")
    if not isinstance(deliveries, list) or not 1 <= len(deliveries) <= 500:
        raise AuditError("1 to 500 deliveries are required")
    results = []
    seen = set()
    canonical = []
    for item in deliveries:
        if not isinstance(item, dict) or set(item) != {"id", "deadline_min", "events"}:
            raise AuditError("delivery fields are incomplete")
        delivery_id, deadline, events = item["id"], item["deadline_min"], item["events"]
        if not isinstance(delivery_id, str) or not delivery_id.strip() or len(delivery_id) > 80 or delivery_id in seen:
            raise AuditError("delivery ids must be unique bounded strings")
        seen.add(delivery_id)
        if type(deadline) is not int or not 0 <= deadline <= 1_000_000:
            raise AuditError("deadline_min must be a bounded integer")
        if not isinstance(events, list) or not 1 <= len(events) <= 4:
            raise AuditError("1 to 4 events are required")
        observed = {}
        previous_time = -1
        for event in events:
            if not isinstance(event, dict) or set(event) != {"stage", "at_min", "actor"}:
                raise AuditError("event fields are incomplete")
            stage, at, actor = event["stage"], event["at_min"], event["actor"]
            if stage not in STAGES or stage in observed:
                raise AuditError("unknown or duplicate stage")
            if type(at) is not int or not 0 <= at <= now or at < previous_time:
                raise AuditError("event time must be ordered and no later than now")
            if not isinstance(actor, str) or not actor.strip() or len(actor) > 80:
                raise AuditError("actor evidence is required")
            observed[stage] = at
            previous_time = at
        ordered = [stage for stage in STAGES if stage in observed]
        if ordered != [event["stage"] for event in events]:
            raise AuditError("stage order must follow the delivery flow")
        if events[0]["stage"] != "created":
            raise AuditError("first event must be created")
        missing = [stage for stage in STAGES[:STAGES.index(events[-1]["stage"])+1] if stage not in observed]
        if missing:
            decision = "EVIDENCE_GAP"
        elif "completed" in observed:
            decision = "ON_TIME" if observed["completed"] <= deadline else "LATE_COMPLETION"
        elif now > deadline:
            decision = "OVERDUE_OPEN"
        else:
            decision = "PENDING"
        results.append({"id": delivery_id, "decision": decision, "last_stage": events[-1]["stage"],
                        "missing_handoffs": missing, "deadline_min": deadline})
        canonical.append(item)
    payload = {"scenario": scenario, "now_min": now, "deliveries": sorted(canonical, key=lambda row: row["id"])}
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"scenario": scenario, "deliveries": sorted(results, key=lambda row: row["id"]),
            "evidence_sha256": digest,
            "limits": "Synthetic event evidence only. A gap cannot be inferred as an actual failed handoff; deadlines are hypothetical."}


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python audit.py DELIVERIES.json", file=sys.stderr)
        return 2
    try:
        result = audit(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, AuditError) as exc:
        print(f"REJECTED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
