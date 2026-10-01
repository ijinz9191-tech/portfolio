import test from "node:test";
import assert from "node:assert/strict";
import { MessageLedger, LedgerError } from "../src/ledger.js";

test("기한 힙은 스캔 기준 구현과 재시도·확인·복원 순서가 동일하다", () => {
  const { ledger } = fixture({ conversationCapacity: 5000 });
  const reference = [];
  for (let i = 0; i < 2000; i++)
    reference.push(
      ledger.enqueue(
        command({ idempotencyKey: `k-${i}`, conversationId: `room-${i % 7}` }),
      ).message,
    );
  for (const at of [1000, 1050, 1100, 1300, 1700]) {
    const expected = [];
    for (const message of reference) {
      if (
        ["DELIVERED", "DEAD_LETTER"].includes(message.status) ||
        at < message.nextAttemptAt
      )
        continue;
      if (message.attempts === 3) {
        message.status = "DEAD_LETTER";
        message.deadLetteredAt = at;
        delete message.nextAttemptAt;
      } else {
        message.nextAttemptAt = at + 100 * 2 ** message.attempts;
        message.attempts++;
        message.status = "IN_FLIGHT";
      }
      message.updatedAt = at;
      expected.push(structuredClone(message));
    }
    assert.deepEqual(ledger.tick(at), expected);
    if (at === 1000)
      for (let i = 0; i < reference.length; i += 3) {
        const message = reference[i];
        ledger.acknowledge(message.id, 1025);
        message.status = "DELIVERED";
        message.deliveredAt = 1025;
        message.updatedAt = 1025;
        delete message.nextAttemptAt;
      }
  }
  const restored = MessageLedger.restore(ledger.snapshot(), {
    now: () => 2000,
    id: () => "new-message",
  });
  assert.deepEqual(restored.tick(2000), []);
  assert.equal(
    restored.enqueue(
      command({ idempotencyKey: "after", conversationId: "room-0" }),
    ).message.sequence,
    287,
  );
});
test("대기 중 복원은 힙과 대화별 용량 인덱스를 재구축한다", () => {
  const { ledger } = fixture({ conversationCapacity: 1 });
  const first = ledger.enqueue(command()).message;
  ledger.dispatch(first.id, 1000);
  const restored = MessageLedger.restore(ledger.snapshot(), {
    now: () => 1100,
  });
  assert.throws(
    () => restored.enqueue(command({ idempotencyKey: "extra" })),
    code("CAPACITY_EXCEEDED"),
  );
  assert.equal(restored.tick(1100)[0].attempts, 2);
  restored.acknowledge(first.id, 1110);
  assert.equal(
    restored.enqueue(command({ idempotencyKey: "extra" })).message.sequence,
    2,
  );
});
test("시간 경계 실패는 상태와 다음 예약을 잃지 않는다", () => {
  const { ledger } = fixture();
  const id = ledger.enqueue(command()).message.id;
  const before = ledger.snapshot();
  for (const at of [NaN, Infinity, -1, Number.MAX_SAFE_INTEGER])
    assert.throws(() => ledger.tick(at), code("INVALID_TIME"));
  assert.deepEqual(ledger.snapshot(), before);
  assert.equal(ledger.tick(1000)[0].id, id);
  assert.throws(() => ledger.acknowledge(id, 999), code("INVALID_TIME"));
});
test("스냅샷 중복 ID와 끊어진 멱등 인덱스를 거부한다", () => {
  const { ledger } = fixture();
  ledger.enqueue(command());
  const duplicate = ledger.snapshot();
  duplicate.messages.push(structuredClone(duplicate.messages[0]));
  assert.throws(
    () => MessageLedger.restore(duplicate),
    code("INVALID_SNAPSHOT"),
  );
  const dangling = ledger.snapshot();
  dangling.idempotency[0][1].messageId = "missing";
  assert.throws(
    () => MessageLedger.restore(dangling),
    code("INVALID_SNAPSHOT"),
  );
});

const fixture = (overrides = {}) => {
  let now = 1000,
    id = 0;
  const ledger = new MessageLedger({
    now: () => now,
    id: () => `m-${++id}`,
    ackTimeoutMs: 100,
    maxAttempts: 3,
    conversationCapacity: 2,
    ...overrides,
  });
  return {
    ledger,
    advance: (value) => {
      now += value;
      return now;
    },
  };
};
const command = (overrides = {}) => ({
  idempotencyKey: "key-1",
  conversationId: "room-1",
  senderId: "user-1",
  payload: "hello",
  ...overrides,
});
const code = (expected) => (error) =>
  error instanceof LedgerError && error.code === expected;

test("queues a message with a conversation sequence", () => {
  const { ledger } = fixture();
  const result = ledger.enqueue(command({ expectedSequence: 1 }));
  assert.equal(result.duplicate, false);
  assert.equal(result.message.sequence, 1);
  assert.equal(result.message.status, "QUEUED");
});

