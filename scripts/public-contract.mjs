import assert from 'node:assert/strict';

const secretPatterns = [
  /-----BEGIN [A-Z ]*PRIVATE KEY-----/i,
  /\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})\b/,
  /\b(?:password|passwd|access_token|refresh_token|session_cookie|authorization)\s*[:=]/i,
  /\b\d{6}-[1-4]\d{6}\b/,
  /\b01[016789][- ]?\d{3,4}[- ]?\d{4}\b/,
  /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i,
  /(?:\b[A-Z]:[\\/]|file:\/\/|\\\\)/i,
];
function keys(value, allowed, label) {
  assert.ok(value && typeof value === 'object' && !Array.isArray(value), `${label}: object required`);
  assert.deepEqual(Object.keys(value).sort(), [...allowed].sort(), `${label}: unexpected or missing fields`);
}
function text(value, label, max = 1200) {
  assert.equal(typeof value, 'string', `${label}: string required`);
  assert.ok(value.trim().length && value.length <= max, `${label}: invalid length`);
  assert.ok(!/[<>\u0000-\u0008]/.test(value), `${label}: markup/control characters prohibited`);
  for (const pattern of secretPatterns) assert.ok(!pattern.test(value), `${label}: possible private data`);
}
export function publicUrl(value, label) {
  if (value === null) return;
  text(value, label, 2048);
  const url = new URL(value);
  assert.equal(url.protocol, 'https:', `${label}: HTTPS required`);
  assert.ok(!url.username && !url.password, `${label}: credentials prohibited`);
  assert.ok(!url.search, `${label}: query strings prohibited`);
  assert.ok(!url.hostname.includes(':') && !/^\d+(\.\d+){3}$/.test(url.hostname), `${label}: numeric/local hosts prohibited`);
  assert.ok(url.hostname.includes('.') && !/(?:^|\.)(?:localhost|local|internal|lan|test|example|invalid)$/.test(url.hostname), `${label}: public hostname required`);
  assert.ok(!/(?:^|\.)(?:example\.com|example\.org|example\.net)$/.test(url.hostname), `${label}: placeholder hostname prohibited`);
}
export function validatePublicData(data) {
  keys(data, ['schemaVersion', 'revision', 'profileSummary', 'repositoryUrl', 'capabilities', 'evidence', 'metrics'], 'public');
  assert.equal(data.schemaVersion, 1, 'unsupported schemaVersion');
  text(data.revision, 'revision', 120);
  assert.match(data.revision, /^[a-zA-Z0-9._-]+$/, 'revision must be a safe public version label');
  text(data.profileSummary, 'profileSummary');
  publicUrl(data.repositoryUrl, 'repositoryUrl');
  assert.ok(Array.isArray(data.capabilities) && data.capabilities.length > 0 && data.capabilities.length <= 12, 'capabilities: 1–12 entries required');
  data.capabilities.forEach((item, i) => {
    keys(item, ['title', 'status', 'description'], `capabilities[${i}]`);
    text(item.title, 'capability title', 100);
    text(item.description, 'capability description');
    assert.ok(['implemented', 'planned', 'unverified'].includes(item.status), 'invalid capability status');
  });
  assert.ok(Array.isArray(data.evidence) && data.evidence.length <= 30, 'evidence: array required');
  data.evidence.forEach((item, i) => {
    keys(item, ['title', 'description', 'kind', 'url'], `evidence[${i}]`);
    text(item.title, 'evidence title', 100);
    text(item.description, 'evidence description');
    assert.ok(['source', 'test', 'release', 'deployment', 'pending'].includes(item.kind), 'invalid evidence kind');
    publicUrl(item.url, 'evidence url');
    if (['release', 'deployment'].includes(item.kind)) assert.ok(item.url, 'release/deployment require public evidence URL');
  });
  if (data.metrics !== null) {
    keys(data.metrics, ['title', 'description', 'scope', 'denominator', 'verifiedAt', 'evidenceUrl'], 'metrics');
    for (const field of ['title', 'description', 'scope']) text(data.metrics[field], `metrics.${field}`);
    assert.ok(Number.isSafeInteger(data.metrics.denominator) && data.metrics.denominator > 0, 'metrics require positive measured denominator');
    assert.match(data.metrics.verifiedAt, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/, 'metrics require UTC timestamp');
    assert.ok(Number.isFinite(Date.parse(data.metrics.verifiedAt)), 'metrics require valid timestamp');
    publicUrl(data.metrics.evidenceUrl, 'metrics.evidenceUrl');
    assert.ok(data.metrics.evidenceUrl, 'metrics require public evidence URL');
  }
  return data;
}
