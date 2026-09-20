# GPU Topology Reliability Lab

A dependency-free Node.js 24 lab that models topology-aware placement, evidence-based performance diagnosis and approval-bound remediation for a synthetic GPU cluster.

The project uses synthetic hardware, metrics and incidents. It does not claim production GPU, NPU, RDMA, data-center or employer experience.

## Run

```bash
npm test
npm run simulate
```

## Capabilities

- Validates node, GPU, NUMA, PCIe-root and NIC topology
- Places GPU workloads with memory, network and same-NUMA constraints
- Detects impossible or unsafe placements before mutation
- Diagnoses NUMA remote access, PCIe pressure, NIC/RDMA saturation, CPU feed bottlenecks and GPU health signals
- Requires an allow-listed plan, independent approval hash and post-change verification before remediation can complete
- Preserves a hash-linked audit ledger and integrity-checked snapshots

## Verification

The test suite covers normal placement, capacity constraints, topology corruption, duplicate allocation, maintenance mode, NUMA/PCIe/RDMA diagnosis, approval and stale-plan controls, audit tampering and snapshot corruption. See `docs/verification.md` and `docs/runbook.md`.

## Contribution boundary

The applicant supplied the career objective, facts and review decisions. AI-assisted tooling implemented and tested the code and documentation. This CareerOps project is portfolio evidence and is separate from employment or production results.
