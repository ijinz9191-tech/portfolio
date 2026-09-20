# Runbook

1. Run `verify.ps1`; do not release if any check fails.
2. Prepare UTF-8 JSON inventory and change files using synthetic or approved data.
3. Execute `python -m infra_change_evidence.cli check --inventory inventory.json --change change.json --db evidence.db` with `src` on `PYTHONPATH`.
4. Exit code `0` means all deterministic checks passed; exit code `2` means the change is blocked.
5. A conflicting reuse of a change ID is an evidence-integrity error. Create a new revision ID after review.
6. To inspect evidence, run the read-only service on a loopback interface. Do not expose the sample store publicly.

Rollback for this reference service is removal of the local SQLite file after export. It never performs the infrastructure change itself.
