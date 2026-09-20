# Runbook

## Validate a release

1. Load the current synthetic inventory and validate IDs, card memory and node state.
2. Reserve cards with a unique lease ID and the release's memory, feature, firmware and node-count constraints.
3. Collect required stage results for every component against the same source revision.
4. Evaluate the release gate with current lease proof and SLO values.
5. Stop on any `BLOCKED` decision. Do not remove a failing stage to make the candidate pass.

## Handle an incident

1. Hash the current release decision and observations.
2. Build a bounded plan from the incident symptoms.
3. Review the plan before producing an approval hash for any mutating step.
4. Execute only allow-listed tools and append every result to the evidence ledger.
5. Verify the complete hash chain before accepting the final state.

## Recovery

- Capacity failure: release stale leases only after ownership is verified; then schedule again.
- Stale facts: rebuild the plan from a fresh evidence snapshot.
- Pipeline or SLO failure: fix the cause and rerun the affected evidence against the unchanged candidate or a new revision.
- Ledger verification failure: reject the run and rebuild evidence from trusted sources.
