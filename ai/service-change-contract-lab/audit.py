"""가상 서비스 API 변경의 이용자 영향과 검토 근거를 검사합니다."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


class ContractError(ValueError):
    pass


def _label(value: object, name: str, limit: int = 80) -> str:
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit or value != value.strip():
        raise ContractError(f"{name} must be a bounded nonblank string")
    return value


def _fields(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) > 40 or any(
        not isinstance(item, str) or not item.strip() or len(item) > 80 for item in value
    ) or len(set(value)) != len(value):
        raise ContractError("fields must be a unique bounded list")
    return sorted(value)


def _routes(rows: object, name: str, minimum: int) -> dict[str, dict]:
    if not isinstance(rows, list) or not minimum <= len(rows) <= 100:
        raise ContractError(f"{name} must contain {minimum} to 100 routes")
    result: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"route", "auth", "fields"}:
            raise ContractError("route needs route, auth and fields")
        route = _label(row["route"], "route", 120)
        if not route.startswith(("GET /", "POST /", "PUT /", "PATCH /", "DELETE /")):
            raise ContractError("route needs HTTP method and path")
        if not isinstance(row["auth"], str) or row["auth"] not in {"public", "authenticated"} or route in result:
            raise ContractError("auth must be valid and routes unique")
        result[route] = {"route": route, "auth": row["auth"], "fields": _fields(row["fields"])}
    return result


def analyze(document: dict) -> dict:
    if not isinstance(document, dict) or set(document) != {
        "change_id", "before", "after", "consumers", "rollback_plan"
    }:
        raise ContractError("change_id, before, after, consumers and rollback_plan are required")
    change_id = _label(document["change_id"], "change_id")
    before = _routes(document["before"], "before", 1)
    after = _routes(document["after"], "after", 0)
    rollback = document["rollback_plan"]
    if not isinstance(rollback, str) or len(rollback) > 500:
        raise ContractError("rollback_plan must be a bounded string")
    rows = document["consumers"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
        raise ContractError("1 to 100 consumers are required")
    consumers: dict[str, dict] = {}
    for row in rows:
        required = {"id", "route", "fields", "owner", "acknowledged"}
        if not isinstance(row, dict) or not required <= set(row) or set(row) - required - {"auth_capable"}:
            raise ContractError("consumer needs id, route, fields, owner and acknowledged")
        ident = _label(row["id"], "consumer id")
        route = _label(row["route"], "consumer route", 120)
        fields = _fields(row["fields"])
        if ident in consumers or route not in before or not set(fields) <= set(before[route]["fields"]):
            raise ContractError("duplicate consumer or invalid baseline dependency")
        if not isinstance(row["acknowledged"], bool):
            raise ContractError("acknowledged must be boolean")
        if "auth_capable" in row and not isinstance(row["auth_capable"], bool):
            raise ContractError("auth_capable must be boolean")
        consumers[ident] = {"id": ident, "route": route, "fields": fields,
                            "owner": _label(row["owner"], "owner"),
                            "acknowledged": row["acknowledged"]}
        if "auth_capable" in row:
            consumers[ident]["auth_capable"] = row["auth_capable"]

    security_downgrades = sorted(route for route in before if route in after and
                                 before[route]["auth"] == "authenticated" and after[route]["auth"] == "public")
    impacts = []
    for ident in sorted(consumers):
        consumer = consumers[ident]
        target = after.get(consumer["route"])
        missing = consumer["fields"] if target is None else sorted(set(consumer["fields"]) - set(target["fields"]))
        auth_required = (target is not None and before[consumer["route"]]["auth"] == "public"
                         and target["auth"] == "authenticated"
                         and not consumer.get("auth_capable", False))
        if target is None or missing or auth_required:
            impacts.append({"consumer": ident, "owner": consumer["owner"],
                            "route": consumer["route"], "missing_fields": missing,
                            "route_removed": target is None,
                            "auth_required": auth_required,
                            "acknowledged": consumer["acknowledged"]})
    uncovered_breaking = sorted(route for route, old in before.items()
                                if (route not in after or set(old["fields"]) - set(after[route]["fields"])
                                    or old["auth"] == "public" and after[route]["auth"] == "authenticated")
                                and not any(item["route"] == route for item in consumers.values()))
    if security_downgrades or (impacts and (not rollback.strip() or any(not item["acknowledged"] for item in impacts))):
        decision = "BLOCK"
    elif impacts or uncovered_breaking:
        decision = "REVIEW"
    else:
        decision = "PASS"
    canonical = {"change_id": change_id, "before": [before[key] for key in sorted(before)],
                 "after": [after[key] for key in sorted(after)],
                 "consumers": [consumers[key] for key in sorted(consumers)], "rollback_plan": rollback}
    digest = hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":")).encode()).hexdigest()
    return {"change_id": change_id, "decision": decision, "consumer_impacts": impacts,
            "security_downgrades": security_downgrades,
            "uncovered_breaking_routes": uncovered_breaking,
            "evidence_sha256": digest,
            "limits": "가상 서비스 계약 검토용입니다. PASS는 실제 배포 승인이나 미등록 이용자의 안전을 보증하지 않습니다."}


def main() -> int:
    if len(sys.argv) != 2:
        print("사용법: python audit.py 변경자료.json", file=sys.stderr)
        return 2
    try:
        document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        result = analyze(document)
    except (OSError, json.JSONDecodeError, ContractError) as exc:
        print(f"거부: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
