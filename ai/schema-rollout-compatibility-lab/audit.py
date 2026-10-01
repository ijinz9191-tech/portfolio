"""가상 Java 서비스와 관계형 스키마의 순차 배포 호환성을 검사한다."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


class InputError(ValueError):
    """판정에 필요한 입력 계약이 깨졌음을 나타낸다."""


def _object(value: object, fields: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        raise InputError(f"{label}: 필드가 올바르지 않습니다")
    return value


def _names(value: object, label: str) -> set[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise InputError(f"{label}: 비어 있지 않은 문자열 목록이 필요합니다")
    if len(set(value)) != len(value):
        raise InputError(f"{label}: 중복 이름이 있습니다")
    return set(value)


def audit(payload: object) -> dict:
    """혼합 버전 구간과 롤백 대상까지 읽기·쓰기 계약을 검사한다."""
    root = _object(payload, {"schemas", "apps", "stages"}, "입력")
    schemas = root["schemas"]
    apps = root["apps"]
    stages = root["stages"]
    if (
        not isinstance(schemas, dict)
        or not schemas
        or not isinstance(apps, dict)
        or not apps
    ):
        raise InputError("schemas와 apps는 비어 있지 않은 객체여야 합니다")
    if not isinstance(stages, list) or not stages:
        raise InputError("stages는 비어 있지 않은 목록이어야 합니다")

    schema_defs = {}
    for version, raw in schemas.items():
        if not isinstance(version, str) or not version.strip():
            raise InputError("스키마 버전 이름이 올바르지 않습니다")
        row = _object(
            raw, {"columns", "required_on_insert", "defaults"}, f"스키마 {version}"
        )
        columns = _names(row["columns"], "columns")
        required = _names(row["required_on_insert"], "required_on_insert")
        defaults = _names(row["defaults"], "defaults")
        if not columns or not (required | defaults) <= columns:
            raise InputError("스키마의 필수·기본값 열이 실제 열에 속해야 합니다")
        schema_defs[version] = (columns, required - defaults)

    app_defs = {}
    for version, raw in apps.items():
        if not isinstance(version, str) or not version.strip():
            raise InputError("애플리케이션 버전 이름이 올바르지 않습니다")
        row = _object(raw, {"reads", "writes"}, f"애플리케이션 {version}")
        reads = _names(row["reads"], "reads")
        writes = _names(row["writes"], "writes")
        if not reads or not writes:
            raise InputError("애플리케이션은 읽기·쓰기 열을 명시해야 합니다")
        app_defs[version] = (reads, writes)

    findings = []
    stage_names = set()
    compatibility_cache = {}
    for raw in stages:
        row = _object(raw, {"name", "schema", "running_apps", "rollback_app"}, "단계")
        name, schema, rollback = row["name"], row["schema"], row["rollback_app"]
        if not isinstance(name, str) or not name.strip() or name in stage_names:
            raise InputError("단계 이름이 비었거나 중복됐습니다")
        stage_names.add(name)
        if (
            not isinstance(schema, str)
            or not isinstance(rollback, str)
            or schema not in schema_defs
            or rollback not in app_defs
        ):
            raise InputError("정의되지 않은 스키마 또는 롤백 앱 버전입니다")
        running = _names(row["running_apps"], "running_apps")
        if not running or not running <= app_defs.keys():
            raise InputError("운영 앱 목록이 비었거나 정의되지 않은 버전을 포함합니다")
        columns, required = schema_defs[schema]
        for app in sorted(running | {rollback}):
            pair = (schema, app)
            if pair not in compatibility_cache:
                reads, writes = app_defs[app]
                compatibility_cache[pair] = (
                    ("MISSING_READ_COLUMN", sorted(reads - columns)),
                    ("MISSING_WRITE_COLUMN", sorted(writes - columns)),
                    ("REQUIRED_INSERT_COLUMN", sorted(required - writes)),
                )
            for issue, values in compatibility_cache[pair]:
                if values:
                    findings.append(
                        {
                            "stage": name,
                            "app": app,
                            "issue": issue,
                            "columns": sorted(values),
                            "rollback_only": app == rollback and app not in running,
                        }
                    )
    canonical = json.dumps(
        root, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        "decision": "REVIEW_REQUIRED" if findings else "PASS",
        "findings": findings,
        "stages_checked": len(stages),
        "contracts_checked": len(compatibility_cache),
        "evidence_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "limits": "합성 열 계약의 정적 검사입니다. SQL 문법, Oracle·PL/SQL 실행 계획, 데이터 이관, 실제 배포를 검증하지 않습니다.",
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("사용법: python audit.py 입력.json", file=sys.stderr)
        return 2
    try:
        result = audit(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    except (InputError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["decision"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
