# Kubernetes Capacity Budget Lab

This offline Python 3.11+ tool estimates the cheapest **uniform** node shape for a Kubernetes workload during a rolling release. It combines p95 observed demand, CPU utilization target, memory headroom, rollout surge, per-node pod limits, fixed system reserve, minimum zone diversity, and an explicit monthly cost ceiling. It refuses stale telemetry and infeasible plans.

## Why this resource is different

The existing Service Mesh Release Safety Lab decides whether to advance or roll back a release from SLO telemetry. This tool answers a different question **before** release: can the requested replica count plus surge fit across zones within a cost ceiling? A successful rollout gate cannot compensate for insufficient scheduled capacity.

## Reproduce

```powershell
conda run -p <compatible-environment-prefix> python -m unittest discover -s tests -v
conda run -p <compatible-environment-prefix> python -m capacitylab samples/rollout.json --now 2026-09-29T00:01:00Z
```

The fixed `--now` is for the synthetic fixture only. In operational use, omit it so the tool checks the current clock. The CLI prints JSON and exits 0 for a feasible plan; invalid or stale inputs print `REJECTED` to stderr and exit 2. No cloud credentials or network access are used.

## Decision model and limits

- Per-pod effective CPU is the greater of requested CPU and p95 observed CPU divided by the utilization target. Effective memory is the greater of requested memory and observed p95 memory plus headroom.
- Per-node pod capacity is the smallest of CPU capacity after system reserve, memory capacity after reserve, and maximum pod count. At least one node is placed in each required zone; remaining nodes are distributed round-robin.
- Cost assumes a 730-hour month and only node hourly price. It excludes storage, network, discounts, autoscaler behavior and live placement constraints. It picks one node shape; it does not optimize mixed pools.
- This is a synthetic planning aid. It neither connects to Kubernetes nor claims production operation, real cost savings, or work performed for Toss.
