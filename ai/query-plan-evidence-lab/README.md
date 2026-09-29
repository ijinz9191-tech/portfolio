# Query Plan Evidence Lab

An offline, deterministic SQLite experiment for investigating a **synthetic** tenant-scoped queue query. It creates 4,000 fixture rows, records the baseline `EXPLAIN QUERY PLAN`, adds a `(tenant_id, status, created_at, order_id)` index, and records the new plan. A witness is accepted only if the baseline scans, the new plan uses the expected covering index, the result rows stay identical, every returned row belongs to the requested tenant **and status**, and the result has bounded, unique, stable `(created_at, order_id)` ordering within the requested time window. A new cursor-page check proves that the next 20 rows neither overlap the first page nor skip a row at the page boundary. The SHA-256 ID binds the query, parameters, both result pages and both plan descriptions.

## Reproduce

```powershell
conda run -p <compatible-environment-prefix> python -B -m unittest discover -s tests -v
conda run -p <compatible-environment-prefix> python -B -m planlab
```

The test suite includes result-change, cross-tenant, wrong-status, missing-index, duplicate-key, changed-order, time-window and cursor-gap failure paths. This is query-plan evidence, **not a measured speedup**. SQLite's optimizer can vary by version. The resource does not access production data and is an AI-built portfolio exercise under the user's direction; it does not claim implementation in an employer system.
