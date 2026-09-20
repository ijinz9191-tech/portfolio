import { createServer } from 'node:http';
import { LedgerError } from './ledger.js';

const json = (response, status, body) => {
  response.writeHead(status, { 'content-type': 'application/json; charset=utf-8' });
  response.end(JSON.stringify(body));
};

const readJson = async request => {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  try { return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}'); }
  catch { throw new LedgerError('INVALID_JSON', 'Request body must be valid JSON'); }
};

export const createMessengerServer = ledger => createServer(async (request, response) => {
  try {
    const url = new URL(request.url, 'http://localhost');
    if (request.method === 'GET' && url.pathname === '/health') return json(response, 200, { status: 'ok' });
    if (request.method === 'POST' && url.pathname === '/messages') {
      const result = ledger.enqueue(await readJson(request));
      return json(response, result.duplicate ? 200 : 201, result);
    }
    const match = url.pathname.match(/^\/messages\/([^/]+)(?:\/(dispatch|ack))?$/);
    if (match && request.method === 'GET' && !match[2]) return json(response, 200, ledger.get(match[1]));
    if (match && request.method === 'POST' && match[2] === 'dispatch') return json(response, 200, ledger.dispatch(match[1]));
    if (match && request.method === 'POST' && match[2] === 'ack') return json(response, 200, ledger.acknowledge(match[1]));
    if (request.method === 'POST' && url.pathname === '/tick') {
      const body = await readJson(request);
      return json(response, 200, { changed: ledger.tick(body.at) });
    }
    return json(response, 404, { code: 'ROUTE_NOT_FOUND' });
  } catch (error) {
    if (error instanceof LedgerError) return json(response, error.status, { code: error.code, message: error.message });
    return json(response, 500, { code: 'INTERNAL_ERROR' });
  }
});
