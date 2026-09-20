# Verification

Run `npm test` from the project root. The tests use only Node.js built-ins and synthetic data.

The required evidence is:

- All tests exit with code 0.
- `npm run simulate` emits a `RELEASABLE` gate, an approved quarantine action and `ledgerValid: true`.
- The published source hash is recorded after the project is merged to `main`.

Tests intentionally fail closed when inventory, pipeline stages, source binding, lease proof, SLO headroom, plan facts, approval or the evidence chain is invalid.
