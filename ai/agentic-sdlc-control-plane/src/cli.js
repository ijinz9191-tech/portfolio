import { reserveCards } from './inventory.js';
import { EvidenceLedger } from './evidence-ledger.js';
import { evaluateRelease } from './pipeline-gate.js';
import { approvalFor, buildPlan, executePlan } from './agentic-runner.js';
import { componentFixture, fleetFixture } from './fixtures.js';

const request = { leaseId: 'release-2026-09-20', count: 2, minMemoryGiB: 48, features: ['fp16', 'collective'], maxNodes: 1, sameFirmware: true };
const { lease } = reserveCards(fleetFixture(), request);
const revision = 'synthetic-4f2c1e9';
const gate = evaluateRelease({ revision, components: componentFixture(revision), lease, expectedRequestHash: lease.requestHash,
  slo: { errorBudgetRemainingPct: 78, p95LatencyMs: 84, p95LimitMs: 120 } });

const ledger = new EvidenceLedger();
ledger.append('RELEASE_GATE', gate, '2026-09-20T12:00:00.000Z');
const plan = buildPlan({ incidentId: 'synthetic-incident-17', factsHash: gate.candidateHash, symptoms: ['CARD_HEALTH_DEGRADED'] });
const tools = {
  'collect-inventory': async () => ({ nodes: 2, healthyCards: 3 }),
  'read-pipeline': async () => ({ revision, decision: gate.decision }),
  'read-signals': async () => ({ degradedCards: ['npu-b2'] }),
  'quarantine-card': async () => ({ cardId: 'npu-b2', state: 'QUARANTINED' })
};
const execution = await executePlan({ plan, approvalHash: approvalFor(plan), factsHash: gate.candidateHash, tools, ledger });
console.log(JSON.stringify({ lease, gate, execution, ledgerValid: EvidenceLedger.verify(ledger.snapshot()) }, null, 2));
