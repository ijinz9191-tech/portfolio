# Requirements and metric semantics

Business users need an explicit metric definition and visibility when late data changes a number. Contracts contain metric_id, sequential version, name, description, owner, event_type and aggregation. Definitions are JSON; the project has no graphical authoring UI.

- Timestamps are strict UTC seconds: YYYY-MM-DDTHH:MM:SSZ. Days are [00:00:00, next day 00:00:00) UTC.
- event_count counts accepted unique event IDs of the selected type.
- distinct_users counts distinct actor IDs among those events.
- sum_amount_cents sums integer purchase amounts: gross amount without refunds, fees, tax or FX.
- Read amounts must be zero; purchase amounts are integers from 0 to 1,000,000,000 cents.
- New batches accept events up to seven UTC calendar dates before receipt, and at most five minutes ahead.
- An accepted batch ID with identical ordered payload returns its durable receipt even after the late window. Different content conflicts. Array order is part of the batch fingerprint.
- An identical repeated event ID is a duplicate. Changed content aborts the whole batch, including earlier inserts in the transaction.
- Each inserted day's revision increments once per batch. All metric heads for that day become STALE, including unaffected event types.
- Materialization computes the latest version of every contract atomically. Old versions and runs remain queryable. Each rebuild creates new runs.
- A day never materialized is absent, not implicitly zero. Explicit empty-day materialization returns zero.

## Limits and acceptance

Identifiers: 1-64 ASCII alphanumeric/underscore/hyphen, first character alphanumeric. Text: 1-500 characters. Contract versions: sequential 1-1000. Batch: 1-1000 events and at most 1 MiB canonical JSON; file input is also byte-limited. Queries: at most 31 inclusive dates and 1000 results. No arbitrary SQL expression is accepted.

Tests cover metric values, midnight, atomic invalid/conflicting batches, restart/replay, late-window boundaries, contract versions, stale/rebuild, injected database failure and recovery, input limits, injection attempts, readonly enforcement, actual CLI and HTTP.

Storage volume and contract catalog size are not globally capped. A metric/day input set is loaded into Python memory. This lab is not a large-volume warehouse.
