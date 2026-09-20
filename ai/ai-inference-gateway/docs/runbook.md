# Runbook

Run ./verify.ps1 from PowerShell 7 with JDK 21 on PATH. It compiles source and tests into ignored .build, executes the test program, and writes artifacts/verification.json. Start with java -cp .build lab.Gateway 4193.

## API

| Method and route | Behavior |
|---|---|
| POST /infer | Validate features, key and admission; returns job snapshot |
| GET /jobs/{id} | Current retained result; 404 when unknown or expired |
| GET /metrics | Counts, queue depth, records, cache size and circuit state |
| GET /health | Liveness identity only; does not certify model readiness |

Query parameters are rejected. Host must be localhost or 127.0.0.1 with the bound port. JSON responses are no-store and nosniff. No raw feature vectors or provider exceptions appear in results.

## Diagnose

- 400: malformed key/features/body; fix the request without changing an accepted key's meaning.
- 409: retained key already binds different features.
- 429 QUEUE_FULL: retry later with the same unchanged key; reservation was rolled back.
- 429 RECORD_CAPACITY: wait for completed-record TTL expiry.
- FAILED CIRCUIT_OPEN: inspect model failures and cooldown. Failed jobs remain idempotent until TTL.
- 503 SHUTTING_DOWN: instance is draining.
- 404: unknown, expired, or lost across restart. Do not imply durable processing.

Ctrl+C stops HTTP and drains model work for up to three seconds, then requests interruption and marks unfinished jobs CANCELLED. A non-cooperative model may continue running; this demo model does not perform blocking external work.

There are no remote resources to clean up. .build contains generated classes and can be removed when no Java process is using them. Artifacts contain synthetic test names/results only. Do not send candidate documents, payment data or secrets to this unauthenticated local demonstration.
