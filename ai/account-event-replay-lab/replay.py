"""가상 계좌 이벤트의 멱등 재생과 잔액 근거를 오프라인에서 검증한다."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


class ReplayError(ValueError):
    """잘못된 이벤트 명세나 충돌을 나타낸다."""


def _integer(value: object, label: str) -> int:
    if type(value) is not int or not -(2**63) <= value <= 2**63 - 1:
        raise ReplayError(f"{label}: 정수가 필요합니다")
    return value


def replay(payload: object) -> dict:
    """버전 순서로 이벤트를 재생하고 중복 전송·누락·예상 잔액을 검사한다."""
    required = {"account", "opening_won", "expected_won", "events"}
    if (
        not isinstance(payload, dict)
        or not required <= set(payload)
        or set(payload) - required - {"checkpoints"}
    ):
        raise ReplayError("account, opening_won, expected_won, events가 필요합니다")
    account = payload["account"]
    if not isinstance(account, str) or not account.strip():
        raise ReplayError("account가 비었습니다")
    opening = _integer(payload["opening_won"], "opening_won")
    expected = _integer(payload["expected_won"], "expected_won")
    if opening < 0 or expected < 0:
        raise ReplayError("음수 시작·예상 잔액은 허용하지 않습니다")
    events = payload["events"]
    if not isinstance(events, list) or not events:
        raise ReplayError("events는 비어 있지 않은 목록이어야 합니다")

    unique: dict[str, tuple[int, int]] = {}
    duplicates = 0
    for row in events:
        if not isinstance(row, dict) or set(row) != {"id", "version", "delta_won"}:
            raise ReplayError("이벤트에는 id, version, delta_won만 필요합니다")
        event_id = row["id"]
        if not isinstance(event_id, str) or not event_id.strip():
            raise ReplayError("이벤트 id가 비었습니다")
        version = _integer(row["version"], "version")
        delta = _integer(row["delta_won"], "delta_won")
        if version < 1 or delta == 0:
            raise ReplayError("version은 양수, delta_won은 0이 아닌 정수여야 합니다")
        value = (version, delta)
        if event_id in unique:
            if unique[event_id] != value:
                raise ReplayError(f"같은 id의 다른 내용: {event_id}")
            duplicates += 1
        else:
            unique[event_id] = value

    by_version: dict[int, tuple[str, int]] = {}
    for event_id, (version, delta) in unique.items():
        if version in by_version:
            raise ReplayError(f"서로 다른 id의 버전 충돌: {version}")
        by_version[version] = (event_id, delta)

    # 중간 스냅샷을 별도 근거로 대조하되, 예전 입력 형식도 그대로 허용한다.
    checkpoints: dict[int, int] = {}
    if "checkpoints" in payload:
        rows = payload["checkpoints"]
        if not isinstance(rows, list):
            raise ReplayError("checkpoints는 목록이어야 합니다")
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"version", "balance_won"}:
                raise ReplayError("체크포인트에는 version, balance_won이 필요합니다")
            version = _integer(row["version"], "checkpoint.version")
            amount = _integer(row["balance_won"], "checkpoint.balance_won")
            if (
                version < 1
                or amount < 0
                or version in checkpoints
                or version not in by_version
            ):
                raise ReplayError("체크포인트 버전·잔액이 잘못됐습니다")
            checkpoints[version] = amount

    balance = opening
    issues: list[dict] = []
    trace: list[dict] = []
    versions = sorted(by_version)
    if any(version != index for index, version in enumerate(versions, 1)):
        issues.append({"kind": "VERSION_GAP", "observed": versions})
    else:
        for version in versions:
            event_id, delta = by_version[version]
            next_balance = balance + delta
            if next_balance > 2**63 - 1:
                issues.append(
                    {"kind": "BALANCE_OVERFLOW", "version": version, "id": event_id}
                )
                break
            if next_balance < 0:
                issues.append(
                    {"kind": "NEGATIVE_BALANCE", "version": version, "id": event_id}
                )
                break
            balance = next_balance
            trace.append({"version": version, "id": event_id, "balance_won": balance})
            if version in checkpoints and checkpoints[version] != balance:
                issues.append(
                    {
                        "kind": "CHECKPOINT_MISMATCH",
                        "version": version,
                        "expected_won": checkpoints[version],
                        "actual_won": balance,
                    }
                )
        if not issues and balance != expected:
            issues.append(
                {
                    "kind": "EXPECTED_MISMATCH",
                    "expected_won": expected,
                    "actual_won": balance,
                }
            )

    canonical = {
        "account": account,
        "opening_won": opening,
        "expected_won": expected,
        "events": [
            {"id": event_id, "version": version, "delta_won": delta}
            for version, (event_id, delta) in sorted(by_version.items())
        ],
    }
    if "checkpoints" in payload:
        canonical["checkpoints"] = [
            {"version": version, "balance_won": amount}
            for version, amount in sorted(checkpoints.items())
        ]
    digest = hashlib.sha256(
        json.dumps(
            canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    return {
        "decision": "CONSISTENT" if not issues else "REVIEW_REQUIRED",
        "balance_won": balance if not issues else None,
        "idempotent_duplicates": duplicates,
        "trace": trace,
        "issues": issues,
        "evidence_sha256": digest,
        "limits": "가상 계좌 이벤트의 오프라인 검사이며 실제 증권 거래나 고객 계좌를 다루지 않습니다.",
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("사용법: python replay.py samples/account.json", file=sys.stderr)
        return 2
    try:
        payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        result = replay(payload)
    except (ReplayError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result["decision"] == "CONSISTENT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
