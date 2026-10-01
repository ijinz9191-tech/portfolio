"""가상 결제·구독 접근권·제휴사 응답의 정합성을 오프라인에서 검사한다."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path


class InputError(ValueError):
    """검증할 수 없는 입력 계약을 받았을 때 발생한다."""


def _row(value: object, fields: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        raise InputError(f"{label}: 필드 계약이 올바르지 않습니다")
    return value


def _id(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 120:
        raise InputError(f"{label}: 1~120자 문자열이 필요합니다")
    return value


def _period(value: object) -> str:
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", value)
        or value.startswith("0000")
    ):
        raise InputError("period: YYYY-MM 형식이 필요합니다")
    return value


def _choice(value: object, allowed: set[str], label: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise InputError(f"{label}: 허용된 상태가 아닙니다")
    return value


def reconcile(payload: object) -> dict:
    """접근 허용 근거와 제휴 확인의 누락·상충을 구독 기간별로 보고한다."""
    _row(payload, {"payments", "entitlements", "partner_acks"}, "입력")
    for name in ("payments", "entitlements", "partner_acks"):
        if not isinstance(payload[name], list):
            raise InputError(f"{name}: 목록이 필요합니다")

    groups: dict[tuple[str, str], dict[str, list[dict]]] = {}
    payment_ids: set[str] = set()
    payment_owners: dict[str, tuple[str, str]] = {}
    for source, fields, states in (
        (
            "payments",
            {"payment_id", "subscription_id", "period", "status", "amount_won"},
            {"CAPTURED", "DECLINED"},
        ),
        (
            "entitlements",
            {"payment_id", "subscription_id", "period", "status"},
            {"ACTIVE", "INACTIVE"},
        ),
        (
            "partner_acks",
            {"payment_id", "subscription_id", "period", "status"},
            {"CONFIRMED", "FAILED"},
        ),
    ):
        for item in payload[source]:
            row = _row(item, fields, source)
            payment_id = _id(row["payment_id"], "payment_id")
            subscription_id = _id(row["subscription_id"], "subscription_id")
            period = _period(row["period"])
            _choice(row["status"], states, "status")
            if source == "payments":
                if payment_id in payment_ids:
                    raise InputError("payment_id가 중복됐습니다")
                payment_ids.add(payment_id)
                payment_owners[payment_id] = (subscription_id, period)
                if type(row["amount_won"]) is not int or row["amount_won"] <= 0:
                    raise InputError("amount_won: 양의 정수 원 단위 금액이 필요합니다")
            group = groups.setdefault(
                (subscription_id, period),
                {"payments": [], "entitlements": [], "partner_acks": []},
            )
            group[source].append(row)

    issues: list[dict] = []
    results: list[dict] = []
    for (subscription_id, period), group in sorted(groups.items()):
        start = len(issues)

        def issue(code: str) -> None:
            issues.append(
                {"subscription_id": subscription_id, "period": period, "issue": code}
            )

        for row in group["entitlements"] + group["partner_acks"]:
            if row["payment_id"] in payment_owners and payment_owners[
                row["payment_id"]
            ] != (subscription_id, period):
                issue("CROSS_SUBSCRIPTION_PAYMENT_REFERENCE")
                break
        payments = group["payments"]
        access = group["entitlements"]
        acks = group["partner_acks"]
        if len(payments) != 1:
            issue("PAYMENT_MISSING" if not payments else "MULTIPLE_PAYMENTS")
        if len(access) > 1:
            issue("MULTIPLE_ENTITLEMENTS")
        if len(acks) > 1:
            issue("MULTIPLE_PARTNER_ACKS")
        payment = payments[0] if len(payments) == 1 else None
        expected_id = payment["payment_id"] if payment else None
        if expected_id and any(
            row["payment_id"] != expected_id for row in access + acks
        ):
            issue("PAYMENT_REFERENCE_MISMATCH")
        if payment and payment["status"] == "CAPTURED":
            if not access or access[0]["status"] != "ACTIVE":
                issue("PAID_ACCESS_MISSING")
            if not acks:
                issue("PARTNER_ACK_MISSING")
            elif acks[0]["status"] != "CONFIRMED":
                issue("PARTNER_ACK_FAILED")
        if payment and payment["status"] == "DECLINED":
            if any(row["status"] == "ACTIVE" for row in access):
                issue("ACCESS_WITHOUT_PAYMENT")
            if any(row["status"] == "CONFIRMED" for row in acks):
                issue("PARTNER_CONFIRMED_DECLINE")
        if not payment and any(row["status"] == "ACTIVE" for row in access):
            issue("ACCESS_WITHOUT_PAYMENT")
        # 결제·권한·제휴 확인이 모두 일치한 경우에만 접근 허용 후보로 분류한다.
        eligible = bool(
            payment
            and payment["status"] == "CAPTURED"
            and len(access) == len(acks) == 1
            and len(issues) == start
        )
        results.append(
            {
                "subscription_id": subscription_id,
                "period": period,
                "access_gate": "ELIGIBLE"
                if eligible
                else "REVIEW"
                if len(issues) > start
                else "NOT_ELIGIBLE",
                "payment_id": expected_id,
            }
        )

    canonical = {
        name: sorted(
            payload[name],
            key=lambda r: json.dumps(r, sort_keys=True, ensure_ascii=False),
        )
        for name in ("payments", "entitlements", "partner_acks")
    }
    digest = hashlib.sha256(
        json.dumps(
            canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    return {
        "decision": "PASS" if not issues else "REVIEW_REQUIRED",
        "results": results,
        "issues": issues,
        "evidence_sha256": digest,
        "limits": "합성 입력의 정적 대조입니다. 실제 결제·계정 접근권 부여·제휴사 통신을 수행하지 않습니다.",
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("사용법: python reconcile.py samples/confirmed.json", file=sys.stderr)
        return 2
    try:
        result = reconcile(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    except (InputError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result["decision"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
