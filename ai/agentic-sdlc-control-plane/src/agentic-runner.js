import { ControlPlaneError } from './errors.js';
import { digest } from './hash.js';

const ALLOWED_ACTIONS = new Set(['collect-inventory', 'read-pipeline', 'read-signals', 'quarantine-card', 'rollback-release']);
const MUTATING_ACTIONS = new Set(['quarantine-card', 'rollback-release']);

export function buildPlan({ incidentId, factsHash, symptoms }) {
  if (!incidentId || !factsHash || !Array.isArray(symptoms) || symptoms.length === 0) throw new ControlPlaneError('PLAN_INPUT_INVALID', 'incident, facts and symptoms are required');
  const steps = ['collect-inventory', 'read-pipeline', 'read-signals'];
  if (symptoms.includes('CARD_HEALTH_DEGRADED')) steps.push('quarantine-card');
  if (symptoms.includes('RELEASE_REGRESSION')) steps.push('rollback-release');
  const body = { incidentId, factsHash, steps, maxSteps: 5 };
  return { ...body, planHash: digest(body) };
}

export const approvalFor = plan => digest({ scope: 'MUTATING_STEPS', planHash: plan.planHash, incidentId: plan.incidentId });

export async function executePlan({ plan, approvalHash, factsHash, tools, ledger }) {
  if (plan.factsHash !== factsHash) throw new ControlPlaneError('FACTS_STALE', 'facts changed after planning');
  if (plan.steps.length > plan.maxSteps) throw new ControlPlaneError('STEP_LIMIT', 'plan exceeds bounded step limit');
  if (plan.steps.some(step => !ALLOWED_ACTIONS.has(step))) throw new ControlPlaneError('ACTION_DENIED', 'plan includes a non allow-listed action');
  if (plan.steps.some(step => MUTATING_ACTIONS.has(step)) && approvalHash !== approvalFor(plan)) throw new ControlPlaneError('APPROVAL_REQUIRED', 'mutation requires a plan-bound approval');
  const outputs = [];
  for (const step of plan.steps) {
    if (typeof tools[step] !== 'function') throw new ControlPlaneError('TOOL_UNAVAILABLE', 'planned tool is unavailable', { step });
    const result = await tools[step]({ incidentId: plan.incidentId, planHash: plan.planHash });
    outputs.push({ step, result });
    ledger.append('TOOL_RESULT', { step, resultHash: digest(result), mutating: MUTATING_ACTIONS.has(step) });
  }
  return { status: 'COMPLETED', outputs, evidenceHead: ledger.snapshot().at(-1)?.hash ?? null };
}
