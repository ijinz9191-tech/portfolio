# Runbook

1. Run `npm test` and require all tests to pass.
2. Run `npm run demo` and confirm `release.status` is `COMPLETED`, traffic is `100`, and `evidenceValid` is `true`.
3. For a rollback rehearsal, change one demo metric beyond an SLO threshold and verify traffic returns to zero on all clusters.
4. If a release is rejected, inspect the explicit gate reason. Do not lower thresholds merely to pass.
5. Treat a failed evidence-chain verification as corruption. Preserve the artifact and start a new controlled run.

All data is synthetic. Never place credentials, production endpoints, customer data, or real incident logs in this project.
