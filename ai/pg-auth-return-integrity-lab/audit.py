"""가상 PG 인증 귀환과 서버 확인을 분리해 대조한다."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


class InputError(ValueError):
    """검사 가능한 입력 계약에 어긋난 자료를 나타낸다."""


def _required_text(row: dict, field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{field}: 비어 있지 않은 문자열이 필요합니다")
    return value


def _money(row: dict) -> int:
    value = row.get("amount_won")
    if type(value) is not int or value <= 0:
        raise InputError("amount_won: 양의 정수 원 단위 금액이 필요합니다")
    return value


def audit(payload: object) -> dict:
    """브라우저 귀환은 신호로만 보고 서버 관측을 결합한다."""
    if not isinstance(payload, dict) or set(payload) != {"sessions", "returns", "confirmations"}:
        raise InputError("sessions, returns, confirmations 세 목록이 필요합니다")
    sessions, returns, confirmations = (payload[name] for name in ("sessions", "returns", "confirmations"))
    if not isinstance(sessions, list) or not sessions or not isinstance(returns, list) or not isinstance(confirmations, list):
        raise InputError("세 값은 목록이며 sessions는 하나 이상이어야 합니다")

    by_session: dict[str, dict] = {}
    order_ids: set[str] = set()
    for row in sessions:
        if not isinstance(row, dict) or set(row) != {"session_id", "order_id", "merchant", "amount_won", "nonce_sha256"}:
            raise InputError("세션 필드가 올바르지 않습니다")
        session_id, order_id = _required_text(row, "session_id"), _required_text(row, "order_id")
        _required_text(row, "merchant")
        _money(row)
        digest = _required_text(row, "nonce_sha256")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise InputError("nonce_sha256은 소문자 SHA-256 64자리여야 합니다")
        if session_id in by_session or order_id in order_ids:
            raise InputError("세션 또는 주문 ID가 중복됐습니다")
        by_session[session_id] = row
        order_ids.add(order_id)

    by_return: dict[str, list[dict]] = {}
    return_ids: set[str] = set()
    for row in returns:
        if not isinstance(row, dict) or set(row) != {"return_id", "session_id", "order_id", "nonce", "result"}:
            raise InputError("귀환 필드가 올바르지 않습니다")
        return_id, session_id = _required_text(row, "return_id"), _required_text(row, "session_id")
        _required_text(row, "order_id")
        _required_text(row, "nonce")
        if not isinstance(row["result"], str) or row["result"] not in {"SUCCESS", "FAILURE"}:
            raise InputError("result는 SUCCESS 또는 FAILURE여야 합니다")
        if return_id in return_ids:
            raise InputError("return_id가 중복됐습니다")
        return_ids.add(return_id)
        by_return.setdefault(session_id, []).append(row)

    by_confirm: dict[str, list[dict]] = {}
    transaction_ids: set[str] = set()
    for row in confirmations:
        if not isinstance(row, dict) or set(row) != {"transaction_id", "session_id", "order_id", "merchant", "amount_won", "status"}:
            raise InputError("서버 확인 필드가 올바르지 않습니다")
        transaction_id, session_id = _required_text(row, "transaction_id"), _required_text(row, "session_id")
        _required_text(row, "order_id")
        _required_text(row, "merchant")
        _money(row)
        if not isinstance(row["status"], str) or row["status"] not in {"AUTHORIZED", "REJECTED"}:
            raise InputError("status는 AUTHORIZED 또는 REJECTED여야 합니다")
        if transaction_id in transaction_ids:
            raise InputError("transaction_id가 중복됐습니다")
        transaction_ids.add(transaction_id)
        by_confirm.setdefault(session_id, []).append(row)

    findings: list[dict] = []
    results: list[dict] = []
    for session_id, session in sorted(by_session.items()):
        local_issues: set[str] = set()
        observed_returns = by_return.get(session_id, [])
        observed_confirmations = by_confirm.get(session_id, [])
        if len(observed_returns) != 1:
            local_issues.add("RETURN_COUNT_MISMATCH")
        if len(observed_confirmations) != 1:
            local_issues.add("CONFIRMATION_COUNT_MISMATCH")
        for row in observed_returns:
            if row["order_id"] != session["order_id"]:
                local_issues.add("RETURN_ORDER_MISMATCH")
            if hashlib.sha256(row["nonce"].encode()).hexdigest() != session["nonce_sha256"]:
                local_issues.add("RETURN_NONCE_MISMATCH")
        for row in observed_confirmations:
            if (row["order_id"], row["merchant"], row["amount_won"]) != (
                session["order_id"], session["merchant"], session["amount_won"]
            ):
                local_issues.add("SERVER_DETAILS_MISMATCH")
        browser_success = len(observed_returns) == 1 and observed_returns[0]["result"] == "SUCCESS"
        server_authorized = len(observed_confirmations) == 1 and observed_confirmations[0]["status"] == "AUTHORIZED"
        if browser_success != server_authorized and len(observed_returns) == 1 and len(observed_confirmations) == 1:
            local_issues.add("RETURN_SERVER_DISAGREEMENT")
        if local_issues:
            decision = "REVIEW"
        elif browser_success and server_authorized:
            decision = "AUTHORIZATION_CANDIDATE"
        else:
            decision = "REJECTED"
        results.append({"session_id": session_id, "order_id": session["order_id"], "decision": decision})
        findings.extend({"session_id": session_id, "issue": issue} for issue in sorted(local_issues))

    for session_id in sorted((set(by_return) | set(by_confirm)) - set(by_session)):
        findings.append({"session_id": session_id, "issue": "UNKNOWN_SESSION"})
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {"decision": "REVIEW_REQUIRED" if findings else "PASS", "results": results,
            "findings": findings, "evidence_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
            "limits": "가상 정적 대조이며 서명 검증, 결제 승인 실행, 금전 이동, 운영 PG 연동을 수행하지 않습니다."}


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
