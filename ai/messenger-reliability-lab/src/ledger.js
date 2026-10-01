import { createHash, randomUUID } from "node:crypto";

const terminal = new Set(["DELIVERED", "DEAD_LETTER"]);
const clone = (value) => structuredClone(value);
const hash = (value) =>
  createHash("sha256").update(JSON.stringify(value)).digest("hex");

// 메시지별 위치를 함께 저장해 재예약·취소 시 오래된 힙 항목이 남지 않도록 한다.
class DeadlineHeap {
  constructor() {
    this.items = [];
    this.positions = new Map();
  }
  peek() {
    return this.items[0];
  }
  remove(id) {
    const index = this.positions.get(id);
    if (index === undefined) return;
    const last = this.items.pop();
    this.positions.delete(id);
    if (index === this.items.length) return;
    this.items[index] = last;
    this.positions.set(last.id, index);
    this.#repair(index);
  }
  set(id, at) {
    this.remove(id);
    const index = this.items.length;
    this.items.push({ id, at });
    this.positions.set(id, index);
    this.#repair(index);
  }
  #less(a, b) {
    return a.at < b.at || (a.at === b.at && a.id < b.id);
  }
  #swap(a, b) {
    [this.items[a], this.items[b]] = [this.items[b], this.items[a]];
    this.positions.set(this.items[a].id, a);
    this.positions.set(this.items[b].id, b);
  }
  #repair(index) {
    while (index > 0) {
      const parent = (index - 1) >> 1;
      if (!this.#less(this.items[index], this.items[parent])) break;
      this.#swap(index, parent);
      index = parent;
    }
    while (index * 2 + 1 < this.items.length) {
      let child = index * 2 + 1;
      if (
        child + 1 < this.items.length &&
        this.#less(this.items[child + 1], this.items[child])
      )
        child++;
      if (!this.#less(this.items[child], this.items[index])) break;
      this.#swap(index, child);
      index = child;
    }
  }
}

export class LedgerError extends Error {
  constructor(code, message, status = 400) {
    super(message);
    this.name = "LedgerError";
    this.code = code;
    this.status = status;
  }
}

export class MessageLedger {
  constructor({
    maxPayloadBytes = 4096,
    maxAttempts = 3,
    ackTimeoutMs = 1000,
    conversationCapacity = 100,
    now = () => Date.now(),
    id = () => randomUUID(),
  } = {}) {
    this.config = {
      maxPayloadBytes,
      maxAttempts,
      ackTimeoutMs,
      conversationCapacity,
    };
    if (
      Object.values(this.config).some(
        (value) => !Number.isSafeInteger(value) || value <= 0,
      ) ||
      maxAttempts > 20
    )
      throw new LedgerError(
        "INVALID_CONFIG",
        "Limits must be positive safe integers; maxAttempts is at most 20",
      );
    this.now = now;
    this.id = id;
    this.messages = new Map();
    this.idempotency = new Map();
    this.sequence = new Map();
    this.events = [];
    this.eventSequence = 0;
    this.deadlines = new DeadlineHeap();
    this.activeCounts = new Map();
    this.enqueueOrder = new Map();
  }

  enqueue(command) {
    const normalized = this.#normalize(command);
    const commandHash = hash(normalized);
    const previous = this.idempotency.get(normalized.idempotencyKey);
    if (previous) {
      if (previous.commandHash !== commandHash)
        throw new LedgerError(
          "IDEMPOTENCY_CONFLICT",
          "The idempotency key was reused with different content",
          409,
        );
      return {
        duplicate: true,
        message: clone(this.messages.get(previous.messageId)),
      };
    }

    const nextSequence =
      (this.sequence.get(normalized.conversationId) ?? 0) + 1;
    if (
      normalized.expectedSequence !== undefined &&
      normalized.expectedSequence !== nextSequence
    ) {
      throw new LedgerError(
        "SEQUENCE_CONFLICT",
        `Expected sequence ${normalized.expectedSequence}, next sequence is ${nextSequence}`,
        409,
      );
    }
    const active = this.activeCounts.get(normalized.conversationId) ?? 0;
    if (active >= this.config.conversationCapacity)
      throw new LedgerError(
        "CAPACITY_EXCEEDED",
        "Conversation delivery capacity is exhausted",
        429,
      );

    const createdAt = this.now();
    this.#time(createdAt);
    const message = {
      id: this.id(),
      idempotencyKey: normalized.idempotencyKey,
      conversationId: normalized.conversationId,
      senderId: normalized.senderId,
      payload: normalized.payload,
      sequence: nextSequence,
      status: "QUEUED",
      attempts: 0,
      nextAttemptAt: createdAt,
      createdAt,
      updatedAt: createdAt,
    };
    if (this.messages.has(message.id))
      throw new LedgerError(
        "MESSAGE_ID_CONFLICT",
        "Message id generator returned an existing id",
        409,
      );
    this.messages.set(message.id, message);
    this.activeCounts.set(message.conversationId, active + 1);
    this.enqueueOrder.set(message.id, this.enqueueOrder.size);
    this.deadlines.set(message.id, message.nextAttemptAt);
    this.sequence.set(message.conversationId, nextSequence);
    this.idempotency.set(message.idempotencyKey, {
      commandHash,
      messageId: message.id,
    });
    this.#event("MESSAGE_QUEUED", message, createdAt);
    return { duplicate: false, message: clone(message) };
  }

