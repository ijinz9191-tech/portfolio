# Agentic SDLC Control Plane

A dependency-free Node.js 24 control-plane lab for synthetic NPU fleet inventory, resource scheduling, multi-component release gates and approval-bound agentic remediation.

The project uses synthetic NPU cards, pipeline results, service signals and incidents. It does not claim production NPU, bare-metal, Slurm, OpenStack or Rebellions experience.

## Run

```bash
npm test
npm run simulate
```

## Problem

Driver, firmware and collective-communication components must be built and tested together while scarce accelerator resources are reserved safely. An AI-assisted incident workflow also needs strict tool boundaries, current evidence and explicit approval before it mutates fleet state.

## Capabilities

- Validates NPU nodes and globally unique card inventory
- Reserves healthy cards by memory, feature, firmware and maximum-node constraints
- Rejects stale leases, degraded capacity and duplicate allocation
- Gates driver, firmware and collective-library releases on build, unit, integration, hardware-simulation and security evidence
- Binds every component result to the candidate source revision and current fleet lease
- Applies SLO error-budget and p95 latency gates
- Builds deterministic, bounded agent plans with an explicit tool allow-list
- Requires a plan-bound approval hash for quarantine or rollback actions
- Stores tool results in a tamper-evident evidence ledger

## Verification

The suite covers inventory corruption, capacity constraints, degraded cards, firmware mismatch, duplicate leases, release-stage failures, stale source and lease evidence, SLO breaches, approval enforcement, stale facts, tool allow-list enforcement and audit tampering.

See `docs/architecture.md`, `docs/runbook.md` and `docs/verification.md`.

## Contribution boundary

The applicant supplied the career objective, source facts and review decisions. AI-assisted tooling implemented and tested this code and documentation. This CareerOps project is portfolio evidence and is separate from employment or production results.
