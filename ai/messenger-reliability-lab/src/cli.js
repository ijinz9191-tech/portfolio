import { MessageLedger } from './ledger.js';

let clock = 1_000;
const ledger = new MessageLedger({ now: () => clock, id: () => 'demo-message', ackTimeoutMs: 100 });
const queued = ledger.enqueue({ idempotencyKey: 'demo-1', conversationId: 'ops-room', senderId: 'bot', payload: 'deploy complete', expectedSequence: 1 });
ledger.dispatch(queued.message.id);
clock += 50;
ledger.acknowledge(queued.message.id);
console.log(JSON.stringify({ message: ledger.get(queued.message.id), events: ledger.listEvents() }, null, 2));
