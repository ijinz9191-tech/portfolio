# Runbook

## Message remains `IN_FLIGHT`

1. Read the message and latest audit event.
2. Confirm `nextAttemptAt` and current attempt count.
3. Run `POST /tick` only when the acknowledgement deadline has passed.
4. If the message reaches `DEAD_LETTER`, preserve the audit trail and investigate the recipient or transport before replay.

## `IDEMPOTENCY_CONFLICT`

Do not overwrite the earlier command. Compare the producer request tied to the key and issue a new key only for a distinct business command.

## `CAPACITY_EXCEEDED`

Check unacknowledged deliveries for the conversation. Restore recipient health or drain terminal work; do not raise the limit before understanding the backlog.

## Recovery

Persist a verified `snapshot()` value atomically, restore it with `MessageLedger.restore`, then run focused idempotency, sequence and dispatch checks before accepting traffic.
