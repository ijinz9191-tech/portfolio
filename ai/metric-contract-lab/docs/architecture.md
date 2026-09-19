# Architecture

```text
Synthetic JSON -> validation -> transaction -> events + batch receipt + day revision
Contract JSON -> validated enum -> immutable contract version
latest contracts + UTC day inputs -> transaction -> immutable runs + current heads
readonly SQLite connection -> loopback GET API -> metrics / quality / lineage
```

| Table | Role |
|---|---|
| contracts | Immutable JSON definition and hash by metric/version |
| events | Immutable accepted event, content hash and event/receive times |
| batches | Durable receipt and ordered payload hash |
| day_revisions | Revision per affected day |
| metric_runs | Immutable value, input count, revision and hashes |
| metric_heads | Current run by metric/version/day |

BEGIN IMMEDIATE, WAL and foreign keys keep writes within a single SQLite transaction. A mid-batch conflict rolls back earlier inserts. Metric runs and heads commit together. HTTP requests open mode=ro connections with query_only enabled.

SQL selects typed inputs and joins heads to revisions. Python implements the three validated aggregation operations. No contract text is evaluated as SQL or code.

Lineage hashes sorted [event ID, content hash] pairs. Each run retains exact contract hash/version, selected day/type, input count and revision. The API returns no raw actor IDs. It stores an input-set fingerprint, not a historical input ID list or independent attestation. Database ownership can bypass triggers.

Day-level invalidation deliberately over-invalidates unaffected metric types. Rebuild is explicit, not scheduled. A synthetic failure-injection test checks that partial materialization leaves all previous heads intact.

The standard-library server is local, single-threaded and unauthenticated. Host checks reduce DNS-rebinding exposure but do not create an authorization boundary.
