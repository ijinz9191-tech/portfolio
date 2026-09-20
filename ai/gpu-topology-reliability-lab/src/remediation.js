import { createHash } from "node:crypto";
import { invariant } from "./errors.js";

const allowed = new Set(["CORDON_GPU", "REPIN_WORKLOAD", "REBALANCE_NIC", "ROLLBACK"]);
const digest = (value) => createHash("sha256").update(JSON.stringify(value)).digest("hex");

export class RemediationLedger {
  constructor(events = []) {
    this.events = [];
    for (const event of events) this.#append(event.type, event.payload, event.at);
  }

  propose({ incidentId, action, target, reason }) {
    invariant(allowed.has(action) && action !== "ROLLBACK", "UNSAFE_ACTION", `action ${action} is not allow-listed`);
    invariant(incidentId && target && reason, "INVALID_PLAN", "incidentId, target and reason are required");
    invariant(!this.events.some((e) => e.type === "PROPOSED" && e.payload.incidentId === incidentId), "DUPLICATE_PLAN", `incident ${incidentId} already has a plan`);
    return this.#append("PROPOSED", { incidentId, action, target, reason, state: "PENDING" });
  }

  approve(incidentId, approver) {
    invariant(approver, "APPROVER_REQUIRED", "approver is required");
    const plan = this.#plan(incidentId);
    invariant(!this.events.some((e) => e.type === "APPROVED" && e.payload.incidentId === incidentId), "ALREADY_APPROVED", "plan already approved");
    return this.#append("APPROVED", { incidentId, planHash: digest(plan.payload), approver });
  }

  execute(incidentId, observedPlanHash) {
    const plan = this.#plan(incidentId);
    const approval = this.events.findLast((e) => e.type === "APPROVED" && e.payload.incidentId === incidentId);
    invariant(approval, "APPROVAL_REQUIRED", "approved plan is required");
    invariant(approval.payload.planHash === observedPlanHash && observedPlanHash === digest(plan.payload), "STALE_PLAN", "plan changed after approval");
    invariant(!this.events.some((e) => e.type === "EXECUTED" && e.payload.incidentId === incidentId), "ALREADY_EXECUTED", "plan already executed");
    return this.#append("EXECUTED", { incidentId, action: plan.payload.action, target: plan.payload.target });
  }

  verify(incidentId, healthy, evidence) {
    invariant(this.events.some((e) => e.type === "EXECUTED" && e.payload.incidentId === incidentId), "EXECUTION_REQUIRED", "execution evidence is required");
    return this.#append(healthy ? "VERIFIED" : "ROLLBACK_REQUIRED", { incidentId, healthy: Boolean(healthy), evidence });
  }

  planHash(incidentId) { return digest(this.#plan(incidentId).payload); }
  #plan(id) { const p = this.events.find((e) => e.type === "PROPOSED" && e.payload.incidentId === id); invariant(p, "PLAN_NOT_FOUND", `plan ${id} not found`); return p; }
  #append(type, payload, at = new Date().toISOString()) {
    const previousHash = this.events.at(-1)?.hash ?? "GENESIS";
    const event = { sequence: this.events.length + 1, type, payload, at, previousHash };
    event.hash = digest(event);
    this.events.push(event);
    return event;
  }
}

export function verifyLedger(events) {
  let previousHash = "GENESIS";
  return events.every((event, index) => {
    const copy = { sequence: event.sequence, type: event.type, payload: event.payload, at: event.at, previousHash: event.previousHash };
    const valid = event.sequence === index + 1 && event.previousHash === previousHash && event.hash === digest(copy);
    previousHash = event.hash;
    return valid;
  });
}
