import test from "node:test";
import assert from "node:assert/strict";
import {
  releaseLease,
  reserveCards,
  validateInventory,
} from "../src/inventory.js";
import { fleetFixture } from "../src/fixtures.js";

test("첫 카드의 펌웨어가 아니라 실제 배치 가능한 펌웨어를 선택한다", () => {
  const fleet = fleetFixture();
  fleet[0].cards[0].firmware = "old";
  fleet[1].cards[1].health = "HEALTHY";
  fleet[1].cards[1].features.push("collective");
  const placed = reserveCards(fleet, { ...request, count: 3, maxNodes: 2 });
  assert.equal(placed.lease.firmware, "2.4.1");
  assert.equal(placed.lease.assignments.flatMap((a) => a.cardIds).length, 3);
  assert.ok(
    fleet.every((node) => node.cards.every((card) => card.leaseId === null)),
  );
});
test("작은 모든 노드 부분집합을 기준 구현으로 삼아 펌웨어 배치 가능성을 대조한다", () => {
  let seed = 7421;
  const random = (n) => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed % n;
  };
  for (let sample = 0; sample < 120; sample++) {
    const nodes = Array.from({ length: 4 }, (_, n) => ({
      id: `node-${n}`,
      zone: "az",
      state: "READY",
      cards: Array.from({ length: 1 + random(4) }, (_, c) => ({
        id: `card-${n}-${c}`,
        memoryGiB: 64,
        health: "HEALTHY",
        leaseId: null,
        features: [],
        firmware: `fw-${random(3)}`,
      })),
    }));
    const maxNodes = 1 + random(4),
      count = 1 + random(9);
    let feasible = false;
    for (let mask = 1; mask < 16; mask++) {
      const selected = nodes.filter((_, n) => mask & (1 << n));
      if (selected.length > maxNodes) continue;
      for (const firmware of ["fw-0", "fw-1", "fw-2"])
        if (
          selected
            .flatMap((n) => n.cards)
            .filter((c) => c.firmware === firmware).length >= count
        )
          feasible = true;
    }
    const operation = () =>
      reserveCards(nodes, {
        leaseId: "new",
        count,
        maxNodes,
        sameFirmware: true,
      });
    if (!feasible) assert.throws(operation, { code: "CAPACITY_UNAVAILABLE" });
    else {
      const placed = operation();
      const selected = placed.lease.assignments.flatMap((a) => a.cardIds);
      assert.equal(selected.length, count);
      assert.ok(placed.lease.assignments.length <= maxNodes);
      assert.ok(
        nodes
          .flatMap((n) => n.cards)
          .filter((c) => selected.includes(c.id))
          .every((c) => c.firmware === placed.lease.firmware),
      );
    }
  }
});
test("유한하지 않은 메모리와 잘못된 노드 제한을 거부한다", () => {
  for (const values of [
    { maxNodes: 0 },
    { maxNodes: NaN },
    { minMemoryGiB: Infinity },
    { features: null },
  ])
    assert.throws(
      () => reserveCards(fleetFixture(), { ...request, ...values }),
      { code: "REQUEST_INVALID" },
    );
});

const request = {
  leaseId: "lease-a",
  count: 2,
  minMemoryGiB: 48,
  features: ["fp16", "collective"],
  maxNodes: 1,
  sameFirmware: true,
};

test("validates globally unique inventory and returns hash", () => {
  const result = validateInventory(fleetFixture());
  assert.equal(result.cardCount, 4);
  assert.equal(result.inventoryHash.length, 64);
});

test("rejects duplicate card identities across nodes", () => {
  const fleet = fleetFixture();
  fleet[1].cards[0].id = fleet[0].cards[0].id;
  assert.throws(() => validateInventory(fleet), { code: "CARD_ID_INVALID" });
});

test("reserves healthy compatible cards on one node", () => {
  const result = reserveCards(fleetFixture(), request);
  assert.deepEqual(result.lease.assignments[0].cardIds, ["npu-a1", "npu-a2"]);
  assert.equal(
    result.nodes[0].cards.filter((card) => card.leaseId === "lease-a").length,
    2,
  );
});

test("does not allocate degraded cards", () => {
  assert.throws(
    () => reserveCards(fleetFixture(), { ...request, count: 4, maxNodes: 2 }),
    { code: "CAPACITY_UNAVAILABLE" },
  );
});

test("rejects a duplicate lease rather than double allocating", () => {
  const once = reserveCards(fleetFixture(), request);
  assert.throws(() => reserveCards(once.nodes, request), {
    code: "LEASE_DUPLICATE",
  });
});

test("enforces same firmware constraint", () => {
  const fleet = fleetFixture();
  fleet[0].cards[1].firmware = "2.5.0";
  assert.throws(() => reserveCards(fleet, request), {
    code: "CAPACITY_UNAVAILABLE",
  });
});

test("releases exactly the selected lease", () => {
  const reserved = reserveCards(fleetFixture(), request);
  const released = releaseLease(reserved.nodes, "lease-a");
  assert.equal(released.released, 2);
  assert.equal(
    released.nodes.flatMap((node) => node.cards).filter((card) => card.leaseId)
      .length,
    0,
  );
});
