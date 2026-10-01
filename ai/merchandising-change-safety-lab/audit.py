"""가상 상품 변경안의 버전·가격·재고 안전 조건을 점검합니다."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


class ChangeError(ValueError):
    """입력 계약이 모호하거나 잘못된 경우에 사용합니다."""


def _text(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 80
        or value != value.strip()
    ):
        raise ChangeError(f"{name}: 비어 있거나 너무 긴 문자열")
    return value


def _number(value: object, name: str, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= 1_000_000_000:
        raise ChangeError(f"{name}: 유효하지 않은 정수")
    return value


def _product(row: object, *, baseline: bool) -> dict:
    required = {"sku", "version", "cost", "price", "discount", "stock"}
    if not isinstance(row, dict) or set(row) != required:
        raise ChangeError(
            "상품에는 sku, version, cost, price, discount, stock이 필요합니다"
        )
    product = {
        "sku": _text(row["sku"], "sku"),
        "version": _number(row["version"], "version", 1 if baseline else 0),
        "cost": _number(row["cost"], "cost"),
        "price": _number(row["price"], "price", 1),
        "discount": _number(row["discount"], "discount"),
        "stock": _number(row["stock"], "stock"),
    }
    return product


def _unique(rows: object, name: str) -> dict[str, dict]:
    if not isinstance(rows, list) or len(rows) > 500:
        raise ChangeError(f"{name}: 500개 이하 목록이어야 합니다")
    result = {}
    for row in rows:
        product = _product(row, baseline=name == "현재 상품")
        if product["sku"] in result:
            raise ChangeError(f"{name}: 중복 SKU")
        result[product["sku"]] = product
    return result


def analyze(document: object) -> dict:
    """안전 위반은 차단하고 운영 검토가 필요한 변경을 분리합니다."""
    if not isinstance(document, dict) or set(document) != {
        "change_id",
        "current",
        "proposed",
        "removed",
    }:
        raise ChangeError("change_id, current, proposed, removed가 필요합니다")
    change_id = _text(document["change_id"], "change_id")
    current = _unique(document["current"], "현재 상품")
    proposed = _unique(document["proposed"], "변경 상품")
    removed_rows = document["removed"]
    if not isinstance(removed_rows, list) or len(removed_rows) > 500:
        raise ChangeError("removed: 500개 이하 목록이어야 합니다")
    removed = {}
    for row in removed_rows:
        if not isinstance(row, dict) or set(row) != {"sku", "expected_version"}:
            raise ChangeError("삭제에는 sku와 expected_version이 필요합니다")
        sku = _text(row["sku"], "삭제 SKU")
        if sku in removed or sku in proposed:
            raise ChangeError("같은 SKU를 중복 변경할 수 없습니다")
        removed[sku] = _number(row["expected_version"], "expected_version", 1)
    if not proposed and not removed:
        raise ChangeError("변경 항목이 없습니다")

    blocking = []
    review = []
    impacts = []
    inventory_delta_won = 0
    stock_delta = 0
    for sku, new in sorted(proposed.items()):
        old = current.get(sku)
        if old is None and new["version"] != 0:
            blocking.append({"sku": sku, "reason": "새 상품 버전 불일치"})
        if old is not None and new["version"] != old["version"]:
            blocking.append({"sku": sku, "reason": "기준 버전 불일치"})
        effective = new["price"] - new["discount"]
        if effective < new["cost"] or effective <= 0:
            blocking.append({"sku": sku, "reason": "할인 후 판매가가 원가 이하"})
        if old is not None:
            old_effective = old["price"] - old["discount"]
            # 기존보다 할인 후 가격이 20% 넘게 하락하면 운영자가 확인합니다.
            if old_effective > 0 and effective * 5 < old_effective * 4:
                review.append({"sku": sku, "reason": "판매가 20% 초과 하락"})
        else:
            old_effective = None
        inventory_delta_won += effective * new["stock"] - (
            old_effective * old["stock"] if old else 0
        )
        stock_delta += new["stock"] - (old["stock"] if old else 0)
        impacts.append(
            {
                "sku": sku,
                "action": "update" if old else "create",
                "before_effective_price": old_effective,
                "after_effective_price": effective,
                "before_stock": old["stock"] if old else None,
                "after_stock": new["stock"],
            }
        )
    for sku, expected_version in sorted(removed.items()):
        old = current.get(sku)
        if old is None or old["version"] != expected_version:
            blocking.append({"sku": sku, "reason": "삭제 기준 버전 불일치"})
            continue
        if old["stock"] > 0:
            blocking.append({"sku": sku, "reason": "잔여 재고가 있는 상품 삭제"})
        inventory_delta_won -= (old["price"] - old["discount"]) * old["stock"]
        stock_delta -= old["stock"]
        impacts.append(
            {
                "sku": sku,
                "action": "remove",
                "before_effective_price": old["price"] - old["discount"],
                "after_effective_price": None,
                "before_stock": old["stock"],
                "after_stock": None,
            }
        )
    canonical = {
        "change_id": change_id,
        "current": [current[key] for key in sorted(current)],
        "proposed": [proposed[key] for key in sorted(proposed)],
        "removed": [
            {"sku": key, "expected_version": removed[key]} for key in sorted(removed)
        ],
    }
    digest = hashlib.sha256(
        json.dumps(
            canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    decision = "BLOCK" if blocking else "REVIEW" if review else "PASS"
    return {
        "change_id": change_id,
        "decision": decision,
        "blocking": blocking,
        "review": review,
        "impacts": impacts,
        "inventory_delta_won": inventory_delta_won,
        "stock_delta": stock_delta,
        "applicable": not blocking,
        "evidence_sha256": digest,
        "limits": "가상 상품 자료의 정적 점검입니다. PASS는 실제 배포·판매 승인이나 수요 예측을 뜻하지 않습니다.",
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("사용법: python audit.py 변경자료.json", file=sys.stderr)
        return 2
    try:
        payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        result = analyze(payload)
    except (OSError, json.JSONDecodeError, ChangeError) as exc:
        print(f"거부: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["decision"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
