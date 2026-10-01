"""Audit synthetic robot command observations; no device or network access."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


class AuditError(ValueError):
    """The command observations cannot support a safe conclusion."""


FIELDS = {
    "request_id",
    "robot_id",
    "action",
    "requested_at",
    "accepted_at",
    "completed_at",
    "result",
}


def _time(value: object) -> datetime:
    if not isinstance(value, str):
        raise AuditError("timestamp must be a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuditError("invalid timestamp") from exc
    if parsed.tzinfo is None:
        raise AuditError("timestamp requires a timezone")
    return parsed.astimezone(timezone.utc)


def _name(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 80:
        raise AuditError("identifier/action must be a bounded non-empty string")
    return value


def audit(document: dict) -> dict:
    if not isinstance(document, dict) or set(document) != {"version", "commands"}:
        raise AuditError("version and commands are required")
    version = _name(document["version"])
    commands = document["commands"]
    if not isinstance(commands, list) or not 1 <= len(commands) <= 500:
        raise AuditError("commands requires 1 to 500 rows")

    seen_ids: set[str] = set()
    per_robot: dict[str, list[tuple[datetime, datetime | None, str]]] = {}
    results = []
    timings = []
    for item in commands:
        if not isinstance(item, dict) or set(item) != FIELDS:
            raise AuditError("command fields are incomplete")
        request_id = _name(item["request_id"])
        robot_id = _name(item["robot_id"])
        _name(item["action"])
        if request_id in seen_ids:
            raise AuditError("duplicate request id")
        seen_ids.add(request_id)
        requested = _time(item["requested_at"])
        accepted = (
            _time(item["accepted_at"]) if item["accepted_at"] is not None else None
        )
        completed = (
            _time(item["completed_at"]) if item["completed_at"] is not None else None
        )
        if accepted is not None and accepted < requested:
            raise AuditError("acceptance precedes request")
        if completed is not None and (accepted is None or completed <= accepted):
            raise AuditError("completion requires earlier acceptance")
        if item["result"] not in (None, "SUCCEEDED", "FAILED"):
            raise AuditError("unknown result")
        if (item["result"] is None) != (completed is None):
            raise AuditError("result and completion observation must agree")
        decision = item["result"] if completed is not None else "EVIDENCE_GAP"
        # 정수 마이크로초로 대기/실행 시간을 나눠 부동소수 반올림을 피한다.
        timings.append(
            {
                "request_id": request_id,
                "queue_us": (accepted - requested) // timedelta(microseconds=1)
                if accepted is not None
                else None,
                "execution_us": (completed - accepted) // timedelta(microseconds=1)
                if completed is not None
                else None,
            }
        )
        results.append(
            {"request_id": request_id, "robot_id": robot_id, "decision": decision}
        )
        per_robot.setdefault(robot_id, []).append((requested, completed, request_id))

    for rows in per_robot.values():
        rows.sort(key=lambda row: (row[0], row[2]))
        for previous, current in zip(rows, rows[1:]):
            if previous[1] is None or current[0] < previous[1]:
                raise AuditError("overlapping or unresolved robot commands")

    canonical = {
        "version": version,
        "commands": sorted(commands, key=lambda row: row["request_id"]),
    }
    digest = hashlib.sha256(
        json.dumps(
            canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    return {
        "decision": "COMMAND_EVIDENCE_AUDITED",
        "commands": sorted(results, key=lambda row: row["request_id"]),
        "evidence_sha256": digest,
        "timings": sorted(timings, key=lambda row: row["request_id"]),
        "limits": "Synthetic observations only; no robot control, safety certification, or employer deployment claim.",
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python audit.py COMMANDS.json", file=sys.stderr)
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
