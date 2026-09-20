import test from 'node:test';
import assert from 'node:assert/strict';
import { MessageLedger, LedgerError } from '../src/ledger.js';

const fixture = (overrides = {}) => {
  let now = 1000, id = 0;
  const ledger = new MessageLedger({ now: () => now, id: () => `m-${++id}`, ackTimeoutMs: 100,
    maxAttempts: 3, conversationCapacity: 2, ...overrides });
  return { ledger, advance: value => { now += value; return now; } };
};
const command = (overrides = {}) => ({ idempotencyKey: 'key-1', conversationId: 'room-1', senderId: 'user-1', payload: 'hello', ...overrides });
const code = expected => error => error instanceof LedgerError && error.code === expected;

test('queues a message with a conversation sequence', () => {
  const { ledger } = fixture();
  const result = ledger.enqueue(command({ expectedSequence: 1 }));
  assert.equal(result.duplicate, false);
  assert.equal(result.message.sequence, 1);
  assert.equal(result.message.status, 'QUEUED');
});

test('replays the same idempotent command without a second message', () => {
  const { ledger } = fixture();
  const first = ledger.enqueue(command());
  const second = ledger.enqueue(command());
  assert.equal(second.duplicate, true);
  assert.equal(second.message.id, first.message.id);
  assert.equal(ledger.listEvents().length, 1);
});

test('rejects an idempotency key reused with different content', () => {
  const { ledger } = fixture();
  ledger.enqueue(command());
  assert.throws(() => ledger.enqueue(command({ payload: 'changed' })), code('IDEMPOTENCY_CONFLICT'));
});

test('rejects an unexpected conversation sequence', () => {
  const { ledger } = fixture();
  assert.throws(() => ledger.enqueue(command({ expectedSequence: 2 })), code('SEQUENCE_CONFLICT'));
});

test('increments sequence independently per conversation', () => {
  const { ledger } = fixture();
  assert.equal(ledger.enqueue(command()).message.sequence, 1);
  assert.equal(ledger.enqueue(command({ idempotencyKey: 'key-2' })).message.sequence, 2);
  assert.equal(ledger.enqueue(command({ idempotencyKey: 'key-3', conversationId: 'room-2' })).message.sequence, 1);
});

test('rejects a payload over the configured byte limit', () => {
  const { ledger } = fixture({ maxPayloadBytes: 4 });
  assert.throws(() => ledger.enqueue(command({ payload: 'hello' })), code('PAYLOAD_TOO_LARGE'));
});

test('enforces active delivery capacity per conversation', () => {
  const { ledger } = fixture();
  ledger.enqueue(command());
  ledger.enqueue(command({ idempotencyKey: 'key-2' }));
  assert.throws(() => ledger.enqueue(command({ idempotencyKey: 'key-3' })), code('CAPACITY_EXCEEDED'));
});

test('dispatches and acknowledges a message', () => {
  const { ledger, advance } = fixture();
  const id = ledger.enqueue(command()).message.id;
  assert.equal(ledger.dispatch(id).attempts, 1);
  const delivered = ledger.acknowledge(id, advance(20));
  assert.equal(delivered.message.status, 'DELIVERED');
  assert.equal(delivered.message.deliveredAt, 1020);
});

test('treats a repeated acknowledgement as idempotent', () => {
  const { ledger } = fixture();
  const id = ledger.enqueue(command()).message.id;
  ledger.dispatch(id);
  ledger.acknowledge(id);
  assert.equal(ledger.acknowledge(id).duplicate, true);
});

test('rejects acknowledgement before dispatch', () => {
  const { ledger } = fixture();
  const id = ledger.enqueue(command()).message.id;
  assert.throws(() => ledger.acknowledge(id), code('INVALID_ACK_STATE'));
});

test('retries overdue in-flight delivery with exponential timeout', () => {
  const { ledger, advance } = fixture();
  const id = ledger.enqueue(command()).message.id;
  ledger.dispatch(id);
  const retried = ledger.tick(advance(100));
  assert.equal(retried[0].attempts, 2);
  assert.equal(retried[0].nextAttemptAt, 1300);
});

test('moves a repeatedly unacknowledged message to the dead-letter state', () => {
  const { ledger, advance } = fixture();
  const id = ledger.enqueue(command()).message.id;
  ledger.dispatch(id);
  ledger.tick(advance(100));
  ledger.tick(advance(200));
  const changed = ledger.tick(advance(400));
  assert.equal(changed[0].status, 'DEAD_LETTER');
  assert.equal(ledger.listEvents().at(-1).type, 'MESSAGE_DEAD_LETTERED');
});

test('terminal messages release conversation capacity', () => {
  const { ledger } = fixture({ conversationCapacity: 1 });
  const id = ledger.enqueue(command()).message.id;
  ledger.dispatch(id);
  ledger.acknowledge(id);
  assert.equal(ledger.enqueue(command({ idempotencyKey: 'key-2' })).message.sequence, 2);
});

test('restores idempotency, sequence and audit events from a snapshot', () => {
  const { ledger } = fixture();
  const first = ledger.enqueue(command());
  const restored = MessageLedger.restore(ledger.snapshot(), { now: () => 2000, id: () => 'restored-id' });
  assert.equal(restored.enqueue(command()).message.id, first.message.id);
  assert.equal(restored.enqueue(command({ idempotencyKey: 'key-2' })).message.sequence, 2);
  assert.equal(restored.listEvents()[0].eventSequence, 1);
});

test('rejects an invalid snapshot instead of partially restoring', () => {
  assert.throws(() => MessageLedger.restore({ version: 99 }), code('INVALID_SNAPSHOT'));
});

test('keeps audit event sequence strictly monotonic', () => {
  const { ledger } = fixture();
  const id = ledger.enqueue(command()).message.id;
  ledger.dispatch(id);
  ledger.acknowledge(id);
  assert.deepEqual(ledger.listEvents().map(event => event.eventSequence), [1, 2, 3]);
});
