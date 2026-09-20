import { ControlPlaneError } from './errors.js';
import { digest } from './hash.js';

const REQUIRED = ['build', 'unit', 'integration', 'hardware-simulation', 'security'];

export function evaluateRelease(candidate) {
  if (!candidate?.revision || !Array.isArray(candidate.components) || candidate.components.length === 0) throw new ControlPlaneError('CANDIDATE_INVALID', 'revision and components are required');
  const failures = [];
  for (const component of candidate.components) {
    for (const stage of REQUIRED) {
      const run = component.stages?.find(item => item.name === stage);
      if (!run) failures.push({ component: component.name, stage, reason: 'MISSING' });
      else if (run.status !== 'PASSED') failures.push({ component: component.name, stage, reason: run.status });
    }
    if (component.sourceRevision !== candidate.revision) failures.push({ component: component.name, stage: 'source-binding', reason: 'STALE_REVISION' });
  }
  if (!candidate.lease?.leaseId || candidate.lease.requestHash !== candidate.expectedRequestHash) failures.push({ component: 'fleet', stage: 'lease', reason: 'INVALID_OR_STALE' });
  if (candidate.slo.errorBudgetRemainingPct < 20) failures.push({ component: 'service', stage: 'slo', reason: 'ERROR_BUDGET_LOW' });
  if (candidate.slo.p95LatencyMs > candidate.slo.p95LimitMs) failures.push({ component: 'service', stage: 'slo', reason: 'P95_BREACH' });
  const decision = failures.length ? 'BLOCKED' : 'RELEASABLE';
  return { decision, failures, candidateHash: digest(candidate), requiredStages: REQUIRED };
}
