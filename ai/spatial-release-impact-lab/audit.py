"""가상 지도 데이터 배포에서 경로 영향과 담당자 확인 근거를 검사한다."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


class ReleaseError(ValueError):
    """배포 입력의 구조나 참조가 올바르지 않다."""


def _name(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 80:
        raise ReleaseError(f"{label} must be a bounded nonempty string")
    return value


def _snapshot(value: object, label: str) -> dict:
    if not isinstance(value, dict) or set(value) != {"version", "segments", "routes"}:
        raise ReleaseError(f"{label} snapshot fields are invalid")
    version = _name(value["version"], "version")
    raw_segments, raw_routes = value["segments"], value["routes"]
    if (
        not isinstance(raw_segments, list)
        or not 1 <= len(raw_segments) <= 1000
        or not isinstance(raw_routes, list)
        or not 1 <= len(raw_routes) <= 1000
    ):
        raise ReleaseError(f"{label} collections must contain 1 to 1000 entries")
    segments = {}
    for row in raw_segments:
        if not isinstance(row, dict) or set(row) != {"id", "geometry_revision"}:
            raise ReleaseError("segment fields are invalid")
        segment_id = _name(row["id"], "segment id")
        revision = _name(row["geometry_revision"], "geometry revision")
        if segment_id in segments:
            raise ReleaseError("duplicate segment id")
        segments[segment_id] = revision
    routes = {}
    for row in raw_routes:
        if not isinstance(row, dict) or set(row) != {"id", "segment_ids"}:
            raise ReleaseError("route fields are invalid")
        route_id = _name(row["id"], "route id")
        path = row["segment_ids"]
        if (
            route_id in routes
            or not isinstance(path, list)
            or not 1 <= len(path) <= 1000
        ):
            raise ReleaseError("duplicate route id or empty route")
        if any(
            not isinstance(segment, str) or segment not in segments for segment in path
        ):
            raise ReleaseError("route references an unknown segment")
        routes[route_id] = path
    return {"version": version, "segments": segments, "routes": routes}


def audit(document: dict) -> dict:
    """변경 세그먼트와 영향 경로를 산출하고 확인 누락을 차단한다."""
    if not isinstance(document, dict) or set(document) != {
        "baseline",
        "candidate",
        "acknowledgements",
    }:
        raise ReleaseError("baseline, candidate and acknowledgements are required")
    baseline = _snapshot(document["baseline"], "baseline")
    candidate = _snapshot(document["candidate"], "candidate")
    if baseline["version"] == candidate["version"]:
        raise ReleaseError("release versions must differ")
    retired = set(baseline["routes"]) - set(candidate["routes"])
    if retired:
        raise ReleaseError("route retirement requires a separate reviewed workflow")
    before, after = baseline["segments"], candidate["segments"]
    changed = {
        segment
        for segment in set(before) | set(after)
        if before.get(segment) != after.get(segment)
    }
    impacted = set(candidate["routes"]) - set(baseline["routes"])
    reverse = {}
    # 변경 세그먼트의 경로 역색인은 이전·새 명세를 모두 포함해야 삭제도 추적한다.
    for snapshot in (baseline, candidate):
        for route_id, path in snapshot["routes"].items():
            for segment in path:
                reverse.setdefault(segment, set()).add(route_id)
    for segment in changed:
        impacted.update(reverse.get(segment, ()))
    for route_id, old_path in baseline["routes"].items():
        new_path = candidate["routes"][route_id]
        if old_path != new_path:
            impacted.add(route_id)
    acknowledgements = document["acknowledgements"]
    if not isinstance(acknowledgements, list) or len(acknowledgements) > 1000:
        raise ReleaseError("acknowledgements must be a bounded list")
    accepted = set()
    for row in acknowledgements:
        if not isinstance(row, dict) or set(row) != {
            "route_id",
            "reviewer",
            "rollback_version",
        }:
            raise ReleaseError("acknowledgement fields are invalid")
        route_id = _name(row["route_id"], "route id")
        _name(row["reviewer"], "reviewer")
        if route_id not in impacted or route_id in accepted:
            raise ReleaseError("unexpected or duplicate acknowledgement")
        if row["rollback_version"] != baseline["version"]:
            raise ReleaseError("rollback version does not match baseline")
        accepted.add(route_id)
    missing = sorted(impacted - accepted)
    canonical = {
        "baseline": {
            "version": baseline["version"],
            "segments": sorted(
                document["baseline"]["segments"], key=lambda row: row["id"]
            ),
            "routes": sorted(document["baseline"]["routes"], key=lambda row: row["id"]),
        },
        "candidate": {
            "version": candidate["version"],
            "segments": sorted(
                document["candidate"]["segments"], key=lambda row: row["id"]
            ),
            "routes": sorted(
                document["candidate"]["routes"], key=lambda row: row["id"]
            ),
        },
        "acknowledgements": sorted(acknowledgements, key=lambda row: row["route_id"]),
    }
    digest = hashlib.sha256(
        json.dumps(
            canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    return {
        "decision": "BLOCKED" if missing else "READY_FOR_HUMAN_REVIEW",
        "changed_segments": sorted(changed),
        "impacted_routes": sorted(impacted),
        "missing_acknowledgements": missing,
        "evidence_sha256": digest,
        "limits": "가상 릴리스 명세의 참조와 검토 기록만 확인하며 실제 지도 정확도나 배포 허가를 증명하지 않습니다.",
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("사용법: python audit.py 변경명세.json", file=sys.stderr)
        return 2
    try:
        document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        result = audit(document)
    except (OSError, json.JSONDecodeError, ReleaseError) as exc:
        print(f"입력 거부: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["decision"] != "BLOCKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
