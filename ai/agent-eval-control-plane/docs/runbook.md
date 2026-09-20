# Runbook

## Verify

```powershell
.\verify.ps1
```

## Inspect one synthetic demo

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m agent_eval_control_plane.cli demo --db artifacts/demo.sqlite
python -m agent_eval_control_plane.cli gate --db artifacts/demo.sqlite --suite booking-agent-v1
```

## Read-only report server

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m agent_eval_control_plane.cli serve --db artifacts/demo.sqlite --port 8080
```

Available endpoints are `GET /health`, `GET /runs/<run-id>` and `GET /suites/<suite>/gate`. Writes through HTTP return `405`.

## Recovery

Run and case IDs are idempotent. Reusing an ID with different content fails instead of replacing evidence. Remove only disposable local demo databases when a clean fixture run is required; published verification metadata remains immutable.
