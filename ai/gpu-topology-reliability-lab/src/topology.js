import { invariant } from "./errors.js";

const nonNegative = (value, label) => {
  invariant(Number.isFinite(value) && value >= 0, "INVALID_TOPOLOGY", `${label} must be non-negative`);
  return value;
};

export function normalizeCluster(input) {
  invariant(input && Array.isArray(input.nodes) && input.nodes.length > 0, "INVALID_TOPOLOGY", "nodes are required");
  const nodeIds = new Set();
  const gpuIds = new Set();
  const nodes = input.nodes.map((raw) => {
    invariant(raw && typeof raw.id === "string" && raw.id.trim(), "INVALID_TOPOLOGY", "node id is required");
    invariant(!nodeIds.has(raw.id), "DUPLICATE_NODE", `duplicate node ${raw.id}`);
    nodeIds.add(raw.id);
    const numaIds = new Set((raw.numa ?? []).map((x) => x.id));
    invariant(numaIds.size === (raw.numa ?? []).length && numaIds.size > 0, "INVALID_TOPOLOGY", `node ${raw.id} needs unique NUMA domains`);
    const nics = (raw.nics ?? []).map((nic) => ({
      id: String(nic.id),
      numaId: nic.numaId,
      fabric: String(nic.fabric ?? "ethernet"),
      capacityGbps: nonNegative(nic.capacityGbps, `nic ${nic.id} capacity`),
      healthy: nic.healthy !== false
    }));
    for (const nic of nics) invariant(numaIds.has(nic.numaId), "INVALID_TOPOLOGY", `NIC ${nic.id} references unknown NUMA`);
    const gpus = (raw.gpus ?? []).map((gpu) => {
      const id = String(gpu.id);
      invariant(!gpuIds.has(id), "DUPLICATE_GPU", `duplicate GPU ${id}`);
      gpuIds.add(id);
      invariant(numaIds.has(gpu.numaId), "INVALID_TOPOLOGY", `GPU ${id} references unknown NUMA`);
      return {
        id,
        model: String(gpu.model ?? "unknown"),
        numaId: gpu.numaId,
        pcieRoot: String(gpu.pcieRoot ?? "unknown"),
        memoryGb: nonNegative(gpu.memoryGb, `gpu ${id} memory`),
        healthy: gpu.healthy !== false,
        allocatedTo: gpu.allocatedTo ?? null
      };
    });
    return { id: raw.id, numa: [...numaIds], nics, gpus, maintenance: raw.maintenance === true };
  });
  return { version: 1, nodes };
}

export function summarizeTopology(cluster) {
  return cluster.nodes.map((node) => ({
    nodeId: node.id,
    totalGpus: node.gpus.length,
    healthyFreeGpus: node.gpus.filter((g) => g.healthy && !g.allocatedTo).length,
    healthyNetworkGbps: node.nics.filter((n) => n.healthy).reduce((sum, n) => sum + n.capacityGbps, 0),
    maintenance: node.maintenance
  }));
}
