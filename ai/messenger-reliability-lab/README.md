# Messenger Reliability Lab

Synthetic Node.js 24 lab for the delivery boundary of an enterprise messenger. It demonstrates how a service can reject duplicate or out-of-order message commands, bound per-conversation work, retry missing acknowledgements, move exhausted deliveries to a dead-letter state, and preserve an append-only audit trail across restart snapshots.

This project uses synthetic messages only and does not claim production messenger, cloud, mobile-client or company-system experience.

## Run

```bash
npm test
npm run simulate
npm start
```

The HTTP server binds to `127.0.0.1:3000` by default.

## Capabilities

- Idempotency-key replay and conflict rejection
- Per-conversation monotonic sequence checks
- UTF-8 payload and active-delivery capacity limits
- Explicit `QUEUED → IN_FLIGHT → DELIVERED | DEAD_LETTER` state model
- Acknowledgement timeout with bounded exponential retry
- Append-only audit events with monotonic event sequence
- Snapshot restoration of message, idempotency and sequence state
- Dependency-free loopback HTTP adapter and typed failures

## Verification

The test suite covers normal, duplicate, conflict, capacity, ordering, retry, dead-letter, snapshot, malformed-input and real loopback HTTP paths. See [verification](docs/verification.md), [architecture](docs/architecture.md) and the [runbook](docs/runbook.md).

## Contribution boundary

The applicant supplied the objective, career facts and review decisions. AI-assisted tooling implemented and tested the code and documentation. This lab is portfolio evidence, separate from past employment and production results.