  dispatch(messageId, at = this.now()) {
    const message = this.#message(messageId);
    this.#time(at, message.updatedAt);
    if (terminal.has(message.status))
      throw new LedgerError(
        "TERMINAL_MESSAGE",
        "Terminal messages cannot be dispatched",
        409,
      );
    if (at < message.nextAttemptAt)
      throw new LedgerError(
        "NOT_DUE",
        "The message is not due for dispatch",
        409,
      );
    if (message.attempts >= this.config.maxAttempts)
      return this.#deadLetter(message, at);
    const deadline = at + this.config.ackTimeoutMs * 2 ** message.attempts;
    this.#time(deadline, at);
    message.attempts += 1;
    message.status = "IN_FLIGHT";
    message.nextAttemptAt = deadline;
    this.deadlines.set(message.id, deadline);
    message.updatedAt = at;
    this.#event("DELIVERY_DISPATCHED", message, at);
    return clone(message);
  }

  acknowledge(messageId, at = this.now()) {
    const message = this.#message(messageId);
    this.#time(at, message.updatedAt);
    if (message.status === "DELIVERED")
      return { duplicate: true, message: clone(message) };
    if (message.status !== "IN_FLIGHT")
      throw new LedgerError(
        "INVALID_ACK_STATE",
        "Only in-flight messages can be acknowledged",
        409,
      );
    message.status = "DELIVERED";
    message.deliveredAt = at;
    message.updatedAt = at;
    delete message.nextAttemptAt;
    this.deadlines.remove(message.id);
    this.activeCounts.set(
      message.conversationId,
      this.activeCounts.get(message.conversationId) - 1,
    );
    this.#event("MESSAGE_DELIVERED", message, at);
    return { duplicate: false, message: clone(message) };
  }

