"""Validate a synthetic manufacturing event handoff before making a decision."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


class AuditError(ValueError):
    """The event log cannot support a completion claim."""


def _time(value: object) -> datetime:
    if not isinstance(value, str):
        raise AuditError("timestamp must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuditError("invalid timestamp") from exc
    if parsed.tzinfo is None:
        raise AuditError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def audit(document: dict) -> dict:
    if not isinstance(document, dict) or set(document) != {"version", "route", "events"}:
        raise AuditError("version, route and events are required")
    version, route, events = (document[key] for key in ("version", "route", "events"))
    if not isinstance(version, str) or not version.strip() or len(version) > 40:
        raise AuditError("invalid version")
    if not isinstance(route, list) or not 1 <= len(route) <= 20 or any(
        not isinstance(step, str) or not step.strip() or len(step) > 60 for step in route
    ) or len(set(route)) != len(route):
        raise AuditError("route requires unique bounded stations")
    if not isinstance(events, list) or not 1 <= len(events) <= 1000:
        raise AuditError("events requires 1 to 1000 rows")

    by_lot: dict[str, list[dict]] = {}
    ids: set[str] = set()
    for event in events:
        if not isinstance(event, dict) or set(event) != {"id", "lot", "station", "kind", "at"}:
            raise AuditError("event fields are incomplete")
        event_id, lot, station, kind = (event[key] for key in ("id", "lot", "station", "kind"))
        if any(not isinstance(value, str) or not value.strip() or len(value) > 80
               for value in (event_id, lot)):
            raise AuditError("event and lot ids must be bounded strings")
        if event_id in ids:
            raise AuditError("duplicate event id")
        ids.add(event_id)
        if station not in route or kind not in ("START", "COMPLETE"):
            raise AuditError("unknown station or event kind")
        by_lot.setdefault(lot, []).append({**event, "at_utc": _time(event["at"])})

    outcomes = []
    for lot, rows in sorted(by_lot.items()):
        rows.sort(key=lambda row: (row["at_utc"], row["id"]))
        previous_time = None
        cursor = 0
        for row in rows:
            if previous_time is not None and row["at_utc"] <= previous_time:
                raise AuditError("lot events require strictly increasing timestamps")
            previous_time = row["at_utc"]
            expected_station = route[cursor // 2] if cursor < 2 * len(route) else None
            expected_kind = "START" if cursor % 2 == 0 else "COMPLETE"
            if row["station"] != expected_station or row["kind"] != expected_kind:
                raise AuditError("lot has a missing, duplicate or out-of-order handoff")
            cursor += 1
        outcomes.append({"lot": lot, "decision": "COMPLETE" if cursor == 2 * len(route)
                         else "EVIDENCE_GAP", "verified_events": cursor,
                         "expected_events": 2 * len(route)})

    canonical = {"version": version, "route": route,
                 "events": sorted(events, key=lambda row: row["id"])}
    digest = hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"decision": "EVENT_SEQUENCE_AUDITED", "lots": outcomes,
            "evidence_sha256": digest,
            "limits": "Synthetic event sequence evidence only; no production MES, factory outcome or employer deployment claim."}


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python audit.py EVENTS.json", file=sys.stderr)
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
