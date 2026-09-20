# Requirements

## Input and result contract

POST /infer accepts only application/x-www-form-urlencoded with a single features field containing 1-16 comma-separated finite doubles within [-100,100]. The body is capped at 1024 bytes. Idempotency-Key must contain 1-64 ASCII letters, digits, underscore or hyphen.

The deterministic-v1 model returns sigmoid(mean(features)). This is a synthetic score with no risk, payment or business interpretation.

A successful admission returns 202 and a job ID. A completed cache hit returns 200. GET /jobs/id exposes QUEUED, RUNNING, SUCCEEDED, FAILED or CANCELLED. Failed results never enter the cache.

## State and limits

Same retained key and same canonical feature payload returns the existing job. Changed payload returns 409. Signed zero is normalized. Different keys may reuse a successful feature-cache entry. Concurrent different keys are not single-flight coalesced.

Completed records expire after TTL; active work remains reserved. Expired keys may be used again. There is no durable deduplication. Record capacity and queue capacity separately return 429; rejected queue entries release their key reservation.

Default limits: one worker, queue 8, records 128, TTL 60 seconds, one retry (at most two calls), failure threshold 3, breaker cooldown 5 seconds. Tests inject smaller values and a logical clock.

## Failure and recovery

Circuit failure counts track failed model attempts. Open circuits reject model execution without calling the model. After cooldown, one probe is allowed; success closes, failure reopens. Retries are immediate and bounded; no jitter/backoff scheduler is claimed. A previously successful cached value can still be served while the breaker is open.

Shutdown rejects new admission, waits for accepted work and interrupts/cancels remaining jobs at the deadline. Cooperative model interruption is required. A Java thread cannot safely kill an uncooperative model. Restart starts an empty service; no old job is silently claimed as recovered.
