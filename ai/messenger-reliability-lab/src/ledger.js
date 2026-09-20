import { createHash, randomUUID } from 'node:crypto';

const terminal = new Set(['DELIVERED', 'DEAD_LETTER']);
const clone = value => structuredClone(value);
const hash = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');

export class LedgerError extends Error {
  constructor(code, message, status = 400) {
    super(message);
    this.name = 'LedgerError';
    this.code = code;
    this.status = status;
  }
}

export class MessageLedger {
  constructor({ maxPayloadBytes = 4096, maxAttempts = 3, ackTimeoutMs = 1000,
    conversationCapacity = 100, now = () => Date.now(), id = () => randomUUID() } = {}) {
    this.config = { maxPayloadBytes, maxAttempts, ackTimeoutMs, conversationCapacity };
    this.now = now;
    this.id = id;
    this.messages = new Map();
    this.idempotency = new Map();
    this.sequence = new Map();
    this.events = [];
    this.eventSequence = 0;
  }

  enqueue(command) {
    const normalized = this.#normalize(command);
    const commandHash = hash(normalized);
    const previous = this.idempotency.get(normalized.idempotencyKey);
    if (previous) {
      if (previous.commandHash !== commandHash) throw new LedgerError('IDEMPOTENCY_CONFLICT', 'The idempotency key was reused with different content', 409);
      return { duplicate: true, message: clone(this.messages.get(previous.messageId)) };
    }

    const nextSequence = (this.sequence.get(normalized.conversationId) ?? 0) + 1;
    if (normalized.expectedSequence !== undefined && normalized.expectedSequence !== nextSequence) {
      throw new LedgerError('SEQUENCE_CONFLICT', `Expected sequence ${normalized.expectedSequence}, next sequence is ${nextSequence}`, 409);
    }
    const active = [...this.messages.values()].filter(item => item.conversationId === normalized.conversationId && !terminal.has(item.status)).length;
    if (active >= this.config.conversationCapacity) throw new LedgerError('CAPACITY_EXCEEDED', 'Conversation delivery capacity is exhausted', 429);

    const createdAt = this.now();
    const message = {
      id: this.id(), idempotencyKey: normalized.idempotencyKey,
      conversationId: normalized.conversationId, senderId: normalized.senderId,
      payload: normalized.payload, sequence: nextSequence, status: 'QUEUED',
      attempts: 0, nextAttemptAt: createdAt, createdAt, updatedAt: createdAt
    };
    this.messages.set(message.id, message);
    this.sequence.set(message.conversationId, nextSequence);
    this.idempotency.set(message.idempotencyKey, { commandHash, messageId: message.id });
    this.#event('MESSAGE_QUEUED', message, createdAt);
    return { duplicate: false, message: clone(message) };
  }

  dispatch(messageId, at = this.now()) {
    const message = this.#message(messageId);
    if (terminal.has(message.status)) throw new LedgerError('TERMINAL_MESSAGE', 'Terminal messages cannot be dispatched', 409);
    if (at < message.nextAttemptAt) throw new LedgerError('NOT_DUE', 'The message is not due for dispatch', 409);
    if (message.attempts >= this.config.maxAttempts) return this.#deadLetter(message, at);
    message.attempts += 1;
    message.status = 'IN_FLIGHT';
    message.nextAttemptAt = at + this.config.ackTimeoutMs * (2 ** (message.attempts - 1));
    message.updatedAt = at;
    this.#event('DELIVERY_DISPATCHED', message, at);
    return clone(message);
  }

  acknowledge(messageId, at = this.now()) {
    const message = this.#message(messageId);
    if (message.status === 'DELIVERED') return { duplicate: true, message: clone(message) };
    if (message.status !== 'IN_FLIGHT') throw new LedgerError('INVALID_ACK_STATE', 'Only in-flight messages can be acknowledged', 409);
    message.status = 'DELIVERED';
    message.deliveredAt = at;
    message.updatedAt = at;
    delete message.nextAttemptAt;
    this.#event('MESSAGE_DELIVERED', message, at);
    return { duplicate: false, message: clone(message) };
  }

  tick(at = this.now()) {
    const changed = [];
    for (const message of this.messages.values()) {
      if (terminal.has(message.status) || at < message.nextAttemptAt) continue;
      if (message.status === 'IN_FLIGHT' && message.attempts >= this.config.maxAttempts) {
        changed.push(this.#deadLetter(message, at));
      } else {
        changed.push(this.dispatch(message.id, at));
      }
    }
    return changed;
  }

  get(messageId) { return clone(this.#message(messageId)); }
  listEvents() { return clone(this.events); }

  snapshot() {
    return clone({ version: 1, config: this.config, eventSequence: this.eventSequence,
      messages: [...this.messages.entries()], idempotency: [...this.idempotency.entries()],
      sequence: [...this.sequence.entries()], events: this.events });
  }

  static restore(snapshot, options = {}) {
    if (snapshot?.version !== 1 || !Array.isArray(snapshot.messages) || !Array.isArray(snapshot.events)) {
      throw new LedgerError('INVALID_SNAPSHOT', 'Snapshot schema is invalid');
    }
    const ledger = new MessageLedger({ ...snapshot.config, ...options });
    ledger.messages = new Map(clone(snapshot.messages));
    ledger.idempotency = new Map(clone(snapshot.idempotency));
    ledger.sequence = new Map(clone(snapshot.sequence));
    ledger.events = clone(snapshot.events);
    ledger.eventSequence = snapshot.eventSequence;
    return ledger;
  }

  #normalize(command) {
    const required = ['idempotencyKey', 'conversationId', 'senderId', 'payload'];
    for (const field of required) if (typeof command?.[field] !== 'string' || !command[field].trim()) {
      throw new LedgerError('INVALID_COMMAND', `${field} is required`);
    }
    if (Buffer.byteLength(command.payload, 'utf8') > this.config.maxPayloadBytes) {
      throw new LedgerError('PAYLOAD_TOO_LARGE', 'Payload exceeds the configured byte limit', 413);
    }
    if (command.expectedSequence !== undefined && (!Number.isInteger(command.expectedSequence) || command.expectedSequence < 1)) {
      throw new LedgerError('INVALID_COMMAND', 'expectedSequence must be a positive integer');
    }
    return { idempotencyKey: command.idempotencyKey.trim(), conversationId: command.conversationId.trim(),
      senderId: command.senderId.trim(), payload: command.payload, expectedSequence: command.expectedSequence };
  }

  #message(messageId) {
    const message = this.messages.get(messageId);
    if (!message) throw new LedgerError('MESSAGE_NOT_FOUND', 'Message does not exist', 404);
    return message;
  }

  #deadLetter(message, at) {
    message.status = 'DEAD_LETTER';
    message.updatedAt = at;
    message.deadLetteredAt = at;
    delete message.nextAttemptAt;
    this.#event('MESSAGE_DEAD_LETTERED', message, at);
    return clone(message);
  }

  #event(type, message, at) {
    this.events.push({ eventSequence: ++this.eventSequence, type, messageId: message.id,
      conversationId: message.conversationId, messageSequence: message.sequence,
      attempt: message.attempts, at });
  }
}
