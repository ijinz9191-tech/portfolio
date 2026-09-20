# Architecture

`MessageLedger` owns the deterministic domain state. Commands cross one validation boundary, receive a content hash for idempotency, and append audit events only after a valid transition. `createMessengerServer` is a thin Node HTTP adapter; it does not own business state.

```text
HTTP/CLI → validation → idempotency + sequence gate → MessageLedger
                                                   ├─ message state
                                                   ├─ bounded retry / DLQ
                                                   ├─ audit events
                                                   └─ restart snapshot
```

The lab intentionally stays local and dependency-free. A production design would replace the in-memory maps with a transactional store, use an authenticated broker/outbox, define recipient-level acknowledgement semantics, encrypt retained payloads and add SLO-backed telemetry.
