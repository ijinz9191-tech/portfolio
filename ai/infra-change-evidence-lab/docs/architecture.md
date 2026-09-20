# Architecture

`validate_change` is a pure deterministic gate. It reads a synthetic inventory and change request, expands dependencies into a blast radius, emits named checks and hashes the complete evidence input. `EvidenceStore` persists one immutable decision per change ID in SQLite; an identical retry is idempotent and a changed payload is rejected. The HTTP layer is deliberately read-only.

```text
inventory + change request
        |
 deterministic validator
        |
 checks + blast radius + SHA-256
        |
 immutable SQLite evidence
        |
 read-only HTTP / CLI
```

Fail-closed behavior is used for malformed windows, unknown risk, missing assets, insufficient approvals and incomplete rollback. Synthetic inputs avoid exposing corporate topology or personal data.
