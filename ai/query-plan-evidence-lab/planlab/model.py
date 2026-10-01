"""처리 시간 수치를 주장하지 않는 재현 가능한 SQLite 실행 계획 비교."""

import hashlib
import json
import sqlite3


class EvidenceError(ValueError):
    """인덱스 전후의 비교 결과가 검증 기준을 충족하지 않을 때 사용한다."""


QUERY = (
    "SELECT order_id, tenant_id, status, created_at FROM synthetic_orders "
    "WHERE tenant_id = ? AND status = ? AND created_at >= ? "
    "ORDER BY created_at, order_id LIMIT 20"
)
PARAMS = ("tenant-07", "PENDING", 200)
INDEX = "idx_orders_tenant_status_created_order"
CURSOR_QUERY = (
    "SELECT order_id, tenant_id, status, created_at FROM synthetic_orders "
    "WHERE tenant_id = ? AND status = ? AND created_at >= ? "
    "AND (created_at > ? OR (created_at = ? AND order_id > ?)) "
    "ORDER BY created_at, order_id LIMIT 20"
)


def _rows(db):
    return db.execute(QUERY, PARAMS).fetchall()


def _plan(db):
    return [row[3] for row in db.execute("EXPLAIN QUERY PLAN " + QUERY, PARAMS)]


def verify(before, after, before_plan, after_plan):
    """결과 변경, 범위 이탈, 기대한 실행 계획 누락을 거절한다."""
    if before != after:
        raise EvidenceError("result rows changed after indexing")
    if len(after) > 20 or len({row[0] for row in after}) != len(after):
        raise EvidenceError("result limit or unique order key violated")
    if after != sorted(after, key=lambda row: (row[3], row[0])):
        raise EvidenceError("result order is not deterministic")
    if any(row[3] < PARAMS[2] for row in after):
        raise EvidenceError("result escaped the requested time window")
    if any(row[1] != PARAMS[0] for row in after):
        raise EvidenceError("cross-tenant row returned")
    if any(row[2] != PARAMS[1] for row in after):
        raise EvidenceError("wrong-status row returned")
    if not any("SCAN synthetic_orders" in line for line in before_plan):
        raise EvidenceError("baseline table scan was not observed")
    if not any(
        "SEARCH synthetic_orders USING COVERING INDEX " + INDEX in line
        for line in after_plan
    ):
        raise EvidenceError("expected covering-index search was not observed")


def verify_cursor_pages(first, second, expected):
    """커서 페이지 사이에 중복이나 경계 누락이 없는지 확인한다."""
    if not first or not second:
        raise EvidenceError("two populated pages are required")
    combined = first + second
    keys = [(row[3], row[0]) for row in combined]
    if len(set(row[0] for row in combined)) != len(combined):
        raise EvidenceError("duplicate order across cursor pages")
    if keys != sorted(keys) or keys[len(first) - 1] >= keys[len(first)]:
        raise EvidenceError("cursor page order or boundary violated")
    if combined != expected:
        raise EvidenceError("cursor page gap or changed result")


def verify_group_totals(before, after):
    """인덱스 변경이 첫 페이지만 아니라 전체 그룹 집계를 보존하는지 검사한다."""
    if before != after:
        raise EvidenceError("group totals changed after indexing")
    if not before or any(count <= 0 for _, _, count in before):
        raise EvidenceError("group totals are empty or invalid")
    if len({(tenant, status) for tenant, status, _ in before}) != len(before):
        raise EvidenceError("duplicate group key")


def cursor_rows(db, parameters=PARAMS, page_size=20):
    """마지막 복합 키를 엄격히 넘기는 커서로 전체 필터 결과를 순회한다."""
    if type(page_size) is not int or not 1 <= page_size <= 1000:
        raise EvidenceError("page size must be an integer between 1 and 1000")
    first_query = QUERY.replace("LIMIT 20", "LIMIT ?")
    next_query = CURSOR_QUERY.replace("LIMIT 20", "LIMIT ?")
    page = db.execute(first_query, tuple(parameters) + (page_size,)).fetchall()
    previous = None
    while page:
        for row in page:
            key = (row[3], row[0])
            if previous is not None and key <= previous:
                raise EvidenceError("cursor did not advance strictly")
            previous = key
            yield row
        timestamp, order_id = previous
        page = db.execute(
            next_query, tuple(parameters) + (timestamp, timestamp, order_id, page_size)
        ).fetchall()


def reproduce():
    """격리된 합성 데이터를 만들고 다시 실행할 수 있는 계획 근거를 반환한다."""
    db = sqlite3.connect(":memory:")
    try:
        db.execute(
            "CREATE TABLE synthetic_orders (order_id INTEGER PRIMARY KEY, "
            "tenant_id TEXT NOT NULL, status TEXT NOT NULL, created_at INTEGER NOT NULL)"
        )
        rows = [
            (n, f"tenant-{n % 10:02d}", "PENDING" if n % 3 else "DONE", n // 10)
            for n in range(1, 4001)
        ]
        db.executemany("INSERT INTO synthetic_orders VALUES (?, ?, ?, ?)", rows)
        before, before_plan = _rows(db), _plan(db)
        totals_query = (
            "SELECT tenant_id, status, COUNT(*) FROM synthetic_orders "
            "GROUP BY tenant_id, status ORDER BY tenant_id, status"
        )
        before_totals = db.execute(totals_query).fetchall()
        db.execute(
            f"CREATE INDEX {INDEX} ON synthetic_orders "
            "(tenant_id, status, created_at, order_id)"
        )
        after, after_plan = _rows(db), _plan(db)
        after_totals = db.execute(totals_query).fetchall()
        verify(before, after, before_plan, after_plan)
        verify_group_totals(before_totals, after_totals)
        last_time, last_id = after[-1][3], after[-1][0]
        next_page = db.execute(
            CURSOR_QUERY, PARAMS + (last_time, last_time, last_id)
        ).fetchall()
        expected_pages = db.execute(
            QUERY.replace("LIMIT 20", "LIMIT 40"), PARAMS
        ).fetchall()
        verify_cursor_pages(after, next_page, expected_pages)
        all_cursor_rows = list(cursor_rows(db))
        all_expected = db.execute(QUERY.replace(" LIMIT 20", ""), PARAMS).fetchall()
        if all_cursor_rows != all_expected:
            raise EvidenceError("full cursor traversal has a gap or changed result")
        witness = {
            "query": QUERY,
            "parameters": PARAMS,
            "rows": after,
            "group_totals": after_totals,
            "next_page": next_page,
            "all_cursor_rows": all_cursor_rows,
            "before_plan": before_plan,
            "after_plan": after_plan,
        }
        digest = hashlib.sha256(
            json.dumps(witness, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return {
            "decision": "INDEX_PLAN_VERIFIED",
            "fixture_rows": len(rows),
            "result_rows": len(after),
            "before_plan": before_plan,
            "after_plan": after_plan,
            "results_equal": before == after,
            "tenant_isolated": all(row[1] == PARAMS[0] for row in after),
            "status_filtered": all(row[2] == PARAMS[1] for row in after),
            "cursor_pages_match": after + next_page == expected_pages,
            "full_cursor_match": all_cursor_rows == all_expected,
            "full_cursor_rows": len(all_cursor_rows),
            "group_totals_match": before_totals == after_totals,
            "group_count": len(after_totals),
            "evidence_sha256": digest,
            "limits": "Synthetic SQLite plan evidence only; no wall-clock speedup, production database, or employer-system claim.",
        }
    finally:
        db.close()
