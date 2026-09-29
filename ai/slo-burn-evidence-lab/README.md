# SLO Burn Evidence Lab

An offline Python 3.11+ decision aid for a **synthetic request-error SLI**. It checks complete, contiguous five-minute buckets for two multiwindow alert policies: 5 minutes and 1 hour above 14.4× error-budget burn, or 30 minutes and 6 hours above 6×. The windows are request weighted; missing and stale evidence is rejected.

## Reproduce

```powershell
conda run -p <compatible-environment-prefix> python -B -m unittest discover -s tests -v
conda run -p <compatible-environment-prefix> python -B -m burnlab samples/sustained.json --now 2026-09-29T00:01:00Z
```

The `--now` value is a fixture clock. Omit it with fresh data. The CLI exits 0 for an assessed decision and 2 for rejected evidence. `NO_PAGE` with zero traffic means insufficient error observations, not proof of health. The SHA-256 ID binds the normalized latest six-hour bucket set to the output.

This lab does not query Prometheus, page humans, prove an SLO is met, or represent any employer system. It is an AI-built, synthetic portfolio resource under the user's direction, not a claim of prior production implementation.
