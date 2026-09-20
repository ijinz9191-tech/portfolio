# Verification

Run `npm test` from the project root. The suite uses Node's built-in test runner without per-file subprocess isolation so it also runs in restricted Windows environments, while every test still receives a separate `node:test` context. The HTTP checks use a real loopback server. A passing record must state the Node version, command, exit code, pass/fail counts, source hash and execution time. Generated documentation alone is not test evidence.

Required failure paths include idempotency conflict, unexpected sequence, payload and capacity limits, early acknowledgement, bounded retry to dead-letter, invalid snapshot, malformed JSON and unknown route.
