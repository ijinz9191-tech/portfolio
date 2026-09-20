import test from 'node:test';
import assert from 'node:assert/strict';
import { releaseLease, reserveCards, validateInventory } from '../src/inventory.js';
import { fleetFixture } from '../src/fixtures.js';

const request = { leaseId: 'lease-a', count: 2, minMemoryGiB: 48, features: ['fp16', 'collective'], maxNodes: 1, sameFirmware: true };

test('validates globally unique inventory and returns hash', () => {
  const result = validateInventory(fleetFixture());
  assert.equal(result.cardCount, 4);
  assert.equal(result.inventoryHash.length, 64);
});

test('rejects duplicate card identities across nodes', () => {
  const fleet = fleetFixture();
  fleet[1].cards[0].id = fleet[0].cards[0].id;
  assert.throws(() => validateInventory(fleet), { code: 'CARD_ID_INVALID' });
});

test('reserves healthy compatible cards on one node', () => {
  const result = reserveCards(fleetFixture(), request);
  assert.deepEqual(result.lease.assignments[0].cardIds, ['npu-a1', 'npu-a2']);
  assert.equal(result.nodes[0].cards.filter(card => card.leaseId === 'lease-a').length, 2);
});

test('does not allocate degraded cards', () => {
  assert.throws(() => reserveCards(fleetFixture(), { ...request, count: 4, maxNodes: 2 }), { code: 'CAPACITY_UNAVAILABLE' });
});

test('rejects a duplicate lease rather than double allocating', () => {
  const once = reserveCards(fleetFixture(), request);
  assert.throws(() => reserveCards(once.nodes, request), { code: 'LEASE_DUPLICATE' });
});

test('enforces same firmware constraint', () => {
  const fleet = fleetFixture();
  fleet[0].cards[1].firmware = '2.5.0';
  assert.throws(() => reserveCards(fleet, request), { code: 'CAPACITY_UNAVAILABLE' });
});

test('releases exactly the selected lease', () => {
  const reserved = reserveCards(fleetFixture(), request);
  const released = releaseLease(reserved.nodes, 'lease-a');
  assert.equal(released.released, 2);
  assert.equal(released.nodes.flatMap(node => node.cards).filter(card => card.leaseId).length, 0);
});
