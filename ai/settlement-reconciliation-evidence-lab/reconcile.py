"""Offline reconciliation of synthetic merchant postings and settlement lines.

The lab deliberately has no payment gateway, bank, or company integration.
Amounts are integer minor units (KRW won in the sample), never floats.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


class EvidenceError(ValueError):
    pass


def _record(row: object, label: str) -> tuple[str, str, int]:
    if not isinstance(row, dict) or set(row) != {"id", "merchant", "amount_won"}:
        raise EvidenceError(f"{label}: expected id, merchant, amount_won")
    txid, merchant, amount = row["id"], row["merchant"], row["amount_won"]
    if not isinstance(txid, str) or not txid.strip():
        raise EvidenceError(f"{label}: invalid id")
    if not isinstance(merchant, str) or not merchant.strip():
        raise EvidenceError(f"{label}: invalid merchant")
    if type(amount) is not int or amount == 0:
        raise EvidenceError(f"{label}: nonzero integer amount required")
    return txid, merchant, amount


def reconcile(payload: object) -> dict:
    """Match each posting to one settlement line and expose every evidence gap."""
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
            txid, merchant, amount = _record(row, name)
            if txid in target:
                raise EvidenceError(f"duplicate {name} id: {txid}")
            target[txid] = (merchant, amount)
    issues = []
    matched = []
    for txid in sorted(set(left) | set(right)):
        if txid not in left:
            issues.append({"id": txid, "issue": "UNMATCHED_SETTLEMENT"})
        elif txid not in right:
            issues.append({"id": txid, "issue": "MISSING_SETTLEMENT"})
        elif left[txid] != right[txid]:
            issues.append({"id": txid, "issue": "MERCHANT_OR_AMOUNT_MISMATCH",
                           "posting": left[txid], "settlement": right[txid]})
        else:
            matched.append(txid)
    canonical = {
        "postings": [{"id": k, "merchant": v[0], "amount_won": v[1]} for k, v in sorted(left.items())],
        "settlements": [{"id": k, "merchant": v[0], "amount_won": v[1]} for k, v in sorted(right.items())],
    }
    digest = hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()
    return {"decision": "MATCH" if not issues else "REVIEW_REQUIRED",
            "matched_ids": matched, "issues": issues, "evidence_sha256": digest,
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
