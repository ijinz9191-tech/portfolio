import test from "node:test";
import assert from "node:assert/strict";
import { normalizeCluster, summarizeTopology } from "../src/topology.js";
import { scheduleWorkload, releaseWorkload } from "../src/scheduler.js";
import { diagnose } from "../src/diagnostics.js";
import { RemediationLedger, verifyLedger } from "../src/remediation.js";
import { createSnapshot, restoreSnapshot } from "../src/snapshot.js";
import { sampleCluster } from "../src/fixtures.js";

test("동일 NUMA의 PCIe 루트 최소화를 모든 GPU 부분집합과 대조한다", () => {
  let seed = 812;
  const random = (n) => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed % n;
  };
  for (let trial = 0; trial < 100; trial++) {
    const gpus = Array.from({ length: 8 }, (_, i) => ({
      id: `g-${i}`,
      numaId: 0,
      pcieRoot: `root-${random(4)}`,
      memoryGb: 80,
      healthy: true,
      allocatedTo: null,
    }));
    const k = 1 + random(8);
    let minimum = Infinity;
    for (let mask = 1; mask < 256; mask++) {
      const subset = gpus.filter((_, i) => mask & (1 << i));
      if (subset.length === k)
        minimum = Math.min(
          minimum,
          new Set(subset.map((g) => g.pcieRoot)).size,
        );
    }
    const make = (g) => ({
      nodes: [
        {
          id: "node",
          maintenance: false,
          gpus: structuredClone(g),
          nics: [
            { healthy: true, numaId: 0, fabric: "rocev2", capacityGbps: 100 },
          ],
        },
      ],
    });
    const first = scheduleWorkload(make(gpus), { id: "w", gpuCount: k });
    assert.equal(first.evidence.pcieRoots.length, minimum);
    const reversed = scheduleWorkload(make([...gpus].reverse()), {
      id: "w",
      gpuCount: k,
    });
    assert.deepEqual(reversed.gpuIds, first.gpuIds);
  }
});
test("무한대 네트워크와 메모리는 요청 경계에서 거부한다", () => {
  for (const field of ["networkGbps", "minMemoryGb"])
    throwsCode(
      () =>
        scheduleWorkload(cluster(), {
          id: "bad",
          gpuCount: 1,
          [field]: Infinity,
        }),
      "INVALID_REQUEST",
    );
});

const cluster = () => normalizeCluster(sampleCluster());
const throwsCode = (fn, code) => assert.throws(fn, (e) => e.code === code);

test("normalizes and summarizes a synthetic cluster", () => {
  const c = cluster();
  assert.equal(c.nodes.length, 2);
  assert.equal(summarizeTopology(c)[0].healthyFreeGpus, 3);
});
test("rejects duplicate node ids", () => {
  const x = sampleCluster();
  x.nodes.push(structuredClone(x.nodes[0]));
  throwsCode(() => normalizeCluster(x), "DUPLICATE_NODE");
});
test("rejects duplicate GPU ids across nodes", () => {
  const x = sampleCluster();
  x.nodes[1].gpus[0].id = "a0";
  throwsCode(() => normalizeCluster(x), "DUPLICATE_GPU");
});
test("rejects dangling NUMA references", () => {
  const x = sampleCluster();
  x.nodes[0].nics[0].numaId = 99;
  throwsCode(() => normalizeCluster(x), "INVALID_TOPOLOGY");
});
test("places a two-GPU workload on one NUMA domain", () => {
  const p = scheduleWorkload(cluster(), {
    id: "w1",
    gpuCount: 2,
    minMemoryGb: 64,
    networkGbps: 100,
    preferredFabric: "rocev2",
  });
  assert.deepEqual(p.gpuIds, ["a0", "a1"]);
  assert.equal(p.evidence.sameNuma, true);
});
test("enforces GPU memory requirements", () => {
  const p = scheduleWorkload(cluster(), {
    id: "w2",
    gpuCount: 2,
    minMemoryGb: 64,
  });
  assert.equal(p.nodeId, "gpu-node-a");
});
test("rejects impossible network capacity", () =>
  throwsCode(
    () =>
      scheduleWorkload(cluster(), { id: "w3", gpuCount: 1, networkGbps: 1000 }),
    "NO_SAFE_PLACEMENT",
  ));
test("rejects same-NUMA request without enough local GPUs", () =>
  throwsCode(
    () =>
      scheduleWorkload(cluster(), {
        id: "w4",
        gpuCount: 3,
        requireSameNuma: true,
      }),
    "NO_SAFE_PLACEMENT",
  ));