test("replays the same idempotent command without a second message", () => {
  const { ledger } = fixture();
  const first = ledger.enqueue(command());
  const second = ledger.enqueue(command());
  assert.equal(second.duplicate, true);
  assert.equal(second.message.id, first.message.id);
  assert.equal(ledger.listEvents().length, 1);
});

test("rejects an idempotency key reused with different content", () => {
  const { ledger } = fixture();
  ledger.enqueue(command());
  assert.throws(
    () => ledger.enqueue(command({ payload: "changed" })),
    code("IDEMPOTENCY_CONFLICT"),
  );
});

test("rejects an unexpected conversation sequence", () => {
  const { ledger } = fixture();
  assert.throws(
    () => ledger.enqueue(command({ expectedSequence: 2 })),
    code("SEQUENCE_CONFLICT"),
  );
});

test("increments sequence independently per conversation", () => {
  const { ledger } = fixture();
  assert.equal(ledger.enqueue(command()).message.sequence, 1);
  assert.equal(
    ledger.enqueue(command({ idempotencyKey: "key-2" })).message.sequence,
    2,
  );
  assert.equal(
    ledger.enqueue(
      command({ idempotencyKey: "key-3", conversationId: "room-2" }),
    ).message.sequence,
    1,
  );
});

test("rejects a payload over the configured byte limit", () => {
  const { ledger } = fixture({ maxPayloadBytes: 4 });
  assert.throws(
    () => ledger.enqueue(command({ payload: "hello" })),
    code("PAYLOAD_TOO_LARGE"),
  );
});

test("enforces active delivery capacity per conversation", () => {
  const { ledger } = fixture();
  ledger.enqueue(command());
  ledger.enqueue(command({ idempotencyKey: "key-2" }));
  assert.throws(
    () => ledger.enqueue(command({ idempotencyKey: "key-3" })),
    code("CAPACITY_EXCEEDED"),
  );
});

test("dispatches and acknowledges a message", () => {
  const { ledger, advance } = fixture();
  const id = ledger.enqueue(command()).message.id;
  assert.equal(ledger.dispatch(id).attempts, 1);
  const delivered = ledger.acknowledge(id, advance(20));
  assert.equal(delivered.message.status, "DELIVERED");
  assert.equal(delivered.message.deliveredAt, 1020);
});

test("treats a repeated acknowledgement as idempotent", () => {
  const { ledger } = fixture();
  const id = ledger.enqueue(command()).message.id;
  ledger.dispatch(id);
  ledger.acknowledge(id);
  assert.equal(ledger.acknowledge(id).duplicate, true);
});

test("rejects acknowledgement before dispatch", () => {
  const { ledger } = fixture();
  const id = ledger.enqueue(command()).message.id;
  assert.throws(() => ledger.acknowledge(id), code("INVALID_ACK_STATE"));
});

test("retries overdue in-flight delivery with exponential timeout", () => {
  const { ledger, advance } = fixture();
  const id = ledger.enqueue(command()).message.id;
  ledger.dispatch(id);
  const retried = ledger.tick(advance(100));
  assert.equal(retried[0].attempts, 2);
  assert.equal(retried[0].nextAttemptAt, 1300);
});

test("moves a repeatedly unacknowledged message to the dead-letter state", () => {
  const { ledger, advance } = fixture();
  const id = ledger.enqueue(command()).message.id;
  ledger.dispatch(id);
  ledger.tick(advance(100));
  ledger.tick(advance(200));
  const changed = ledger.tick(advance(400));
  assert.equal(changed[0].status, "DEAD_LETTER");
  assert.equal(ledger.listEvents().at(-1).type, "MESSAGE_DEAD_LETTERED");
});

test("terminal messages release conversation capacity", () => {
  const { ledger } = fixture({ conversationCapacity: 1 });
  const id = ledger.enqueue(command()).message.id;
  ledger.dispatch(id);
  ledger.acknowledge(id);
  assert.equal(
    ledger.enqueue(command({ idempotencyKey: "key-2" })).message.sequence,
    2,
  );
});

test("restores idempotency, sequence and audit events from a snapshot", () => {
  const { ledger } = fixture();
  const first = ledger.enqueue(command());
  const restored = MessageLedger.restore(ledger.snapshot(), {
    now: () => 2000,
    id: () => "restored-id",
  });
  assert.equal(restored.enqueue(command()).message.id, first.message.id);
  assert.equal(
    restored.enqueue(command({ idempotencyKey: "key-2" })).message.sequence,
    2,
  );
  assert.equal(restored.listEvents()[0].eventSequence, 1);
});

test("rejects an invalid snapshot instead of partially restoring", () => {
  assert.throws(
    () => MessageLedger.restore({ version: 99 }),
    code("INVALID_SNAPSHOT"),
  );
});

test("keeps audit event sequence strictly monotonic", () => {
  const { ledger } = fixture();
  const id = ledger.enqueue(command()).message.id;
  ledger.dispatch(id);
  ledger.acknowledge(id);
  assert.deepEqual(
    ledger.listEvents().map((event) => event.eventSequence),
    [1, 2, 3],
  );
});
