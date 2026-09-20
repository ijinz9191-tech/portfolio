const clamp = (x) => Math.max(0, Math.min(1, x));

export function diagnose(sample) {
  const causes = [];
  const add = (code, confidence, evidence, action) => causes.push({ code, confidence: clamp(confidence), evidence, action });
  if ((sample.numaRemoteRatio ?? 0) >= 0.25) {
    add("NUMA_REMOTE_ACCESS", 0.65 + sample.numaRemoteRatio / 3, { numaRemoteRatio: sample.numaRemoteRatio }, "pin CPU and GPU workers to the local NUMA domain");
  }
  if ((sample.pcieReplayRate ?? 0) >= 0.02 || (sample.pcieThroughputRatio ?? 1) < 0.65) {
    add("PCIE_PATH_PRESSURE", 0.7 + (sample.pcieReplayRate ?? 0), { pcieReplayRate: sample.pcieReplayRate ?? 0, pcieThroughputRatio: sample.pcieThroughputRatio ?? 1 }, "inspect PCIe link width, generation, replay counters and shared root complexes");
  }
  const nicRatio = sample.nicCapacityGbps ? (sample.nicRxGbps ?? 0) / sample.nicCapacityGbps : 0;
  if (nicRatio >= 0.85 || (sample.rdmaErrors ?? 0) > 0) {
    add("NETWORK_SATURATION_OR_RDMA", 0.68 + nicRatio / 4, { nicUtilizationRatio: nicRatio, rdmaErrors: sample.rdmaErrors ?? 0 }, "rebalance NIC affinity and validate RDMA lossless-network settings");
  }
  if ((sample.eccErrors ?? 0) > 0 || sample.gpuHealthy === false) {
    add("GPU_HEALTH", 0.98, { eccErrors: sample.eccErrors ?? 0, gpuHealthy: sample.gpuHealthy !== false }, "cordon the GPU and run vendor health diagnostics");
  }
  if ((sample.gpuUtilization ?? 0) < 0.4 && (sample.cpuUtilization ?? 0) >= 0.85) {
    add("CPU_FEED_BOTTLENECK", 0.8, { gpuUtilization: sample.gpuUtilization, cpuUtilization: sample.cpuUtilization }, "profile preprocessing and increase parallel input workers");
  }
  return {
    sampleId: String(sample.id ?? "unknown"),
    severity: causes.some((x) => x.code === "GPU_HEALTH") ? "CRITICAL" : causes.length >= 2 ? "HIGH" : causes.length ? "MEDIUM" : "HEALTHY",
    causes: causes.sort((a, b) => b.confidence - a.confidence),
    measured: Object.fromEntries(Object.entries(sample).filter(([, v]) => typeof v === "number" || typeof v === "boolean"))
  };
}
