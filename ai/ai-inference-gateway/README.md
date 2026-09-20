# AI Inference Gateway

Java 21 standard-library implementation of local inference-serving controls: bounded asynchronous admission, idempotency, TTL result caching, retry and Circuit Breaker, job polling and operational counters.

The model is a deterministic synthetic function, not a trained model or external AI API. This project demonstrates serving behavior around model calls.

## Build, verify, run

JDK 21 (java and javac on PATH), PowerShell 7 for the evidence script. No dependency downloads.

```powershell
./verify.ps1
java -cp .build lab.Gateway 4193
```

```sh
curl -i -X POST http://localhost:4193/infer -H "Content-Type: application/x-www-form-urlencoded" -H "Idempotency-Key: demo-001" --data "features=0.2,-0.1,0.7"
curl http://localhost:4193/jobs/REPLACE_WITH_RETURNED_ID
curl http://localhost:4193/metrics
```

Poll the returned job ID until SUCCEEDED, FAILED or CANCELLED. Stop with Ctrl+C. The service binds loopback only. It has no authentication, production deployment or browser UI.

## Implemented behavior

- Single model worker, bounded queue and explicit 429 backpressure.
- Immutable feature snapshot, idempotency conflict detection and bounded retained job records.
- TTL response cache keyed by canonical feature fingerprint; active requests are never evicted.
- Bounded retry, Circuit Breaker open/cooldown/probe/recovery and sanitized model errors.
- Graceful draining, bounded shutdown wait, cancellation of cooperative work.
- Real HTTP tests and controlled failure scenarios.

See [requirements](docs/requirements.md), [architecture](docs/architecture.md), [runbook](docs/runbook.md), [verification](docs/verification.md) and [actual test evidence](artifacts/verification.json). [project.json](project.json) supplies portfolio metadata.

## Contribution and limitations

The user provided the portfolio goal and authorized scope. AI implemented the code, tests, synthetic sample and documentation using development tools. This project is not claimed as the user's employer production system or individually written code.

All state is in memory. Restart loses jobs, cache, counters and idempotency history. Exactly-once processing across restart is not guaranteed. There is no real model training, cloud GPU, durable broker, authentication, distributed coordination or production throughput/SLO claim. Only synthetic features should be sent.
