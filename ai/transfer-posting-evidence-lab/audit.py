"""가상 계좌 이체의 차변·대변 기장 완결성과 잔액을 검사한다."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


class AuditError(ValueError):
    """입력 명세가 불명확하거나 서로 충돌한다."""


def _won(value: object, name: str, *, positive: bool = False) -> int:
    if type(value) is not int or (value <= 0 if positive else value < 0):
        raise AuditError(f"{name}: 유효한 정수 원화 금액이 필요합니다")
    return value


def _id(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise AuditError(f"{name}: 공백 없는 ID가 필요합니다")
    return value


def audit(payload: object) -> dict:
    """이체 명령과 관측된 두 기장을 대조하고 계좌별 잔액을 재생한다."""
    if not isinstance(payload, dict) or set(payload) != {"accounts", "transfers", "postings"}:
        raise AuditError("accounts, transfers, postings가 필요합니다")
    if not isinstance(payload["accounts"], list) or len(payload["accounts"]) < 2:
        raise AuditError("두 개 이상의 계좌가 필요합니다")
    accounts: dict[str, dict[str, int]] = {}
    for row in payload["accounts"]:
        if not isinstance(row, dict) or set(row) != {"id", "opening_won", "expected_won"}:
            raise AuditError("계좌에는 id, opening_won, expected_won이 필요합니다")
        name = _id(row["id"], "account.id")
        if name in accounts:
            raise AuditError(f"중복 계좌: {name}")
        accounts[name] = {"opening_won": _won(row["opening_won"], "opening_won"),
                          "expected_won": _won(row["expected_won"], "expected_won")}

    if not isinstance(payload["transfers"], list) or not payload["transfers"]:
        raise AuditError("이체 목록이 비었습니다")
    transfers: dict[str, tuple[int, str, str, int]] = {}
    retries = 0
    for row in payload["transfers"]:
        if not isinstance(row, dict) or set(row) != {"id", "sequence", "from", "to", "amount_won"}:
            raise AuditError("이체 명세에 id, sequence, from, to, amount_won이 필요합니다")
        key = _id(row["id"], "transfer.id")
        sequence = _won(row["sequence"], "sequence", positive=True)
        source = _id(row["from"], "from")
        target = _id(row["to"], "to")
        amount = _won(row["amount_won"], "amount_won", positive=True)
        if source not in accounts or target not in accounts or source == target:
            raise AuditError(f"이체 계좌 참조가 잘못됐습니다: {key}")
        entry = (sequence, source, target, amount)
        if key in transfers:
            if transfers[key] != entry:
                raise AuditError(f"같은 이체 ID의 다른 내용: {key}")
            retries += 1
        else:
            transfers[key] = entry
    sequences = [entry[0] for entry in transfers.values()]
    if sorted(sequences) != list(range(1, len(transfers) + 1)):
        raise AuditError("이체 sequence는 1부터 연속이며 중복이 없어야 합니다")

    if not isinstance(payload["postings"], list):
        raise AuditError("postings는 목록이어야 합니다")
    postings: dict[str, set[tuple[str, int]]] = {key: set() for key in transfers}
    posting_retries = 0
    for row in payload["postings"]:
        if not isinstance(row, dict) or set(row) != {"transfer_id", "account", "delta_won"}:
            raise AuditError("기장에는 transfer_id, account, delta_won이 필요합니다")
        key = _id(row["transfer_id"], "posting.transfer_id")
        account = _id(row["account"], "posting.account")
        delta = row["delta_won"]
        if key not in transfers or account not in accounts or type(delta) is not int or delta == 0:
            raise AuditError("미등록 이체·계좌 또는 잘못된 기장 금액입니다")
        posting = (account, delta)
        if posting in postings[key]:
            posting_retries += 1
        else:
            postings[key].add(posting)

    balances = {name: values["opening_won"] for name, values in accounts.items()}
    issues: list[dict] = []
    trace: list[dict] = []
    blocked_by: str | None = None
    for key, (sequence, source, target, amount) in sorted(transfers.items(), key=lambda item: item[1][0]):
        if blocked_by is not None:
            issues.append({"kind": "REPLAY_BLOCKED", "transfer_id": key,
                           "blocked_by": blocked_by})
            continue
        expected = {(source, -amount), (target, amount)}
        observed = postings[key]
        if observed != expected:
            issues.append({"kind": "POSTING_INCOMPLETE", "transfer_id": key,
                           "missing": sorted([{"account": a, "delta_won": d} for a, d in expected - observed],
                                             key=lambda item: item["account"]),
                           "unexpected": sorted([{"account": a, "delta_won": d} for a, d in observed - expected],
                                                key=lambda item: item["account"])})
            blocked_by = key
            continue
        if balances[source] < amount:
            issues.append({"kind": "OVERDRAFT", "transfer_id": key, "account": source})
            blocked_by = key
            continue
        balances[source] -= amount
        balances[target] += amount
        trace.append({"transfer_id": key, "sequence": sequence,
                      "balances_won": {source: balances[source], target: balances[target]}})
    if not issues:
        for name, values in sorted(accounts.items()):
            if balances[name] != values["expected_won"]:
                issues.append({"kind": "EXPECTED_MISMATCH", "account": name,
                               "expected_won": values["expected_won"], "actual_won": balances[name]})

    canonical = {"accounts": [{"id": name, **values} for name, values in sorted(accounts.items())],
                 "transfers": [{"id": key, "sequence": sequence, "from": source,
                                "to": target, "amount_won": amount}
                               for key, (sequence, source, target, amount) in sorted(transfers.items())],
                 "postings": [{"transfer_id": key, "account": account, "delta_won": delta}
                              for key, rows in sorted(postings.items()) for account, delta in sorted(rows)]}
    digest = hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"decision": "CONSISTENT" if not issues else "REVIEW_REQUIRED",
            "balances_won": balances if not issues else None, "transfer_retries": retries,
            "posting_retries": posting_retries, "trace": trace, "issues": issues,
            "evidence_sha256": digest,
            "limits": "가상 원화 이체 기장 검사이며 실제 금융 거래나 고객 계좌를 처리하지 않습니다."}


def main() -> int:
    if len(sys.argv) != 2:
        print("사용법: python audit.py samples/transfer.json", file=sys.stderr)
        return 2
    try:
        payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        result = audit(payload)
    except (AuditError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result["decision"] == "CONSISTENT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
