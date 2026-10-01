import test from "node:test";
import assert from "node:assert/strict";
import { ReleaseController } from "../src/controller.js";

test("동일 관측 재사용과 일부 클러스터 역행은 상태·원장을 변경하지 않는다", () => {
  const c = clusterMode();
  start(c);
  c.observe("r1", perCluster());
  const before = c.get("r1"),
    evidence = c.ledger.list();
  assert.throws(() => c.observe("r1", perCluster()), /must advance/);
  const mixed = perCluster();
  mixed.clusterSamples.a.observedAt = "2026-09-29T00:00:00.500Z";
  assert.throws(() => c.observe("r1", mixed), /must advance/);
  assert.deepEqual(c.get("r1"), before);
  assert.deepEqual(c.ledger.list(), evidence);
  mixed.clusterSamples.b.observedAt = "2026-09-29T00:00:00.500Z";
  assert.equal(c.observe("r1", mixed).trafficPercent, 25);
});
test("NaN 단계는 승격 정책에 들어갈 수 없다", () =>
  assert.throws(() => make({ steps: [NaN, 100] }), /steps/));

const healthy = { errorRate: 0.002, p99LatencyMs: 180, saturation: 0.55 };
const make = (overrides = {}) =>
  new ReleaseController({
    clusters: ["a", "b"],
    approvalToken: "ok",
    ...overrides,
  });
const start = (controller, overrides = {}) =>
  controller.start({
    releaseId: "r1",
    service: "payments",
    version: "2.0.0",
    requester: "platform",
    approvalToken: "ok",
    ...overrides,
  });

test("requires two unique clusters", () =>
  assert.throws(
    () => new ReleaseController({ clusters: ["a"], approvalToken: "ok" }),
    /two unique/,
  ));
test("requires an approval token", () =>
  assert.throws(
    () => new ReleaseController({ clusters: ["a", "b"] }),
    /approvalToken/,
  ));
test("rejects invalid steps", () =>
  assert.throws(() => make({ steps: [20, 10, 100] }), /steps/));
test("rejects an invalid error budget", () =>
  assert.throws(() => make({ errorBudgetRemaining: 2 }), /errorBudget/));
test("rejects missing release identity", () =>
  assert.throws(() => make().start({}), /identity/));
test("rejects unauthorized release", () =>
  assert.throws(() => start(make(), { approvalToken: "no" }), /approval/));
test("rejects release below error budget", () =>
  assert.throws(() => start(make({ errorBudgetRemaining: 0.1 })), /budget/));
test("rejects duplicate release identifiers", () => {
  const c = make();
  start(c);
  assert.throws(() => start(c), /already/);
});
test("advances a healthy release through all mesh weights", () => {
  const c = make();
  start(c);
  for (let i = 0; i < 4; i += 1) c.observe("r1", healthy);
  assert.equal(c.get("r1").status, "COMPLETED");
  assert.equal(c.get("r1").trafficPercent, 100);
});
test("applies the same traffic policy to every cluster", () => {
  const c = make();
  start(c);
  const r = c.observe("r1", healthy);
  assert.deepEqual(
    Object.values(r.clusters).map((x) => x.trafficPercent),
    [5, 5],
  );
});
test("rolls back on error-rate breach", () => {
  const c = make();
  start(c);
  const r = c.observe("r1", { ...healthy, errorRate: 0.02 });
  assert.equal(r.rollbackReason, "error rate SLO breach");
});
test("rolls back on p99 latency breach", () => {
  const c = make();
  start(c);
  assert.equal(
    c.observe("r1", { ...healthy, p99LatencyMs: 501 }).status,
    "ROLLED_BACK",
  );
});
test("rolls back on saturation breach", () => {
  const c = make();
  start(c);
  assert.match(
    c.observe("r1", { ...healthy, saturation: 0.9 }).rollbackReason,
    /saturation/,
  );
});
test("rolls back on security policy violation", () => {
  const c = make();
  start(c);
  assert.match(
    c.observe("r1", { ...healthy, securityViolations: 1 }).rollbackReason,
    /security/,
  );
});
test("rejects malformed metrics", () => {
  const c = make();
  start(c);
  assert.throws(
    () => c.observe("r1", { ...healthy, errorRate: -1 }),
    /errorRate/,
  );
});
test("prevents changes after completion", () => {
  const c = make();
  start(c);
  for (let i = 0; i < 4; i += 1) c.observe("r1", healthy);
  assert.throws(() => c.observe("r1", healthy), /COMPLETED/);
});
test("supports operator rollback", () => {
  const c = make();
  start(c);
  assert.equal(c.rollback("r1", "maintenance").rollbackReason, "maintenance");
});
test("rejects unknown releases", () =>
  assert.throws(() => make().get("missing"), /not found/));
test("creates a valid hash-chained evidence ledger", () => {
  const c = make();
  start(c);
  c.observe("r1", healthy);
  assert.equal(c.ledger.verify(), true);
});
test("detects evidence tampering", () => {
  const c = make();
  start(c);
  const events = c.ledger.list();
  events[0].payload.version = "tampered";
  assert.equal(c.ledger.verify(events), false);
});

const observedAt = "2026-09-29T00:00:00.000Z";
const clusterMode = (overrides = {}) =>
  make({
    requireClusterSamples: true,
    clock: () => Date.parse(observedAt) + 1000,
    ...overrides,
  });
const perCluster = (overrides = {}) => ({
  clusterSamples: {
    a: { ...healthy, observedAt },
    b: { ...healthy, observedAt, ...overrides },
  },
});

test("advances only when every cluster has fresh healthy telemetry", () => {
  const c = clusterMode();
  start(c);
  assert.equal(c.observe("r1", perCluster()).trafficPercent, 5);
  assert.equal(c.ledger.verify(), true);
});
test("rolls back when one cluster breaches despite healthy peers", () => {
  const c = clusterMode();
  start(c);
  const r = c.observe("r1", perCluster({ errorRate: 0.03 }));
  assert.equal(r.status, "ROLLED_BACK");
  assert.equal(r.rollbackReason, "b: error rate SLO breach");
  assert.equal(r.clusters.a.trafficPercent, 0);
});
test("does not allow aggregate-only telemetry in strict cluster mode", () => {
  const c = clusterMode();
  start(c);
  assert.throws(() => c.observe("r1", healthy), /clusterSamples are required/);
  assert.equal(c.get("r1").trafficPercent, 0);
});
test("rejects missing, extra and stale cluster telemetry without advancing", () => {
  const c = clusterMode();
  start(c);
  assert.throws(
    () =>
      c.observe("r1", { clusterSamples: { a: { ...healthy, observedAt } } }),
    /exactly/,
  );
  assert.throws(
    () =>
      c.observe("r1", {
        clusterSamples: {
          ...perCluster().clusterSamples,
          unknown: { ...healthy, observedAt },
        },
      }),
    /exactly/,
  );
  assert.throws(
    () =>
      c.observe("r1", perCluster({ observedAt: "2026-09-28T23:58:00.000Z" })),
    /stale/,
  );
  assert.equal(c.get("r1").trafficPercent, 0);
});
test("rejects future and malformed cluster telemetry", () => {
  const c = clusterMode();
  start(c);
  assert.throws(
    () =>
      c.observe("r1", perCluster({ observedAt: "2026-09-29T00:00:02.000Z" })),
    /future/,
  );
  assert.throws(
    () => c.observe("r1", perCluster({ saturation: -1 })),
    /saturation/,
  );
});
