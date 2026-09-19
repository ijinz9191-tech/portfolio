# Project Index

Existing projects are preserved. This index is separate from the original [CareerOps guide](README.md). It contains public engineering material, not recruitment history.

| Project | Problem and implementation | Validation | Source / fixed version |
|---|---|---|---|
| Incident Replay Lab | Synthetic service fault propagation, Runbook actions, SQLite snapshots, replay and postmortem export. Node.js 24, HTTP API, SQLite. | Normal and failure-path tests are included. Test execution status must be checked against an actual run record; listing tests alone does not establish PASS. Existing project; no new application ownership assigned. | [Latest source](sre/README.md) · [Fixed source](https://github.com/ijinz9191-tech/portfolio/tree/7353bfe2cf80d6cd7cb976969e0a9a3c17c407bd/ai/sre) · [Tests](https://github.com/ijinz9191-tech/portfolio/tree/7353bfe2cf80d6cd7cb976969e0a9a3c17c407bd/ai/sre/tests) |
| Metric Contract Lab | New Python/SQLite implementation: immutable versioned metric contracts, atomic synthetic event ingestion, batch replay and conflict detection, late-event freshness, daily materialization and SHA-256 lineage. Distinct from incident simulation. | 18 local tests PASS in the current execution record, including real temporary SQLite, loopback HTTP, CLI, rollback/recovery, restart and malformed JSON type handling. Synthetic data only; no public deployment or production claims. | [Latest source](metric-contract-lab/README.md) · [Verification](metric-contract-lab/artifacts/verification.json) · [Architecture](metric-contract-lab/docs/architecture.md). Published snapshot commit pending remote verification. |

The source URL is not a running service URL. All scenario data are synthetic. Public site source: [Engineering Portfolio](../site/README.md); deployment URL pending verification.
