import { invariant } from "./errors.js";

function candidatesForNode(node, request) {
  if (node.maintenance) return [];
  const free = node.gpus.filter((g) => g.healthy && !g.allocatedTo && g.memoryGb >= request.minMemoryGb);
  const groups = request.requireSameNuma
    ? [...new Set(free.map((g) => g.numaId))].map((numaId) => free.filter((g) => g.numaId === numaId))
    : [free];
  return groups.filter((group) => group.length >= request.gpuCount).map((group) => {
    const selected = group.slice(0, request.gpuCount);
    const numaIds = [...new Set(selected.map((g) => g.numaId))];
    const compatibleNics = node.nics.filter((n) => n.healthy && numaIds.includes(n.numaId));
    const preferred = compatibleNics.filter((n) => !request.preferredFabric || n.fabric === request.preferredFabric);
    const network = (preferred.length ? preferred : compatibleNics).reduce((sum, n) => sum + n.capacityGbps, 0);
    const rootCount = new Set(selected.map((g) => g.pcieRoot)).size;
    const score = network * 10 - rootCount * 4 - (numaIds.length - 1) * 100;
    return { node, selected, numaIds, network, rootCount, score };
  });
}

export function scheduleWorkload(cluster, rawRequest) {
  const request = {
    id: String(rawRequest?.id ?? ""),
    gpuCount: Number(rawRequest?.gpuCount),
    minMemoryGb: Number(rawRequest?.minMemoryGb ?? 0),
    networkGbps: Number(rawRequest?.networkGbps ?? 0),
    requireSameNuma: rawRequest?.requireSameNuma !== false,
    preferredFabric: rawRequest?.preferredFabric ? String(rawRequest.preferredFabric) : null
  };
  invariant(request.id, "INVALID_REQUEST", "workload id is required");
  invariant(Number.isInteger(request.gpuCount) && request.gpuCount > 0, "INVALID_REQUEST", "gpuCount must be a positive integer");
  invariant(request.minMemoryGb >= 0 && request.networkGbps >= 0, "INVALID_REQUEST", "capacity requirements must be non-negative");
  invariant(!cluster.nodes.some((n) => n.gpus.some((g) => g.allocatedTo === request.id)), "DUPLICATE_WORKLOAD", `workload ${request.id} is already allocated`);

  const candidates = cluster.nodes.flatMap((node) => candidatesForNode(node, request))
    .filter((candidate) => candidate.network >= request.networkGbps)
    .sort((a, b) => b.score - a.score || a.node.id.localeCompare(b.node.id));
  invariant(candidates.length > 0, "NO_SAFE_PLACEMENT", "no placement satisfies topology and capacity constraints", { request });
  const winner = candidates[0];
  for (const gpu of winner.selected) gpu.allocatedTo = request.id;
  return {
    workloadId: request.id,
    nodeId: winner.node.id,
    gpuIds: winner.selected.map((g) => g.id),
    numaIds: winner.numaIds,
    networkGbps: winner.network,
    score: winner.score,
    evidence: {
      sameNuma: winner.numaIds.length === 1,
      pcieRoots: [...new Set(winner.selected.map((g) => g.pcieRoot))],
      preferredFabric: request.preferredFabric,
      candidateCount: candidates.length
    }
  };
}

export function releaseWorkload(cluster, workloadId) {
  let released = 0;
  for (const node of cluster.nodes) for (const gpu of node.gpus) {
    if (gpu.allocatedTo === workloadId) { gpu.allocatedTo = null; released += 1; }
  }
  invariant(released > 0, "WORKLOAD_NOT_FOUND", `workload ${workloadId} has no allocation`);
  return released;
}
