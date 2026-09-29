# Incident Dependency Triage Lab

An offline Python tool for reviewing a synthetic multi-service incident. It orders observed failures dependency-first, identifies failed services with no failed dependency as *candidates* for first investigation, and shows possible downstream impact. A healthy downstream probe remains explicit counterevidence rather than being converted into a failure.

```powershell
conda run -n base python -B -m unittest discover -s tests -v
conda run -n base python -B triage.py samples/incident.json
```

The input is a bounded directed acyclic graph. Unknown dependencies, cycles, duplicate services, missing evidence and invalid health values fail closed. A SHA-256 digest binds the canonical snapshot to the result. The output is a diagnostic review plan, not a proven root cause or an instruction to automatically restart production services.

All data are synthetic. This lab does not use any employer systems, live telemetry, or confidential incident data. It is a new resource for reasoning about SRE incident dependencies, separate from the existing Incident Replay Lab's fault simulation and runbook state machine.
