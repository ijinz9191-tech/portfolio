import test from 'node:test';
import assert from 'node:assert/strict';
import { evaluateRelease } from '../src/pipeline-gate.js';
import { componentFixture } from '../src/fixtures.js';

const candidate = () => ({
  revision: 'rev-17', components: componentFixture('rev-17'),
  lease: { leaseId: 'lease-17', requestHash: 'request-17' }, expectedRequestHash: 'request-17',
  slo: { errorBudgetRemainingPct: 72, p95LatencyMs: 80, p95LimitMs: 120 }
});

test('allows a source-bound candidate with all required stages', () => {
  assert.equal(evaluateRelease(candidate()).decision, 'RELEASABLE');
});

test('blocks missing hardware simulation instead of assuming success', () => {
  const value = candidate();
  value.components[0].stages = value.components[0].stages.filter(stage => stage.name !== 'hardware-simulation');
  assert.equal(evaluateRelease(value).failures[0].reason, 'MISSING');
});

test('blocks failed security stage', () => {
  const value = candidate();
  value.components[1].stages.find(stage => stage.name === 'security').status = 'FAILED';
  assert.equal(evaluateRelease(value).decision, 'BLOCKED');
});

test('blocks evidence produced for another source revision', () => {
  const value = candidate();
  value.components[2].sourceRevision = 'old-revision';
  assert.ok(evaluateRelease(value).failures.some(item => item.reason === 'STALE_REVISION'));
});

test('blocks stale fleet lease proof', () => {
  const value = candidate();
  value.expectedRequestHash = 'different-request';
  assert.ok(evaluateRelease(value).failures.some(item => item.stage === 'lease'));
});

test('blocks release when error budget is nearly exhausted', () => {
  const value = candidate();
  value.slo.errorBudgetRemainingPct = 8;
  assert.ok(evaluateRelease(value).failures.some(item => item.reason === 'ERROR_BUDGET_LOW'));
});

test('blocks release on p95 latency breach', () => {
  const value = candidate();
  value.slo.p95LatencyMs = 180;
  assert.ok(evaluateRelease(value).failures.some(item => item.reason === 'P95_BREACH'));
});
