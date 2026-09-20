# Verification contract

The project is verified only when `npm run verify` exits 0 on the published source revision. Tests cover configuration, authorization, error budget, identity, duplicate rejection, progressive traffic, multi-cluster consistency, four independent rollback causes, malformed telemetry, terminal-state protection, manual rollback, missing releases, and evidence integrity/tamper detection.

The generated `artifacts/verification.json` records the actual runtime, test count, command, source-manifest hash, and execution time. README claims must match that artifact and the published commit.
