# Runbook

1. Run `npm test` and stop if any invariant, negative-path or integrity test fails.
2. Run `npm run simulate` to inspect the selected GPUs, diagnosis evidence and audit chain.
3. For a `GPU_HEALTH` diagnosis, cordon the synthetic GPU and validate capacity before replacement.
4. For `NUMA_REMOTE_ACCESS`, compare worker affinity with GPU and NIC NUMA domains before proposing a repin.
5. For `PCIE_PATH_PRESSURE`, inspect link width/generation, replay counters and shared PCIe roots.
6. For `NETWORK_SATURATION_OR_RDMA`, validate NIC affinity, utilization, errors and lossless-network configuration.
7. Never execute a remediation whose approval hash differs from the current plan.
8. Record the post-change signal and mark rollback required when health does not recover.

All scenarios are synthetic and safe for local execution.
