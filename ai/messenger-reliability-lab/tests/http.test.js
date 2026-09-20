import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { MessageLedger } from '../src/ledger.js';
import { createMessengerServer } from '../src/http.js';

const withServer = async run => {
  let id = 0;
  const ledger = new MessageLedger({ id: () => `http-${++id}` });
  const server = createMessengerServer(ledger).listen(0, '127.0.0.1');
  await once(server, 'listening');
  try { await run(`http://127.0.0.1:${server.address().port}`); }
  finally { server.close(); await once(server, 'close'); }
};

test('serves a real loopback enqueue, dispatch, ack and read flow', async () => withServer(async base => {
  const created = await fetch(`${base}/messages`, { method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ idempotencyKey: 'http-key', conversationId: 'room', senderId: 'user', payload: 'hello' }) });
  assert.equal(created.status, 201);
  const id = (await created.json()).message.id;
  assert.equal((await fetch(`${base}/messages/${id}/dispatch`, { method: 'POST' })).status, 200);
  assert.equal((await fetch(`${base}/messages/${id}/ack`, { method: 'POST' })).status, 200);
  const result = await (await fetch(`${base}/messages/${id}`)).json();
  assert.equal(result.status, 'DELIVERED');
}));

test('returns a typed error for malformed JSON', async () => withServer(async base => {
  const response = await fetch(`${base}/messages`, { method: 'POST', body: '{' });
  assert.equal(response.status, 400);
  assert.equal((await response.json()).code, 'INVALID_JSON');
}));

test('rejects unsupported routes without mutating state', async () => withServer(async base => {
  const response = await fetch(`${base}/unknown`, { method: 'POST' });
  assert.equal(response.status, 404);
  assert.equal((await response.json()).code, 'ROUTE_NOT_FOUND');
}));
