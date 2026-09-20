# Architecture

```text
Loopback HttpServer -> validate -> idempotency/TTL lookup -> bounded worker queue
                                                        -> retry/circuit -> synthetic model
GET jobs/metrics <- synchronized in-memory state <- result/cache/counters
```

Java HttpServer provides the small HTTP surface. The HTTP dispatcher is serialized; model execution runs on a separate single-worker ThreadPoolExecutor with ArrayBlockingQueue. This demonstrates asynchronous model admission, not a high-throughput HTTP server.

Synchronized state transitions serialize idempotency reservation and admission. A queue rejection rolls the reservation back. Input arrays are cloned before queueing and before invoking the model. Result objects are immutable snapshots.

Model attempts receive no request headers, credentials or network client. Exceptions are translated into fixed public error codes. SHA-256 fingerprints bind canonical numeric arrays, not a proof of model correctness.

Circuit state uses a cooldown deadline and one half-open probe. TTL and cooldown use an injectable millisecond clock; production uses wall time, so clock adjustments can affect durations. This is explicitly not a distributed circuit breaker.

State and result-cache sizes are bounded by retained job admission and TTL pruning. No persistence, multi-instance coordination or durable queue exists. Local ownership is a deployment restriction, not authentication. HTTP request parsing remains susceptible to slow local clients; production hardening would need request deadlines, authenticated routing and a different server deployment.

The implementation is a new inference-serving project, separate from metric-contract ingestion and incident simulation.
