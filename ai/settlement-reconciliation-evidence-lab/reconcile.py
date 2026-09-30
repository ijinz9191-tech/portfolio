"""가상의 거래 원장과 정산 명세를 오프라인에서 대조한다.

결제 게이트웨이·은행·회사 시스템과 연결하지 않는다. 금액은 원 단위 정수로만 처리한다.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


class EvidenceError(ValueError):
    pass


def _record(row: object, label: str) -> tuple[str, str, int, str | None]:
    required = {"id", "merchant", "amount_won"}
    allowed = required | ({"reversal_of"} if label == "posting" else set())
    if not isinstance(row, dict) or not required <= set(row) or not set(row) <= allowed:
        raise EvidenceError(f"{label}: expected id, merchant, amount_won")
    txid, merchant, amount = row["id"], row["merchant"], row["amount_won"]
    if not isinstance(txid, str) or not txid.strip():
        raise EvidenceError(f"{label}: invalid id")
    if not isinstance(merchant, str) or not merchant.strip():
        raise EvidenceError(f"{label}: invalid merchant")
    if type(amount) is not int or amount == 0:
        raise EvidenceError(f"{label}: nonzero integer amount required")
    reversal_of = row.get("reversal_of")
    if reversal_of is not None and (not isinstance(reversal_of, str) or not reversal_of.strip()):
        raise EvidenceError(f"{label}: invalid reversal_of")
    return txid, merchant, amount, reversal_of


def reconcile(payload: object) -> dict:
    """거래와 정산 명세를 ID별로 비교하고 확인이 필요한 차이를 보고한다."""
    if not isinstance(payload, dict) or set(payload) != {"postings", "settlements"}:
        raise EvidenceError("postings and settlements lists required")
    postings, settlements = payload["postings"], payload["settlements"]
    if not isinstance(postings, list) or not isinstance(settlements, list):
        raise EvidenceError("postings and settlements must be lists")
    if not postings:
        raise EvidenceError("at least one posting is required")
    left, right = {}, {}
    for name, rows, target in (("posting", postings, left), ("settlement", settlements, right)):
        for row in rows:
            txid, merchant, amount, reversal_of = _record(row, name)
            if txid in target:
                raise EvidenceError(f"duplicate {name} id: {txid}")
            target[txid] = (merchant, amount, reversal_of)
    issues = []
    matched = []
    merchant_totals: dict[str, dict[str, int]] = {}
    for source, records in (("posting_won", left), ("settlement_won", right)):
        for merchant, amount, _ in records.values():
            totals = merchant_totals.setdefault(merchant, {"posting_won": 0, "settlement_won": 0})
            totals[source] += amount
    for txid in sorted(set(left) | set(right)):
        if txid not in left:
            issues.append({"id": txid, "issue": "UNMATCHED_SETTLEMENT"})
        elif txid not in right:
            issues.append({"id": txid, "issue": "MISSING_SETTLEMENT"})
        elif left[txid][:2] != right[txid][:2]:
            issues.append({"id": txid, "issue": "MERCHANT_OR_AMOUNT_MISMATCH",
                           "posting": left[txid][:2], "settlement": right[txid][:2]})
        else:
            matched.append(txid)
    # 환불성 음수 거래가 실제 원거래 한 건과 연결되는지 별도로 확인한다.
    reversals: dict[str, list[str]] = {}
    for txid, (merchant, amount, original_id) in sorted(left.items()):
        if original_id is None:
            continue
        reversals.setdefault(original_id, []).append(txid)
        original = left.get(original_id)
        if original is None or original[0] != merchant or original[1] != -amount or amount >= 0 or original[1] <= 0:
            issues.append({"id": txid, "issue": "INVALID_REVERSAL_LINK", "reversal_of": original_id})
    for original_id, linked_ids in sorted(reversals.items()):
        if len(linked_ids) > 1:
            issues.append({"id": original_id, "issue": "MULTIPLE_REVERSALS", "reversal_ids": sorted(linked_ids)})
    canonical = {
        "postings": [{"id": k, "merchant": v[0], "amount_won": v[1],
                      **({"reversal_of": v[2]} if v[2] is not None else {})} for k, v in sorted(left.items())],
        "settlements": [{"id": k, "merchant": v[0], "amount_won": v[1]} for k, v in sorted(right.items())],
    }
    digest = hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()
    # 건별 불일치가 합계에서 상쇄되더라도 건별 문제는 그대로 남긴다.
    aggregates = [
        {"merchant": merchant, **totals,
         "delta_won": totals["posting_won"] - totals["settlement_won"]}
        for merchant, totals in sorted(merchant_totals.items())
    ]
    return {"decision": "MATCH" if not issues else "REVIEW_REQUIRED",
            "matched_ids": matched, "issues": issues, "evidence_sha256": digest,
            "merchant_totals": aggregates,
            "limits": "Synthetic offline comparison only; no actual money movement or company settlement claim."}


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python reconcile.py sample.json", file=sys.stderr)
        return 2
    try:
        payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        result = reconcile(payload)
    except (EvidenceError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result["decision"] == "MATCH" else 1


if __name__ == "__main__":
    raise SystemExit(main())
