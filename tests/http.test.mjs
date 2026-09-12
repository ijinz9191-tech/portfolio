import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { createLabServer } from '../src/server.mjs';
import { LabStore } from '../src/store.mjs';
const root=new URL('../',import.meta.url);
async function setup(t){const store=new LabStore();const server=createLabServer({store,assetRoot:fileURLToPath(root)});server.listen(0,'127.0.0.1');await once(server,'listening');t.after(async()=>{await new Promise(resolve=>{server.close(resolve);server.closeAllConnections();});store.close();});return 'http://127.0.0.1:'+server.address().port;}
async function post(base,path,body,headers={}){return fetch(base+path,{method:'POST',headers:{'Content-Type':'application/json',...headers},body:JSON.stringify(body)});}
test('HTTP end-to-end: scenario, search, mitigation, recovery, retry and health',async t=>{
 const base=await setup(t);assert.equal((await (await fetch(base+'/api/health')).json()).status,'ok');
 const created=await post(base,'/api/scenarios',{scenario:'identity-session'});assert.equal(created.status,201);const item=await created.json();
 assert.equal(item.status,'open');assert.equal(item.events.length,3);
 const filtered=await (await fetch(base+'/api/incidents?service=identity-api&status=open&q=SSO')).json();assert.equal(filtered.matched,1);
 let response=await post(base,`/api/incidents/${item.id}/actions`,{action:'recover'});assert.equal(response.status,409);
 response=await post(base,`/api/incidents/${item.id}/actions`,{action:'mitigate'});assert.equal((await response.json()).status,'mitigating');
 response=await post(base,`/api/incidents/${item.id}/actions`,{action:'recover'});const resolved=await response.json();assert.equal(resolved.status,'resolved');
 const {sequence,...event}=resolved.events.at(-1);response=await post(base,'/api/events',{events:[event]});assert.equal((await response.json()).results[0].duplicate,true);
 const final=await (await fetch(base+'/api/incidents')).json();assert.equal(final.eventCount,5);assert.equal(final.counts.resolved,1);
});
test('HTTP rejects malformed bodies, oversized payloads, cross-site writes and invalid query',async t=>{
 const base=await setup(t);
 assert.equal((await fetch(base+'/api/events',{method:'POST',headers:{'Content-Type':'application/json'},body:'{'})).status,400);
 assert.equal((await fetch(base+'/api/events',{method:'POST',body:'{}'})).status,415);
 assert.equal((await post(base,'/api/events',{events:[],padding:'x'.repeat(17000)})).status,413);
 assert.equal((await post(base,'/api/scenarios',{scenario:'checkout-timeout'},{Origin:'https://untrusted.example'})).status,403);
 assert.equal((await post(base,'/api/scenarios',{scenario:'checkout-timeout'},{'Sec-Fetch-Site':'cross-site'})).status,403);
 assert.equal((await fetch(base+'/api/incidents?limit=10000')).status,400);
 assert.equal((await fetch(base+'/api/incidents?status=open&status=resolved')).status,400);
 assert.equal((await post(base,'/api/scenarios',{scenario:'checkout-timeout',extra:true})).status,400);
 assert.equal((await (await fetch(base+'/api/incidents')).json()).eventCount,0);
});
test('HTTP only serves allowlisted public assets and supplies browser protection headers',async t=>{
 const base=await setup(t);const response=await fetch(base+'/');assert.equal(response.status,200);assert.match(await response.text(),/Incident Replay Lab/);
 assert.match(response.headers.get('content-security-policy'),/frame-ancestors 'none'/);
 for(const path of ['/README.md','/APP.md','/.git/config','/src/store.mjs','/data/lab.sqlite','/%2e%2e/README.md','/resume.pdf']) assert.equal((await fetch(base+path)).status,404,path);
 assert.equal((await fetch(base+'/styles.css',{method:'HEAD'})).status,200);
 assert.equal((await fetch(base+'/api/incidents',{method:'DELETE'})).status,405);
 const unknown=await fetch(base+'/api/incidents/missing');assert.equal(unknown.status,404);assert.equal((await unknown.json()).error.code,'NOT_FOUND');
});
