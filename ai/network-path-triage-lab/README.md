# Network Path Triage Lab

A small, offline diagnostic model for a synthetic Kubernetes service request. It treats DNS, Service selection, EndpointSlice, NetworkPolicy, service mesh and application as an ordered path. The first fresh failed probe is a **candidate** root cause; later failures remain symptoms. An unknown earlier probe blocks a confident diagnosis.

```powershell
python -B triage.py samples/network-policy.json --now 2026-09-29T04:00:00Z
$env:PYTHONPATH='.'
python -B -m unittest discover -s tests -v
```

The fixture reports a `policy` candidate, recommends a source/destination policy check and records a deterministic SHA-256 evidence ID. All observations must have an explicit timestamp and be no more than five minutes old by default. The tool never opens a socket or reads a cluster; it cannot prove a production root cause.

## Provenance

This is a synthetic, AI-assisted portfolio demonstration prepared for a DevOps application. The applicant's earlier work includes deployment operations, monitoring and DMZ transition support; the lab itself is new and is not represented as past employer work. No employer network details or credentials are included.
