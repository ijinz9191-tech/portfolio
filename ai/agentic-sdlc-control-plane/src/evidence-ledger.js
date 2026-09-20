import { ControlPlaneError } from './errors.js';
import { digest } from './hash.js';

export class EvidenceLedger {
  #entries = [];

  append(type, payload, observedAt = new Date().toISOString()) {
    if (!type || !payload) throw new ControlPlaneError('EVIDENCE_INVALID', 'type and payload are required');
    const previousHash = this.#entries.at(-1)?.hash ?? 'GENESIS';
    const body = { sequence: this.#entries.length + 1, type, payload, observedAt, previousHash };
    const entry = { ...body, hash: digest(body) };
    this.#entries.push(entry);
    return structuredClone(entry);
  }

  snapshot() { return structuredClone(this.#entries); }

  static verify(entries) {
    let previousHash = 'GENESIS';
    for (const entry of entries) {
      const body = { sequence: entry.sequence, type: entry.type, payload: entry.payload, observedAt: entry.observedAt, previousHash: entry.previousHash };
      if (entry.previousHash !== previousHash || digest(body) !== entry.hash) return false;
      previousHash = entry.hash;
    }
    return true;
  }
}
