import { ControlPlaneError } from './errors.js';
import { digest } from './hash.js';

export function validateInventory(nodes) {
  if (!Array.isArray(nodes) || nodes.length === 0) throw new ControlPlaneError('INVENTORY_EMPTY', 'at least one node is required');
  const nodeIds = new Set();
  const cardIds = new Set();
  for (const node of nodes) {
    if (!node.id || nodeIds.has(node.id)) throw new ControlPlaneError('NODE_ID_INVALID', 'node ids must be unique', { nodeId: node.id });
    nodeIds.add(node.id);
    if (!node.zone || !Array.isArray(node.cards) || node.cards.length === 0) throw new ControlPlaneError('NODE_INVALID', 'node requires zone and cards', { nodeId: node.id });
    for (const card of node.cards) {
      if (!card.id || cardIds.has(card.id)) throw new ControlPlaneError('CARD_ID_INVALID', 'card ids must be globally unique', { cardId: card.id });
      if (!Number.isInteger(card.memoryGiB) || card.memoryGiB <= 0) throw new ControlPlaneError('CARD_INVALID', 'memoryGiB must be a positive integer', { cardId: card.id });
      cardIds.add(card.id);
    }
  }
  return { nodeCount: nodeIds.size, cardCount: cardIds.size, inventoryHash: digest(nodes) };
}

const eligibleCards = (node, request) => node.cards.filter(card =>
  card.health === 'HEALTHY' && card.leaseId === null && card.memoryGiB >= request.minMemoryGiB &&
  request.features.every(feature => card.features.includes(feature)));

export function reserveCards(nodes, request) {
  validateInventory(nodes);
  if (!request?.leaseId || !Number.isInteger(request.count) || request.count <= 0) throw new ControlPlaneError('REQUEST_INVALID', 'leaseId and positive count are required');
  const normalized = { minMemoryGiB: 0, features: [], maxNodes: 1, sameFirmware: true, ...request };
  if (nodes.some(node => node.cards.some(card => card.leaseId === normalized.leaseId))) throw new ControlPlaneError('LEASE_DUPLICATE', 'lease already exists', { leaseId: normalized.leaseId });

  const groups = [];
  for (const node of nodes.filter(item => item.state === 'READY')) {
    const cards = eligibleCards(node, normalized);
    if (cards.length) groups.push({ node, cards });
  }
  groups.sort((a, b) => b.cards.length - a.cards.length || a.node.id.localeCompare(b.node.id));

  let remaining = normalized.count;
  const chosen = [];
  let firmware = null;
  for (const group of groups) {
    if (chosen.length >= normalized.maxNodes || remaining === 0) break;
    const compatible = group.cards.filter(card => !normalized.sameFirmware || firmware === null || card.firmware === firmware);
    if (!compatible.length) continue;
    firmware ??= compatible[0].firmware;
    const sameVersion = normalized.sameFirmware ? compatible.filter(card => card.firmware === firmware) : compatible;
    const take = sameVersion.slice(0, remaining);
    if (take.length) chosen.push({ nodeId: group.node.id, zone: group.node.zone, cardIds: take.map(card => card.id) });
    remaining -= take.length;
  }
  if (remaining > 0) throw new ControlPlaneError('CAPACITY_UNAVAILABLE', 'request cannot be placed safely', { requested: normalized.count, available: normalized.count - remaining });

  const selected = new Set(chosen.flatMap(item => item.cardIds));
  const nextNodes = nodes.map(node => ({ ...node, cards: node.cards.map(card => selected.has(card.id) ? { ...card, leaseId: normalized.leaseId } : { ...card }) }));
  return { nodes: nextNodes, lease: { leaseId: normalized.leaseId, assignments: chosen, firmware, requestHash: digest(normalized), inventoryHash: digest(nodes) } };
}

export function releaseLease(nodes, leaseId) {
  let released = 0;
  const nextNodes = nodes.map(node => ({ ...node, cards: node.cards.map(card => {
    if (card.leaseId !== leaseId) return { ...card };
    released += 1;
    return { ...card, leaseId: null };
  }) }));
  if (!released) throw new ControlPlaneError('LEASE_NOT_FOUND', 'lease does not exist', { leaseId });
  return { nodes: nextNodes, released };
}
