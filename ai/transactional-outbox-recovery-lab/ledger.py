"""가상 이체·기장·발행 대기 기록의 단일 SQLite 트랜잭션을 실습한다."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


class LedgerError(ValueError):
    """명령 충돌이나 잔액 부족으로 이체를 승인할 수 없다."""


class InjectedFailure(RuntimeError):
    """복구 검증을 위해 지정한 단계에서 발생시키는 합성 오류다."""


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    """이 실습만 사용하는 DB 연결과 최소 스키마를 생성한다."""
    db = sqlite3.connect(str(path), isolation_level=None, timeout=5)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY, balance_won INTEGER NOT NULL CHECK(balance_won >= 0));
        CREATE TABLE IF NOT EXISTS transfers (
            id TEXT PRIMARY KEY, source TEXT NOT NULL REFERENCES accounts(id),
            target TEXT NOT NULL REFERENCES accounts(id), amount_won INTEGER NOT NULL CHECK(amount_won > 0));
        CREATE TABLE IF NOT EXISTS postings (
            transfer_id TEXT NOT NULL REFERENCES transfers(id), account TEXT NOT NULL REFERENCES accounts(id),
            delta_won INTEGER NOT NULL, PRIMARY KEY(transfer_id, account));
        CREATE TABLE IF NOT EXISTS outbox (
            event_id TEXT PRIMARY KEY REFERENCES transfers(id), payload TEXT NOT NULL,
            delivered INTEGER NOT NULL DEFAULT 0 CHECK(delivered IN (0, 1)));
        CREATE TABLE IF NOT EXISTS inbox (
            event_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS projections (
            account TEXT PRIMARY KEY, delta_won INTEGER NOT NULL);
    """)
    return db


def seed(db: sqlite3.Connection, accounts: dict[str, int]) -> None:
    if not accounts or any(not isinstance(k, str) or not k.strip() or type(v) is not int or v < 0
                           for k, v in accounts.items()):
        raise LedgerError("계좌 ID와 0 이상 정수 원화 금액이 필요합니다")
    db.execute("BEGIN IMMEDIATE")
    try:
        db.executemany("INSERT INTO accounts VALUES (?, ?)", accounts.items())
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise


def transfer(db: sqlite3.Connection, key: str, source: str, target: str,
             amount: int, *, fail_at: str | None = None) -> str:
    """잔액·양쪽 기장·outbox를 함께 커밋하거나 함께 취소한다."""
    if any(not isinstance(v, str) or not v.strip() or v != v.strip() for v in (key, source, target)):
        raise LedgerError("공백 없는 ID가 필요합니다")
    if source == target or type(amount) is not int or not 0 < amount <= 2**63 - 1:
        raise LedgerError("서로 다른 계좌와 유효한 양수 정수 금액이 필요합니다")
    if fail_at not in (None, "after_debit", "before_outbox", "before_commit"):
        raise LedgerError("알 수 없는 오류 주입 단계입니다")
    db.execute("BEGIN IMMEDIATE")
    try:
        prior = db.execute("SELECT source, target, amount_won FROM transfers WHERE id=?", (key,)).fetchone()
        if prior:
            if prior != (source, target, amount):
                raise LedgerError("같은 이체 ID의 내용 충돌")
            db.execute("COMMIT")
            return "ALREADY_COMMITTED"
        rows = dict(db.execute("SELECT id, balance_won FROM accounts WHERE id IN (?, ?)", (source, target)))
        if source not in rows or target not in rows:
            raise LedgerError("등록되지 않은 계좌")
        if rows[source] < amount or rows[target] > 2**63 - 1 - amount:
            raise LedgerError("잔액 부족 또는 정수 범위 초과")
        db.execute("INSERT INTO transfers VALUES (?, ?, ?, ?)", (key, source, target, amount))
        db.execute("UPDATE accounts SET balance_won=balance_won-? WHERE id=?", (amount, source))
        if fail_at == "after_debit":
            raise InjectedFailure("출금 갱신 뒤 합성 오류")
        db.execute("UPDATE accounts SET balance_won=balance_won+? WHERE id=?", (amount, target))
        db.executemany("INSERT INTO postings VALUES (?, ?, ?)", [(key, source, -amount), (key, target, amount)])
        if fail_at == "before_outbox":
            raise InjectedFailure("기장 뒤 합성 오류")
        payload = json.dumps({"source": source, "target": target, "amount_won": amount}, sort_keys=True)
        db.execute("INSERT INTO outbox(event_id, payload) VALUES (?, ?)", (key, payload))
        if fail_at == "before_commit":
            raise InjectedFailure("커밋 직전 합성 오류")
        db.execute("COMMIT")
        return "COMMITTED"
    except Exception:
        db.execute("ROLLBACK")
        raise


def deliver(producer: sqlite3.Connection, consumer: sqlite3.Connection, *, lose_ack: bool = False) -> int:
    """소비자 반영 뒤 ACK가 손실돼도 이벤트 ID로 중복 반영을 막는다."""
    applied = 0
    for key, payload in producer.execute("SELECT event_id, payload FROM outbox WHERE delivered=0 ORDER BY event_id").fetchall():
        consumer.execute("BEGIN IMMEDIATE")
        try:
            prior = consumer.execute("SELECT payload FROM inbox WHERE event_id=?", (key,)).fetchone()
            if prior and prior[0] != payload:
                raise LedgerError("소비자 이벤트 ID의 내용 충돌")
            if prior is None:
                body = json.loads(payload)
                consumer.execute("INSERT INTO inbox VALUES (?, ?)", (key, payload))
                for account, delta in [(body["source"], -body["amount_won"]), (body["target"], body["amount_won"])]:
                    consumer.execute("INSERT INTO projections VALUES (?, ?) ON CONFLICT(account) DO UPDATE SET delta_won=delta_won+excluded.delta_won", (account, delta))
                applied += 1
            consumer.execute("COMMIT")
        except Exception:
            consumer.execute("ROLLBACK")
            raise
        if not lose_ack:
            producer.execute("UPDATE outbox SET delivered=1 WHERE event_id=?", (key,))
    return applied


def demo() -> dict:
    with connect() as producer, connect() as consumer:
        seed(producer, {"A": 10000, "B": 0})
        try:
            transfer(producer, "T1", "A", "B", 3000, fail_at="after_debit")
        except InjectedFailure:
            pass
        after_failure = dict(producer.execute("SELECT * FROM accounts"))
        transfer(producer, "T1", "A", "B", 3000)
        first = deliver(producer, consumer, lose_ack=True)
        retry = deliver(producer, consumer)
        return {"rollback_balances_won": after_failure,
                "committed_balances_won": dict(producer.execute("SELECT * FROM accounts")),
                "consumer_first_applied": first, "consumer_retry_applied": retry,
                "projection_delta_won": dict(consumer.execute("SELECT * FROM projections")),
                "limit": "가상 SQLite 실습. 실제 은행 계좌·메시지 브로커·운영 복구를 검증하지 않습니다."}


if __name__ == "__main__":
    print(json.dumps(demo(), ensure_ascii=False, indent=2))
