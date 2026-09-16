import { createServer } from 'node:http';
import { readFile, mkdir } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { LabStore, LabError, SCENARIOS } from './store.mjs';
import { SimulationEngine } from './simulation.mjs';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const assets = new Map([['/', ['index.html','text/html; charset=utf-8']], ['/index.html',['index.html','text/html; charset=utf-8']], ['/app.js',['app.js','text/javascript; charset=utf-8']], ['/styles.css',['styles.css','text/css; charset=utf-8']], ['/public.data.json',['public.data.json','application/json; charset=utf-8']]]);
const CSP = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'";
async function body(request) {
  if (!/^application\/json(?:;|$)/i.test(request.headers['content-type'] || '')) throw new LabError(415,'JSON_REQUIRED','Use application/json.');
  let bytes = 0; const chunks = [];
  for await (const chunk of request) { bytes += chunk.length; if (bytes <= 16384) chunks.push(chunk); }
  if (bytes > 16384) throw new LabError(413,'BODY_TOO_LARGE','JSON body must be at most 16 KiB.');
  try { return JSON.parse(Buffer.concat(chunks).toString('utf8')); }
  catch { throw new LabError(400,'INVALID_JSON','Malformed JSON.'); }
}
function field(value, name) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).length !== 1 || !Object.hasOwn(value,name)) throw new LabError(400,'INVALID_FIELDS',`Expected only ${name}.`);
  return value[name];
}
export function createLabServer({store = new LabStore(), assetRoot = resolve(ROOT, 'dist'), simulationIntervalMs = 1000} = {}) {
  const started = Date.now();
  const simulation = new SimulationEngine(store.db, {intervalMs: simulationIntervalMs});
  const server = createServer(async (request,response) => {
    const headers = { 'X-Content-Type-Options':'nosniff', 'Cache-Control':'no-store', 'Content-Security-Policy':CSP, 'Referrer-Policy':'no-referrer' };
    function json(status, data) { response.writeHead(status,{...headers,'Content-Type':'application/json; charset=utf-8'}); response.end(request.method === 'HEAD' ? undefined : JSON.stringify(data)); }
    try {
      const port = server.address()?.port;
      if (![ `127.0.0.1:${port}`, `localhost:${port}` ].includes(request.headers.host)) throw new LabError(403,'INVALID_HOST','Use the loopback address printed by the server.');
      const url = new URL(request.url, 'http://127.0.0.1');
      if (!['GET','HEAD','POST'].includes(request.method)) throw new LabError(405,'METHOD_NOT_ALLOWED','Method not supported.');
      if (request.method === 'POST') {
        const origin = request.headers.origin;
        if (request.headers['sec-fetch-site'] === 'cross-site' || (origin && ![`http://127.0.0.1:${port}`, `http://localhost:${port}`].includes(origin))) throw new LabError(403,'ORIGIN_BLOCKED','Cross-origin writes are blocked.');
      }
      if (url.pathname.startsWith('/api/sim/')) {
        const replay = /^\/api\/sim\/runs\/([A-Za-z0-9_-]{1,80})$/.exec(url.pathname);
        if (replay && request.method === 'GET') {
          if ([...url.searchParams.keys()].some(key=>key!=='tick') || url.searchParams.getAll('tick').length!==1 || !/^\d{1,9}$/.test(url.searchParams.get('tick'))) throw new LabError(400,'INVALID_QUERY','Supply one integer replay tick.');
          return json(200,simulation.replay(replay[1],Number(url.searchParams.get('tick'))));
        }
        if ([...url.searchParams].length) throw new LabError(400,'INVALID_QUERY','This simulation endpoint accepts no query parameters.');
        if (url.pathname === '/api/sim/state' && request.method === 'GET') return json(200,simulation.view());
        if (url.pathname === '/api/sim/runs' && request.method === 'GET') return json(200,{runs:simulation.runs(),simulation:true});
        const report = /^\/api\/sim\/incidents\/([A-Za-z0-9_-]{1,80})\/(postmortem|export)$/.exec(url.pathname);
        if (report && request.method === 'GET') {
          const data=simulation.postmortem(report[1]);
          if(report[2]==='export')response.setHeader('Content-Disposition',`attachment; filename="incident-${report[1]}.json"`);
          return json(200,data);
        }
        const commands = new Map([['/api/sim/control','control'],['/api/sim/reset','reset'],['/api/sim/faults','fault'],['/api/sim/runbooks','runbook']]);
        if (commands.has(url.pathname) && request.method === 'POST') return json(200,simulation.command(commands.get(url.pathname),await body(request)));
        throw new LabError(404,'NOT_FOUND','Simulation route not found.');
      }
      if (url.pathname === '/api/health' && ['GET','HEAD'].includes(request.method)) return json(200,{status: store.healthy()?'ok':'unavailable', storage:'sqlite', uptimeSeconds:Math.floor((Date.now()-started)/1000), synthetic:true});
      if (url.pathname === '/api/scenarios' && request.method === 'GET') return json(200,{scenarios:SCENARIOS.map(({id,service,title,description})=>({id,service,title,description})),synthetic:true});
      if (url.pathname === '/api/incidents' && request.method === 'GET') return json(200,store.list(url.searchParams));
      if (url.pathname === '/api/events' && request.method === 'POST') return json(200,{results:store.ingest(field(await body(request),'events')),synthetic:true});
      if (url.pathname === '/api/scenarios' && request.method === 'POST') return json(201,store.scenario(field(await body(request),'scenario')));
      const match = /^\/api\/incidents\/([A-Za-z0-9_-]{1,80})(\/actions)?$/.exec(url.pathname);
      if (match && !match[2] && request.method === 'GET') return json(200,store.detail(match[1]));
      if (match && match[2] && request.method === 'POST') return json(200,store.action(match[1],field(await body(request),'action')));
      if (url.pathname.startsWith('/api/')) throw new LabError(404,'NOT_FOUND','API route not found.');
      if (!['GET','HEAD'].includes(request.method)) throw new LabError(405,'METHOD_NOT_ALLOWED','Static assets are read-only.');
      const asset = assets.get(url.pathname);
      if (!asset) throw new LabError(404,'NOT_FOUND','Not found.');
      let data;
      try { data = await readFile(resolve(assetRoot,asset[0])); }
      catch { throw new LabError(503,'BUILD_REQUIRED','Run npm run build first.'); }
      response.writeHead(200,{...headers,'Content-Type':asset[1]});response.end(request.method==='HEAD'?undefined:data);
    } catch(error) {
      const expected = error instanceof LabError;
      if (!expected) console.error('Request failed:', error.code || error.name);
      json(expected?error.status:500,{error:{code:expected?error.code:'INTERNAL_ERROR',message:expected?error.message:'Request failed. Inspect the local server log.'}});
    }
  });
  server.on('close',()=>simulation.close());
  server.simulation=simulation;
  server.requestTimeout=10000; server.headersTimeout=10000;
  return server;
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const port = Number(process.env.PORT || 4173);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('PORT must be 1-65535.');
  const dbPath = resolve(process.env.LAB_DB || resolve(ROOT,'data/lab.sqlite'));
  await mkdir(dirname(dbPath),{recursive:true});
  const store = new LabStore(dbPath), server = createLabServer({store});
  server.listen(port,'127.0.0.1',()=>console.log(`Incident Replay Lab: http://127.0.0.1:${port} | synthetic data only | SQLite persisted locally`));
  function shutdown() { server.close(()=>{store.close();process.exit(0);}); server.closeIdleConnections(); }
  process.once('SIGINT',shutdown);process.once('SIGTERM',shutdown);
}
