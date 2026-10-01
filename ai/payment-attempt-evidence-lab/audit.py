"""가상 결제 시도의 재전송과 제공자 응답 근거를 대조한다.

외부 결제 API를 호출하지 않으며 실제 금전 이동을 수행하지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


class EvidenceError(ValueError):
    """입력 형식이 검증 가능한 계약을 벗어났을 때 발생한다."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{label}: 비어 있지 않은 문자열이 필요합니다")
    return value


def _amount(value: object, label: str) -> int:
    if type(value) is not int or not 0 < value <= 2**63 - 1:
        raise EvidenceError(f"{label}: 양의 정수 원 단위 금액이 필요합니다")
    return value


def audit(payload: object) -> dict:
    """요청별 응답과 제공자 관측을 결합해 확정·불명확·충돌을 구분한다."""
    if not isinstance(payload, dict) or set(payload) != {"attempts", "provider_events"}:
        raise EvidenceError("attempts와 provider_events 목록이 필요합니다")
    attempts, events = payload["attempts"], payload["provider_events"]
    if not isinstance(attempts, list) or not attempts or not isinstance(events, list):
        raise EvidenceError("시도는 하나 이상이고 두 필드는 모두 목록이어야 합니다")

    by_key: dict[str, list[dict]] = {}
    seen_attempts: set[tuple[str, int]] = set()
    request_to_key: dict[str, str] = {}
    for row in attempts:
        if not isinstance(row, dict) or set(row) != {
            "request_id",
            "key",
            "merchant",
            "amount_won",
            "attempt_no",
            "response",
        }:
            raise EvidenceError("결제 시도 필드가 올바르지 않습니다")
        request_id = _text(row["request_id"], "request_id")
        key = _text(row["key"], "key")
        merchant = _text(row["merchant"], "merchant")
        amount = _amount(row["amount_won"], "amount_won")
        attempt_no = row["attempt_no"]
        if type(attempt_no) is not int or attempt_no < 1:
            raise EvidenceError("attempt_no는 1 이상의 정수여야 합니다")
        if not isinstance(row["response"], str) or row["response"] not in {
            "ACK",
            "TIMEOUT",
            "DECLINED",
        }:
            raise EvidenceError("response는 ACK, TIMEOUT, DECLINED 중 하나여야 합니다")
        identity = (key, attempt_no)
        if identity in seen_attempts:
            raise EvidenceError("동일 키의 시도 번호가 중복됐습니다")
        seen_attempts.add(identity)
        if request_id in request_to_key and request_to_key[request_id] != key:
            raise EvidenceError("request_id가 다른 멱등 키에 재사용됐습니다")
        request_to_key[request_id] = key
        by_key.setdefault(key, []).append(
            {
                "request_id": request_id,
                "merchant": merchant,
                "amount_won": amount,
                "attempt_no": attempt_no,
                "response": row["response"],
            }
        )

    by_event: dict[str, list[dict]] = {}
    seen_event_ids: set[str] = set()
    for row in events:
        if not isinstance(row, dict) or set(row) != {
            "event_id",
            "key",
            "status",
            "amount_won",
        }:
            raise EvidenceError("제공자 관측 필드가 올바르지 않습니다")
        event_id = _text(row["event_id"], "event_id")
        key = _text(row["key"], "key")
        amount = _amount(row["amount_won"], "amount_won")
        if not isinstance(row["status"], str) or row["status"] not in {
            "CAPTURED",
            "DECLINED",
            "REVERSED",
        }:
            raise EvidenceError(
                "status는 CAPTURED, DECLINED, REVERSED 중 하나여야 합니다"
            )
        if event_id in seen_event_ids:
            raise EvidenceError("provider event_id가 중복됐습니다")
        seen_event_ids.add(event_id)
        by_event.setdefault(key, []).append(
            {"event_id": event_id, "status": row["status"], "amount_won": amount}
        )

    issues: list[dict] = []
    results: list[dict] = []
    for key in sorted(set(by_key) | set(by_event)):
        issue_start = len(issues)
        rows = sorted(by_key.get(key, []), key=lambda r: r["attempt_no"])
        observed = sorted(by_event.get(key, []), key=lambda r: r["event_id"])
        if not rows:
            issues.append({"key": key, "issue": "ORPHAN_PROVIDER_EVENT"})
            continue
        base = rows[0]
        if rows[0]["attempt_no"] != 1 or [r["attempt_no"] for r in rows] != list(
            range(1, len(rows) + 1)
        ):
            issues.append({"key": key, "issue": "ATTEMPT_SEQUENCE_GAP"})
        if any(
            (r["request_id"], r["merchant"], r["amount_won"])
            != (base["request_id"], base["merchant"], base["amount_won"])
            for r in rows[1:]
        ):
            issues.append({"key": key, "issue": "IDEMPOTENCY_KEY_CONFLICT"})
        if any(e["amount_won"] != base["amount_won"] for e in observed):
            issues.append({"key": key, "issue": "PROVIDER_AMOUNT_MISMATCH"})
        captures = [e for e in observed if e["status"] == "CAPTURED"]
        declines = [e for e in observed if e["status"] == "DECLINED"]
        reversals = [e for e in observed if e["status"] == "REVERSED"]
        if len(captures) > 1 or len(declines) > 1 or (captures and declines):
            issues.append({"key": key, "issue": "CONFLICTING_PROVIDER_OUTCOME"})
        if reversals and (len(reversals) != 1 or len(captures) != 1 or declines):
            issues.append({"key": key, "issue": "REVERSAL_EVIDENCE_CONFLICT"})
        if (captures and any(r["response"] == "DECLINED" for r in rows)) or (
            declines and not captures and any(r["response"] == "ACK" for r in rows)
        ):
            issues.append({"key": key, "issue": "RESPONSE_PROVIDER_CONFLICT"})
        if not observed:
            issues.append({"key": key, "issue": "PROVIDER_OUTCOME_UNKNOWN"})
        status = (
            "REVERSED"
            if len(captures) == 1 and len(reversals) == 1 and not declines
            else "CAPTURED"
            if len(captures) == 1 and not declines and not reversals
            else "DECLINED"
            if len(declines) == 1 and not captures and not reversals
            else "UNKNOWN"
        )
        # 접근 권한은 이 정적 판정을 근거로 운영 시스템이 별도로 결정한다.
        entitlement_gate = (
            "ELIGIBLE"
            if status == "CAPTURED" and len(issues) == issue_start
            else "NOT_ELIGIBLE"
            if status in {"DECLINED", "REVERSED"} and len(issues) == issue_start
            else "REVIEW"
        )
        results.append(
            {
                "key": key,
                "status": status,
                "attempts": len(rows),
                "provider_event_ids": [e["event_id"] for e in observed],
                "entitlement_gate": entitlement_gate,
            }
        )

    canonical = {
        "attempts": [
            dict(key=k, **r)
            for k in sorted(by_key)
            for r in sorted(by_key[k], key=lambda v: v["attempt_no"])
        ],
        "provider_events": [
            dict(key=k, **r)
            for k in sorted(by_event)
            for r in sorted(by_event[k], key=lambda v: v["event_id"])
        ],
    }
    digest = hashlib.sha256(
        json.dumps(
            canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    return {
        "decision": "PASS" if not issues else "REVIEW_REQUIRED",
        "results": results,
        "issues": issues,
        "evidence_sha256": digest,
        "limits": "가상 오프라인 근거 대조입니다. 실제 결제 확정·금전 이동·구독 접근권 부여를 수행하거나 증명하지 않습니다.",
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("사용법: python audit.py sample.json", file=sys.stderr)
        return 2
    try:
        result = audit(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    except (EvidenceError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result["decision"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
