import { sha256 } from './hash.js';

export class EvidenceLedger {
  #events = [];

  append(type, payload) {
    const previousHash = this.#events.at(-1)?.hash ?? 'GENESIS';
    const sequence = this.#events.length + 1;
    const body = { sequence, type, payload, previousHash };
    const event = { ...body, hash: sha256(body) };
    this.#events.push(Object.freeze(event));
    return event;
  }

  list() { return this.#events.map((event) => ({ ...event })); }

  verify(events = this.#events) {
    let previousHash = 'GENESIS';
    for (let index = 0; index < events.length; index += 1) {
      const event = events[index];
      const body = { sequence: index + 1, type: event.type, payload: event.payload, previousHash };
      if (event.sequence !== index + 1 || event.previousHash !== previousHash || sha256(body) !== event.hash) return false;
      previousHash = event.hash;
    }
    return true;
  }
}
