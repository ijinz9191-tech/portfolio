export function sampleCluster() {
  return {
    nodes: [
      {
        id: "gpu-node-a", numa: [{ id: 0 }, { id: 1 }],
        nics: [{ id: "mlx-a", numaId: 0, fabric: "rocev2", capacityGbps: 200 }, { id: "eth-a", numaId: 1, fabric: "ethernet", capacityGbps: 25 }],
        gpus: [
          { id: "a0", model: "synthetic-80g", numaId: 0, pcieRoot: "0000:20", memoryGb: 80 },
          { id: "a1", model: "synthetic-80g", numaId: 0, pcieRoot: "0000:20", memoryGb: 80 },
          { id: "a2", model: "synthetic-80g", numaId: 1, pcieRoot: "0000:a0", memoryGb: 80 }
        ]
      },
      {
        id: "gpu-node-b", numa: [{ id: 0 }],
        nics: [{ id: "mlx-b", numaId: 0, fabric: "infiniband", capacityGbps: 100 }],
        gpus: [
          { id: "b0", model: "synthetic-48g", numaId: 0, pcieRoot: "0000:40", memoryGb: 48 },
          { id: "b1", model: "synthetic-48g", numaId: 0, pcieRoot: "0000:41", memoryGb: 48 }
        ]
      }
    ]
  };
}
