"""가상 답변의 인용 위치와 문서 버전을 재현 가능하게 감사한다."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normal(value: str) -> str:
    return " ".join(value.split())


def audit(payload: dict[str, Any]) -> dict[str, Any]:
    """인용의 존재와 버전 일치만 확인한다. 주장 자체의 참 여부는 판정하지 않는다."""
    if not isinstance(payload, dict):
        raise ValueError("입력은 객체여야 합니다")
    documents = payload.get("documents")
    claims = payload.get("claims")
    if not isinstance(documents, list) or not documents:
        raise ValueError("문서가 하나 이상 필요합니다")
    if not isinstance(claims, list) or not claims:
        raise ValueError("주장이 하나 이상 필요합니다")

    by_id: dict[str, str] = {}
    document_index = {}
    for document in documents:
        if not isinstance(document, dict):
            raise ValueError("문서 형식이 올바르지 않습니다")
        source_id, source_text = document.get("id"), document.get("text")
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("문서 ID가 필요합니다")
        if not isinstance(source_text, str) or not source_text.strip():
            raise ValueError("문서 본문이 필요합니다")
        if source_id in by_id:
            raise ValueError("문서 ID가 중복되었습니다")
        by_id[source_id] = source_text
        # 문서별 버전 해시와 공백 정규화는 인용 수와 무관하게 한 번 계산한다.
        document_index[source_id] = (digest(source_text), normal(source_text))

    results: list[dict[str, Any]] = []
    for number, claim in enumerate(claims, 1):
        if (
            not isinstance(claim, dict)
            or not isinstance(claim.get("statement"), str)
            or not claim["statement"].strip()
        ):
            raise ValueError(f"{number}번 주장의 문장이 필요합니다")
        citations = claim.get("citations")
        if not isinstance(citations, list) or not citations:
            raise ValueError(f"{number}번 주장에 인용이 필요합니다")
        seen: set[tuple[str, str]] = set()
        problems: list[str] = []
        for citation in citations:
            if not isinstance(citation, dict):
                problems.append("인용 형식 오류")
                continue
            source_id = citation.get("source_id")
            quote = citation.get("quote")
            expected = citation.get("source_sha256")
            if not all(
                isinstance(value, str) and value.strip()
                for value in (source_id, quote, expected)
            ):
                problems.append("인용 필드 누락")
                continue
            key = (source_id, normal(quote))
            if key in seen:
                problems.append("중복 인용")
            seen.add(key)
            source = by_id.get(source_id)
            if source is None:
                problems.append("존재하지 않는 문서")
                continue
            source_hash, normalized_source = document_index[source_id]
            normalized_quote = key[1]
            if expected != source_hash:
                problems.append("문서 버전 불일치")
            if len(normalized_quote) < 12 or normalized_quote not in normalized_source:
                problems.append("문서에 없는 인용")
        results.append(
            {
                "claim": number,
                "traceable": not problems,
                "problems": sorted(set(problems)),
            }
        )

    return {
        "traceable": all(item["traceable"] for item in results),
        "claim_count": len(results),
        "results": results,
        "scope": "인용 존재·문서 버전 검사; 의미적 사실 검증은 별도 필요",
        "input_sha256": digest(json.dumps(payload, ensure_ascii=False, sort_keys=True)),
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("사용법: python audit.py <가상-답변.json>", file=sys.stderr)
        return 2
    try:
        payload = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        result = audit(payload)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["traceable"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