test("allows explicit cross-NUMA placement", () => {
  const p = scheduleWorkload(cluster(), {
    id: "w5",
    gpuCount: 3,
    requireSameNuma: false,
  });
  assert.equal(p.gpuIds.length, 3);
});
test("does not schedule maintenance nodes", () => {
  const c = cluster();
  c.nodes[0].maintenance = true;
  const p = scheduleWorkload(c, { id: "w6", gpuCount: 1 });
  assert.equal(p.nodeId, "gpu-node-b");
});
test("prevents duplicate workload allocation", () => {
  const c = cluster();
  scheduleWorkload(c, { id: "dup", gpuCount: 1 });
  throwsCode(
    () => scheduleWorkload(c, { id: "dup", gpuCount: 1 }),
    "DUPLICATE_WORKLOAD",
  );
});
test("releases all workload GPUs", () => {
  const c = cluster();
  scheduleWorkload(c, { id: "r1", gpuCount: 2 });
  assert.equal(releaseWorkload(c, "r1"), 2);
});
test("diagnoses NUMA and PCIe pressure with evidence", () => {
  const d = diagnose({
    id: "d1",
    numaRemoteRatio: 0.4,
    pcieReplayRate: 0.04,
    pcieThroughputRatio: 0.5,
  });
  assert.equal(d.severity, "HIGH");
  assert.deepEqual(d.causes.map((x) => x.code).sort(), [
    "NUMA_REMOTE_ACCESS",
    "PCIE_PATH_PRESSURE",
  ]);
});
test("diagnoses network saturation and RDMA errors", () => {
  const d = diagnose({
    id: "d2",
    nicRxGbps: 95,
    nicCapacityGbps: 100,
    rdmaErrors: 3,
  });
  assert.equal(d.causes[0].code, "NETWORK_SATURATION_OR_RDMA");
});
test("GPU health is critical", () =>
  assert.equal(diagnose({ id: "d3", eccErrors: 1 }).severity, "CRITICAL"));
test("healthy samples stay healthy", () =>
  assert.equal(
    diagnose({
      id: "d4",
      gpuUtilization: 0.9,
      cpuUtilization: 0.4,
      numaRemoteRatio: 0.02,
    }).severity,
    "HEALTHY",
  ));
test("requires approval before remediation", () => {
  const l = new RemediationLedger();
  l.propose({
    incidentId: "i1",
    action: "CORDON_GPU",
    target: "a0",
    reason: "ECC",
  });
  throwsCode(() => l.execute("i1", l.planHash("i1")), "APPROVAL_REQUIRED");
});
test("executes only an approved immutable plan", () => {
  const l = new RemediationLedger();
  l.propose({
    incidentId: "i2",
    action: "REPIN_WORKLOAD",
    target: "w1",
    reason: "NUMA",
  });
  l.approve("i2", "reviewer");
  const h = l.planHash("i2");
  l.execute("i2", h);
  l.verify("i2", true, { ratio: 0.03 });
  assert.equal(l.events.at(-1).type, "VERIFIED");
  assert.equal(verifyLedger(l.events), true);
});
test("rejects stale approval hashes", () => {
  const l = new RemediationLedger();
  l.propose({
    incidentId: "i3",
    action: "REBALANCE_NIC",
    target: "n1",
    reason: "RDMA",
  });
  l.approve("i3", "reviewer");
  throwsCode(() => l.execute("i3", "bad"), "STALE_PLAN");
});
test("rejects unsafe remediation actions", () => {
  const l = new RemediationLedger();
  throwsCode(
    () =>
      l.propose({
        incidentId: "i4",
        action: "SHELL",
        target: "all",
        reason: "test",
      }),
    "UNSAFE_ACTION",
  );
});
test("detects audit tampering", () => {
  const l = new RemediationLedger();
  l.propose({
    incidentId: "i5",
    action: "CORDON_GPU",
    target: "a0",
    reason: "ECC",
  });
  l.events[0].payload.target = "b0";
  assert.equal(verifyLedger(l.events), false);
});
test("snapshot round-trip preserves source and audit", () => {
  const c = cluster();
  const l = new RemediationLedger();
  l.propose({
    incidentId: "i6",
    action: "CORDON_GPU",
    target: "a0",
    reason: "ECC",
  });
  const restored = restoreSnapshot(createSnapshot(c, l.events));
  assert.equal(restored.cluster.nodes[0].id, "gpu-node-a");
  assert.equal(restored.events.length, 1);
});
test("rejects corrupt snapshots", () => {
  const s = createSnapshot(cluster(), []);
  s.body.cluster.nodes[0].id = "tampered";
  throwsCode(() => restoreSnapshot(s), "CORRUPT_SNAPSHOT");
});