  tick(at = this.now()) {
    this.#time(at);
    const changed = [];
    const due = [];
    while (this.deadlines.peek()?.at <= at) {
      const entry = this.deadlines.peek();
      this.deadlines.remove(entry.id);
      due.push(this.messages.get(entry.id));
    }
    try {
      for (const message of due)
        if (message.attempts < this.config.maxAttempts)
          this.#time(at + this.config.ackTimeoutMs * 2 ** message.attempts, at);
    } catch (error) {
      for (const message of due)
        this.deadlines.set(message.id, message.nextAttemptAt);
      throw error;
    }
    // 기존 API의 삽입 순서 응답을 유지하면서 기한이 지난 항목만 순회한다.
    due.sort(
      (a, b) => this.enqueueOrder.get(a.id) - this.enqueueOrder.get(b.id),
    );
    for (const message of due) {
      if (
        message.status === "IN_FLIGHT" &&
        message.attempts >= this.config.maxAttempts
      ) {
        changed.push(this.#deadLetter(message, at));
      } else {
        changed.push(this.dispatch(message.id, at));
      }
    }
    return changed;
  }

  get(messageId) {
    return clone(this.#message(messageId));
  }
  listEvents() {
    return clone(this.events);
  }

  snapshot() {
    return clone({
      version: 1,
      config: this.config,
      eventSequence: this.eventSequence,
      messages: [...this.messages.entries()],
      idempotency: [...this.idempotency.entries()],
      sequence: [...this.sequence.entries()],
      events: this.events,
    });
  }

  static restore(snapshot, options = {}) {
    if (
      snapshot?.version !== 1 ||
      !Array.isArray(snapshot.messages) ||
      !Array.isArray(snapshot.events) ||
      !Array.isArray(snapshot.idempotency) ||
      !Array.isArray(snapshot.sequence) ||
      snapshot.eventSequence !== snapshot.events.length
    ) {
      throw new LedgerError("INVALID_SNAPSHOT", "Snapshot schema is invalid");
    }
    const ledger = new MessageLedger({ ...snapshot.config, ...options });
    ledger.messages = new Map(clone(snapshot.messages));
    ledger.idempotency = new Map(clone(snapshot.idempotency));
    ledger.sequence = new Map(clone(snapshot.sequence));
    ledger.events = clone(snapshot.events);
    ledger.eventSequence = snapshot.eventSequence;
    const invalid = () => {
      throw new LedgerError(
        "INVALID_SNAPSHOT",
        "Snapshot indices or state invariants do not match",
      );
    };
    if (
      ledger.messages.size !== snapshot.messages.length ||
      ledger.idempotency.size !== ledger.messages.size ||
      ledger.sequence.size !== snapshot.sequence.length
    )
      invalid();
    const maximumSequences = new Map();
    const messageSequences = new Set();
    for (const [id, message] of ledger.messages) {
      const sequenceKey = JSON.stringify([
        message.conversationId,
        message.sequence,
      ]);
      if (
        id !== message.id ||
        !["QUEUED", "IN_FLIGHT", "DELIVERED", "DEAD_LETTER"].includes(
          message.status,
        ) ||
        !Number.isSafeInteger(message.sequence) ||
        message.sequence <= 0 ||
        messageSequences.has(sequenceKey) ||
        !Number.isSafeInteger(message.attempts) ||
        message.attempts < 0 ||
        message.attempts > ledger.config.maxAttempts ||
        ledger.idempotency.get(message.idempotencyKey)?.messageId !== id
      )
        invalid();
      messageSequences.add(sequenceKey);
      maximumSequences.set(
        message.conversationId,
        Math.max(
          maximumSequences.get(message.conversationId) ?? 0,
          message.sequence,
        ),
      );
    }
    if (
      maximumSequences.size !== ledger.sequence.size ||
      [...maximumSequences].some(
        ([room, maximum]) => ledger.sequence.get(room) !== maximum,
      )
    )
      invalid();
    for (let i = 0; i < ledger.events.length; i++)
      if (
        ledger.events[i].eventSequence !== i + 1 ||
        !ledger.messages.has(ledger.events[i].messageId)
      )
        invalid();
    for (const message of ledger.messages.values()) {
      ledger.enqueueOrder.set(message.id, ledger.enqueueOrder.size);
      if (!terminal.has(message.status)) {
        ledger.#time(message.nextAttemptAt, message.updatedAt);
        ledger.deadlines.set(message.id, message.nextAttemptAt);
        ledger.activeCounts.set(
          message.conversationId,
          (ledger.activeCounts.get(message.conversationId) ?? 0) + 1,
        );
      }
    }
    if (
      [...ledger.activeCounts.values()].some(
        (count) => count > ledger.config.conversationCapacity,
      )
    )
      invalid();
    return ledger;
  }

  #normalize(command) {
    const required = [
      "idempotencyKey",
      "conversationId",
      "senderId",
      "payload",
    ];
    for (const field of required)
      if (typeof command?.[field] !== "string" || !command[field].trim()) {
        throw new LedgerError("INVALID_COMMAND", `${field} is required`);
      }
    if (
      Buffer.byteLength(command.payload, "utf8") > this.config.maxPayloadBytes
    ) {
      throw new LedgerError(
        "PAYLOAD_TOO_LARGE",
        "Payload exceeds the configured byte limit",
        413,
      );
    }
    if (
      command.expectedSequence !== undefined &&
      (!Number.isInteger(command.expectedSequence) ||
        command.expectedSequence < 1)
    ) {
      throw new LedgerError(
        "INVALID_COMMAND",
        "expectedSequence must be a positive integer",
      );
    }
    return {
      idempotencyKey: command.idempotencyKey.trim(),
      conversationId: command.conversationId.trim(),
      senderId: command.senderId.trim(),
      payload: command.payload,
      expectedSequence: command.expectedSequence,
    };
  }

  #message(messageId) {
    const message = this.messages.get(messageId);
    if (!message)
      throw new LedgerError("MESSAGE_NOT_FOUND", "Message does not exist", 404);
    return message;
  }

  #deadLetter(message, at) {
    message.status = "DEAD_LETTER";
    message.updatedAt = at;
    message.deadLetteredAt = at;
    delete message.nextAttemptAt;
    this.deadlines.remove(message.id);
    this.activeCounts.set(
      message.conversationId,
      this.activeCounts.get(message.conversationId) - 1,
    );
    this.#event("MESSAGE_DEAD_LETTERED", message, at);
    return clone(message);
  }

  #event(type, message, at) {
    this.events.push({
      eventSequence: ++this.eventSequence,
      type,
      messageId: message.id,
      conversationId: message.conversationId,
      messageSequence: message.sequence,
      attempt: message.attempts,
      at,
    });
  }
  #time(at, minimum = 0) {
    if (!Number.isSafeInteger(at) || at < minimum)
      throw new LedgerError(
        "INVALID_TIME",
        "Time must be a nonnegative safe integer and must not precede the message state",
      );
  }
}
