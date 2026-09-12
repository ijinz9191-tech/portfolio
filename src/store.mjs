import { DatabaseSync } from 'node:sqlite';
import { randomUUID } from 'node:crypto';

export class LabError extends Error {
  constructor(status, code, message) { super(message); this.status = status; this.code = code; }
}
export const SERVICES = ['checkout-api', 'catalog-api', 'identity-api'];
const KINDS = ['alert', 'note', 'mitigation', 'recovery'];
export const SCENARIOS = [
  { id: 'checkout-timeout', service: 'checkout-api', title: 'Checkout Query Timeout', description: '느린 Query로 응답이 지연되는 상황을 재현합니다.', evidence: ['Synthetic query latency exceeded the lab threshold.', 'A missing index was identified in the synthetic query plan.'], mitigation: 'Synthetic index change applied; query plan reviewed.', recovery: 'Synthetic probe passed after the index change.' },
  { id: 'catalog-cache', service: 'catalog-api', title: 'Catalog Cache Miss', description: 'Cache miss 증가와 Backend 부하를 연결해 봅니다.', evidence: ['Synthetic cache warm-up was skipped.', 'Synthetic origin reads increased after cache expiry.'], mitigation: 'Synthetic cache warm-up completed; expiry policy adjusted.', recovery: 'Synthetic cache and origin probes passed.' },
  { id: 'identity-session', service: 'identity-api', title: 'SSO Session Routing', description: 'Session과 요청 경로의 불일치를 추적합니다.', evidence: ['Synthetic sign-in reached a node without the expected session.', 'Synthetic route trace points to a session affinity mismatch.'], mitigation: 'Synthetic session routing policy aligned across nodes.', recovery: 'Synthetic sign-in probe passed across both nodes.' },
];
function reject(code, message, status = 400) { throw new LabError(status, code, message); }
function object(value, fields) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) reject('INVALID_INPUT', 'JSON object required.');
  if (Object.keys(value).some(key => !fields.includes(key)) || fields.some(key => !Object.hasOwn(value, key))) reject('INVALID_FIELDS', `Expected fields: ${fields.join(', ')}`);
}
function text(value, max, label) {
  if (typeof value !== 'string' || !value.trim() || value.length > max || /[\u0000-\u001f\u007f]/.test(value)) reject('INVALID_INPUT', `${label} must be 1-${max} printable characters.`);
  return value;
}
export function identifier(value) {
  if (typeof value !== 'string' || !/^[A-Za-z0-9_-]{1,80}$/.test(value)) reject('INVALID_ID', 'Invalid identifier.');
  return value;
}
export function validateEvent(input) {
  object(input, ['eventId', 'incidentId', 'service', 'kind', 'message', 'occurredAt']);
  identifier(input.eventId); identifier(input.incidentId);
  if (!SERVICES.includes(input.service)) reject('INVALID_SERVICE', 'Unknown lab service.');
  if (!KINDS.includes(input.kind)) reject('INVALID_KIND', 'Unknown event kind.');
  text(input.message, 600, 'message');
  if (typeof input.occurredAt !== 'string' || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(input.occurredAt) || !Number.isFinite(Date.parse(input.occurredAt)) || new Date(input.occurredAt).toISOString() !== input.occurredAt) reject('INVALID_TIME', 'occurredAt must be a valid canonical UTC timestamp with milliseconds.');
  return Object.fromEntries(['eventId', 'incidentId', 'service', 'kind', 'message', 'occurredAt'].map(key => [key, input[key]]));
}
export function transition(status, kind) {
  if (!status && kind === 'alert') return 'open';
  if (status === 'resolved') reject('INCIDENT_RESOLVED', 'Resolved incidents are immutable. Create a new incident.', 409);
  if (!status) reject('ALERT_REQUIRED', 'An incident must start with an alert.', 409);
  if (kind === 'alert') reject('ALREADY_OPEN', 'An incident has only one opening alert.', 409);
  if (kind === 'recovery' && status !== 'mitigating') reject('MITIGATION_REQUIRED', 'Apply mitigation before confirming recovery.', 409);
  if (kind === 'mitigation') return 'mitigating';
  if (kind === 'recovery') return 'resolved';
  return status;
}
function incident(row) {
  return row && { id: row.id, service: row.service, title: row.title, status: row.status, createdAt: row.created_at, updatedAt: row.updated_at, revision: row.revision, synthetic: true };
}
function event(row) { return { ...JSON.parse(row.payload), sequence: row.sequence }; }
export class LabStore {
  constructor(path = ':memory:') {
    this.db = new DatabaseSync(path);
    this.db.exec(`PRAGMA foreign_keys=ON; PRAGMA journal_mode=WAL; PRAGMA busy_timeout=3000;
      CREATE TABLE IF NOT EXISTS incidents (id TEXT PRIMARY KEY, service TEXT NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('open','mitigating','resolved')), created_at TEXT NOT NULL, updated_at TEXT NOT NULL, revision INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE, incident_id TEXT NOT NULL REFERENCES incidents(id), occurred_at TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS events_incident_sequence ON events(incident_id,sequence);
      CREATE INDEX IF NOT EXISTS incidents_status_updated ON incidents(status,updated_at);`);
  }
  close() { this.db.close(); }
  healthy() { return this.db.prepare('SELECT 1 AS ok').get().ok === 1; }
  ingest(inputs) {
    if (!Array.isArray(inputs) || !inputs.length || inputs.length > 20) reject('INVALID_BATCH', 'Supply 1-20 events.');
    const values = inputs.map(validateEvent);
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const outcomes = [];
      for (const value of values) {
        const payload = JSON.stringify(value);
        const previous = this.db.prepare('SELECT * FROM events WHERE event_id=?').get(value.eventId);
        if (previous) {
          if (previous.payload !== payload) reject('IDEMPOTENCY_CONFLICT', 'Event ID already exists with a different payload.', 409);
          outcomes.push({ eventId: value.eventId, duplicate: true, sequence: previous.sequence }); continue;
        }
        const row = this.db.prepare('SELECT * FROM incidents WHERE id=?').get(value.incidentId);
        if (row && row.service !== value.service) reject('SERVICE_CONFLICT', 'Incident service cannot change.', 409);
        if (row && value.occurredAt < row.updated_at) reject('OUT_OF_ORDER', 'Late events are rejected; preserve the event timeline.', 409);
        const next = transition(row?.status, value.kind);
        if (!row) this.db.prepare('INSERT INTO incidents VALUES (?,?,?,?,?,?,?)').run(value.incidentId, value.service, value.message, next, value.occurredAt, value.occurredAt, 1);
        else this.db.prepare('UPDATE incidents SET status=?, updated_at=?, revision=revision+1 WHERE id=?').run(next, value.occurredAt, value.incidentId);
        const result = this.db.prepare('INSERT INTO events(event_id,incident_id,occurred_at,kind,payload) VALUES (?,?,?,?,?)').run(value.eventId, value.incidentId, value.occurredAt, value.kind, payload);
        outcomes.push({ eventId: value.eventId, duplicate: false, sequence: Number(result.lastInsertRowid) });
      }
      this.db.exec('COMMIT'); return outcomes;
    } catch (error) { this.db.exec('ROLLBACK'); throw error; }
  }
  detail(id) {
    identifier(id);
    const row = this.db.prepare('SELECT * FROM incidents WHERE id=?').get(id);
    if (!row) reject('NOT_FOUND', 'Incident not found.', 404);
    return { ...incident(row), events: this.db.prepare('SELECT * FROM events WHERE incident_id=? ORDER BY sequence ASC').all(id).map(event) };
  }
  list(params = new URLSearchParams()) {
    for (const key of params.keys()) if (!['q','status','service','limit'].includes(key) || params.getAll(key).length !== 1) reject('INVALID_QUERY', 'Unknown or duplicate query parameter.');
    const q = params.get('q') || '', status = params.get('status') || '', service = params.get('service') || '', rawLimit = params.get('limit') || '50';
    if (q.length > 80 || /[\u0000-\u001f\u007f]/.test(q)) reject('INVALID_QUERY', 'Search must contain at most 80 printable characters.');
    if (status && !['open','mitigating','resolved'].includes(status)) reject('INVALID_QUERY', 'Invalid status.');
    if (service && !SERVICES.includes(service)) reject('INVALID_QUERY', 'Invalid service.');
    if (!/^[1-9]\d?$|^100$/.test(rawLimit)) reject('INVALID_QUERY', 'limit must be an integer from 1 to 100.');
    const where = [], args = [];
    if (q) { where.push("(title LIKE ? ESCAPE '\\' OR id LIKE ? ESCAPE '\\')"); const literal = '%' + q.replace(/[\\%_]/g, '\\$&') + '%'; args.push(literal, literal); }
    if (status) { where.push('status=?'); args.push(status); }
    if (service) { where.push('service=?'); args.push(service); }
    const clause = where.length ? ' WHERE '+where.join(' AND ') : '';
    const matched = this.db.prepare('SELECT COUNT(*) AS n FROM incidents'+clause).get(...args).n;
    const incidents = this.db.prepare('SELECT * FROM incidents'+clause+' ORDER BY updated_at DESC, id ASC LIMIT ?').all(...args, Number(rawLimit)).map(incident);
    const counts = { open: 0, mitigating: 0, resolved: 0 };
    for (const row of this.db.prepare('SELECT status, COUNT(*) AS n FROM incidents GROUP BY status').all()) counts[row.status] = row.n;
    return { incidents, matched, limit: Number(rawLimit), counts, eventCount: this.db.prepare('SELECT COUNT(*) AS n FROM events').get().n, synthetic: true };
  }
  scenario(id) {
    const config = SCENARIOS.find(item => item.id === id);
    if (!config) reject('INVALID_SCENARIO', 'Unknown scenario.');
    const incidentId = randomUUID(), now = Date.now();
    const inputs = [config.title, ...config.evidence].map((message, index) => ({ eventId: randomUUID(), incidentId, service: config.service, kind: index ? 'note' : 'alert', message, occurredAt: new Date(now + index).toISOString() }));
    this.ingest(inputs); return this.detail(incidentId);
  }
  action(id, action) {
    if (!['mitigate','recover'].includes(action)) reject('INVALID_ACTION', 'Use mitigate or recover.');
    const current = this.detail(id);
    if (action === 'mitigate' && current.status !== 'open') reject('INVALID_ACTION_STATE', 'Mitigation is available for open incidents only.', 409);
    const config = SCENARIOS.find(item => item.service === current.service);
    const kind = action === 'mitigate' ? 'mitigation' : 'recovery';
    this.ingest([{eventId: randomUUID(), incidentId: id, service: current.service, kind, message: config[kind], occurredAt: new Date(Math.max(Date.now(), Date.parse(current.updatedAt)+1)).toISOString()}]);
    return this.detail(id);
  }
}
