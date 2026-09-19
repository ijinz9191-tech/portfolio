# Metric Contract Lab

A Python + SQLite data product lab: define versioned business metrics, ingest synthetic events atomically, and inspect daily values, freshness and lineage through a read-only HTTP API.

## Run

Python 3.11+; standard library only. From this directory:

```sh
python -B scripts/verify.py
python -B scripts/run_demo.py
python -B -m metriclab init
python -B -m metriclab contract samples/contracts/daily_readers.json
python -B -m metriclab contract samples/contracts/daily_reads.json
python -B -m metriclab contract samples/contracts/daily_revenue_cents.json
python -B -m metriclab ingest sample-initial samples/events.json --at 2026-09-20T12:00:00Z
python -B -m metriclab materialize 2026-09-19 --at 2026-09-20T12:00:00Z
python -B -m metriclab serve --port 4192
```

Open http://127.0.0.1:4192/metrics?start=2026-09-19&end=2026-09-19 in a browser. This is a local JSON API, not a hosted dashboard. Stop with Ctrl+C. The --at option is an explicit fixture clock; omitting it uses system UTC.

## Implemented

- Sequential immutable metric contracts and three allowlisted aggregations.
- Atomic ingestion, durable batch replay, event deduplication and conflict detection.
- UTC day boundaries and late-event invalidation.
- Immutable materialization runs, current heads and input-set SHA-256 lineage.
- Read-only loopback API, CLI and actual SQLite/HTTP/subprocess tests.

| Synthetic metric | Initial | After one late read and rebuild |
|---|---:|---:|
| Daily distinct readers | 2 | 3 |
| Daily accepted reads | 3 | 4 |
| Gross purchase cents | 1299 | 1299 |

These are fixture results, not production business metrics. See [executed demo](artifacts/demo-result.json), [test evidence](artifacts/verification.json), [requirements](docs/requirements.md), [architecture](docs/architecture.md), [runbook](docs/runbook.md) and [verification scope](docs/verification.md). [Project metadata](project.json) is available for portfolio indexing.

This implementation is independent of the existing incident-simulation project: the new behavior concerns analytical contracts, transactional data ingestion, late-arrival quality and metric lineage.

## Contribution and limitations

The user supplied the objective and authorized scope. AI implemented the code, synthetic fixtures, tests and documentation through development tools. This lab does not imply that the user individually wrote it or operated it at an employer.

No external LLM, cloud service or paid infrastructure is called. Only synthetic data is permitted; schema validation is not PII classification. SQLite triggers protect application writes, not a database owner. The HTTP server has no authentication and must remain on loopback. No production SLO, public deployment, streaming broker, scheduler or autonomous AI Agent is claimed.
