# Architecture

## Components

1. `inventory.js` validates nodes/cards and issues immutable lease evidence after constrained scheduling.
2. `pipeline-gate.js` verifies all required stages, source revision, lease proof and SLO headroom.
3. `agentic-runner.js` creates deterministic plans from evidence. Mutating steps require a hash bound to the exact plan and incident.
4. `evidence-ledger.js` stores hash-linked observations and action results.

## Trust boundaries

- Fixtures are synthetic and contain no employer data.
- The agent cannot add tools outside a fixed allow-list.
- An approval is scoped to one plan hash and cannot approve a changed plan.
- Release evidence must match the exact candidate revision and resource request.
- This lab does not execute shell commands, reach external infrastructure or expose credentials.

## New implementation

This project adds a multi-component SDLC gate and approval-bound agent workflow. It does not reuse the placement diagnosis or remediation model from earlier topology projects.
