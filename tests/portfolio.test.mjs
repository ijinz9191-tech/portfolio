import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, access } from 'node:fs/promises';

import { validatePublicData } from '../scripts/public-contract.mjs';
const root = new URL('../', import.meta.url);
const data = JSON.parse(await readFile(new URL('public.data.json', root), 'utf8'));
const html = await readFile(new URL('index.html', root), 'utf8');
const app = await readFile(new URL('app.js', root), 'utf8');
function changed(mutate) { const copy = structuredClone(data); mutate(copy); return copy; }
test('public data passes its explicit contract', () => assert.equal(validatePublicData(data), data));
test('private fields, contact details, markup and secrets are rejected', () => {
  assert.throws(() => validatePublicData({ ...data, candidate_facts: [] }));
  for (const value of ['password=secret', '010-1234-5678', 'someone@example.com', '<script>alert(1)</script>', 'C:\\private\\resume.pdf', 'ghp_' + 'a'.repeat(36)]) {
    assert.throws(() => validatePublicData(changed(d => { d.profileSummary = value; })), value);
  }
});
test('private, credential-bearing and placeholder links are rejected', () => {
  for (const url of ['http://github.com/user/repo', 'https://localhost/', 'https://127.0.0.1/', 'https://[::1]/', 'https://intranet.local/', 'https://user:password@github.com/', 'https://github.com/?token=secret', 'https://example.com/']) {
    assert.throws(() => validatePublicData(changed(d => { d.repositoryUrl = url; })), url);
  }
});
test('metrics cannot be presented without a measured denominator and evidence', () => {
  const metrics = { title: '실행 시간', description: '합성 입력 로컬 실험', scope: '합성 공고 세 건', denominator: 3, verifiedAt: '2026-09-12T00:00:00Z', evidenceUrl: 'https://github.com/org/repo/actions/runs/1' };
  assert.doesNotThrow(() => validatePublicData(changed(d => { d.metrics = metrics; })));
  for (const invalid of [{ ...metrics, denominator: 0 }, { ...metrics, evidenceUrl: null }, { ...metrics, verifiedAt: 'pending' }]) assert.throws(() => validatePublicData(changed(d => { d.metrics = invalid; })));
});
test('all section anchors and local assets resolve', async () => {
  const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(match => match[1]);
  assert.equal(ids.length, new Set(ids).size, 'duplicate IDs');
  for (const match of html.matchAll(/(?:href|src)="([^"]+)"/g)) {
    const target = match[1];
    if (target.startsWith('#')) assert.ok(ids.includes(target.slice(1)), `missing anchor ${target}`);
    else { assert.ok(!target.includes(':'), `unexpected external static asset ${target}`); await access(new URL(target, root)); }
  }
  assert.match(html, /<html lang="ko">/);
  assert.match(html, /name="viewport"/);
  assert.match(html, /Content-Security-Policy/);
  assert.ok(!html.includes('style="'), 'inline styles violate CSP');
});

test('app uses text nodes for event content and exposes functioning controls', () => {
  assert.ok(!/\.innerHTML\s*=/.test(app));
  for (const id of ['scenario-list','incident-list','filters','detail','health-label','repository-link','topology-map','chart-latency','chart-error','chart-rps','run','step','inject','reset','run-select','replay-tick','load-replay','back-live']) assert.match(html,new RegExp('id="'+id+'"'));
  for (const route of ['/api/sim/state','/api/sim/control','/api/sim/faults','/api/sim/runbooks','/api/sim/reset','/api/sim/runs/','/api/sim/incidents/']) assert.ok(app.includes(route), 'missing functioning API route '+route);
});
