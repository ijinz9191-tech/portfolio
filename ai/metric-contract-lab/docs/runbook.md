# Runbook

Use Python 3.11+ from this directory; no pip install. Follow the README initial commands. Default database: .local/metrics.sqlite. Place --db before a subcommand to override. Only init creates the parent directory.

## Late arrival and recovery

```sh
python -B -m metriclab ingest sample-late samples/late-events.json --at 2026-09-20T12:00:00Z
python -B -m metriclab quality
python -B -m metriclab materialize 2026-09-19 --at 2026-09-20T12:00:00Z
python -B -m metriclab query 2026-09-19 2026-09-19 --metric daily_readers
```

Expect three stale heads before rebuild, zero after, and daily_readers changing from 2 to 3.

| GET route | Result |
|---|---|
| /health | Readonly service status |
| /contracts | All contract versions and hashes |
| /metrics?start=YYYY-MM-DD&end=YYYY-MM-DD&metric=optional_id | Values, versions, run IDs, freshness |
| /quality | Batch/event counts, duplicates, late events, stale heads |
| /lineage/positive_run_id | Stored run, exact contract, hashes and selection |

Host must be localhost or 127.0.0.1 with the server port. Query keys/duplicates are checked. POST/PUT/PATCH/DELETE return 405. There is no authentication, TLS, public service URL or CORS configuration.

## Exceptions

- EVENT_ID_CONFLICT: investigate synthetic source data; do not rewrite accepted evidence.
- BATCH_ID_CONFLICT: an ID was reused with changed content. Assign a new ID only for a genuinely new batch.
- LATE_WINDOW_EXCEEDED: the --at override is for fixture replay, not disguising live late events.
- STALE: rematerialize the affected day and retain prior run IDs.
- DATABASE_ERROR or HTTP 503: inspect local disk/permissions/database health. Last committed state is the recovery point.
- Definition correction: register the next contract version and rebuild.

Stop with Ctrl+C and restart against the same database. Accepted batch replay remains durable. scripts/run_demo.py uses and cleans an isolated TemporaryDirectory. The CLI database persists intentionally; stop all processes before manually removing your own .local files. Never point it at production or candidate data.

No backup service, migration engine, retry scheduler or measured SLO is implemented.
