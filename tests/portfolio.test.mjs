import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, access } from 'node:fs/promises';
import vm from 'node:vm';
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
function fakeBrowser(payload, ok = true) {
  class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.textContent = ''; this.hidden = true; }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; }
  }
  const elements = new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(match => [`#${match[1]}`, new Element('div')]));
  const context = vm.createContext({ URL, document: { createElement: tag => new Element(tag), querySelector: selector => elements.get(selector) }, fetch: async () => ({ ok, json: async () => payload }) });
  return { context, elements };
}
test('user view renders public content and exposes repository link', async () => {
  const { context, elements } = fakeBrowser(data);
  await vm.runInContext(app, context);
  assert.equal(elements.get('#capabilities').children.length, data.capabilities.length);
  assert.equal(elements.get('#profile-summary').textContent, data.profileSummary);
  assert.equal(elements.get('#repository-link').children[0].href, data.repositoryUrl);
  assert.equal(elements.get('#data-error').hidden, true);
});
test('unavailable public data fails visibly without inventing project state', async () => {
  const { context, elements } = fakeBrowser({}, false);
  await vm.runInContext(app, context);
  assert.equal(elements.get('#data-error').hidden, false);
  assert.equal(elements.get('#capabilities').children.length, 1);
});
test('rendering uses text nodes even if untrusted strings reach the view', async () => {
  const payload = changed(d => { d.profileSummary = '<img src=x onerror=alert(1)>'; });
  const { context, elements } = fakeBrowser(payload);
  await vm.runInContext(app, context);
  assert.equal(elements.get('#profile-summary').textContent, payload.profileSummary);
  assert.ok(!/\.innerHTML\s*=/.test(app));
});
