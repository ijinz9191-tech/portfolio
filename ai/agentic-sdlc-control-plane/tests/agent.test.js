import test from 'node:test';
import assert from 'node:assert/strict';
import { approvalFor, buildPlan, executePlan } from '../src/agentic-runner.js';
import { EvidenceLedger } from '../src/evidence-ledger.js';

const tools = () => ({
  'collect-inventory': async () => ({ ok: true }),
  'read-pipeline': async () => ({ revision: 'r1' }),
  'read-signals': async () => ({ alerts: 1 }),
  'quarantine-card': async () => ({ state: 'QUARANTINED' }),
  'rollback-release': async () => ({ state: 'ROLLED_BACK' })
});

test('builds a bounded read-only plan for observation symptoms', () => {
  const plan = buildPlan({ incidentId: 'i-1', factsHash: 'f-1', symptoms: ['LATENCY'] });
  assert.equal(plan.steps.length, 3);
  assert.ok(plan.steps.every(step => step.startsWith('read-') || step === 'collect-inventory'));
});

test('requires plan-bound approval before mutating the fleet', async () => {
  const plan = buildPlan({ incidentId: 'i-2', factsHash: 'f-2', symptoms: ['CARD_HEALTH_DEGRADED'] });
  await assert.rejects(() => executePlan({ plan, factsHash: 'f-2', tools: tools(), ledger: new EvidenceLedger() }), { code: 'APPROVAL_REQUIRED' });
});

test('executes an approved bounded plan and records every tool result', async () => {
  const plan = buildPlan({ incidentId: 'i-3', factsHash: 'f-3', symptoms: ['CARD_HEALTH_DEGRADED'] });
  const ledger = new EvidenceLedger();
  const result = await executePlan({ plan, approvalHash: approvalFor(plan), factsHash: 'f-3', tools: tools(), ledger });
  assert.equal(result.status, 'COMPLETED');
  assert.equal(ledger.snapshot().length, 4);
  assert.equal(EvidenceLedger.verify(ledger.snapshot()), true);
});

test('rejects a stale fact snapshot after planning', async () => {
  const plan = buildPlan({ incidentId: 'i-4', factsHash: 'old', symptoms: ['LATENCY'] });
  await assert.rejects(() => executePlan({ plan, factsHash: 'new', tools: tools(), ledger: new EvidenceLedger() }), { code: 'FACTS_STALE' });
});

test('rejects non allow-listed actions even if a tool implementation exists', async () => {
  const plan = buildPlan({ incidentId: 'i-5', factsHash: 'f-5', symptoms: ['LATENCY'] });
  plan.steps.push('shell-anything');
  plan.maxSteps = 6;
  await assert.rejects(() => executePlan({ plan, factsHash: 'f-5', tools: { ...tools(), 'shell-anything': async () => ({}) }, ledger: new EvidenceLedger() }), { code: 'ACTION_DENIED' });
});

test('detects evidence ledger tampering', async () => {
  const ledger = new EvidenceLedger();
  ledger.append('SIGNAL', { latency: 10 }, '2026-09-20T10:00:00.000Z');
  ledger.append('ACTION', { result: 'ok' }, '2026-09-20T10:01:00.000Z');
  const entries = ledger.snapshot();
  entries[0].payload.latency = 999;
  assert.equal(EvidenceLedger.verify(entries), false);
});
