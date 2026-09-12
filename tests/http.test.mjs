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

test('simulation HTTP contract: inject, runbook, deterministic ticks, replay and postmortem export',async t=>{
 const base=await setup(t);let response=await fetch(base+'/api/sim/state');assert.equal(response.status,200);const initial=await response.json();assert.equal(initial.simulation,true);assert.equal(initial.services.length,8);assert.equal(initial.clock.tick,0);
 response=await post(base,'/api/sim/faults',{scenarioId:'query-lock',intensity:3,commandId:'http-fault'});assert.equal(response.status,200);const injected=await response.json();const id=injected.incidents[0].id;assert.equal(injected.incidents[0].status,'open');assert.ok(injected.summary.edgeLatencyMs>initial.summary.edgeLatencyMs);
 response=await post(base,'/api/sim/faults',{scenarioId:'query-lock',intensity:3,commandId:'http-fault'});assert.equal((await response.json()).lastCommand.duplicate,true);
 response=await post(base,'/api/sim/runbooks',{actionId:'unlock-query',incidentId:id});assert.equal((await response.json()).incidents[0].status,'mitigating');
 response=await post(base,'/api/sim/control',{action:'tick',steps:4});const resolved=await response.json();assert.equal(resolved.incidents[0].status,'resolved');assert.equal(resolved.summary.healthy,8);
 const snapshot=await (await fetch(base+`/api/sim/runs/${initial.runId}?tick=2`)).json();assert.equal(snapshot.replay,true);assert.equal(snapshot.clock.tick,2);assert.equal(snapshot.incidents[0].status,'mitigating');
 response=await fetch(base+`/api/sim/incidents/${id}/export`);assert.equal(response.status,200);assert.match(response.headers.get('content-disposition'),/attachment; filename="incident-/);const report=await response.json();assert.equal(report.timing.recoverySeconds,20);assert.equal(report.integrity.algorithm,'SHA-256');
 await post(base,'/api/sim/reset',{seed:17});assert.equal((await (await fetch(base+'/api/sim/runs')).json()).runs.length,2);assert.equal((await fetch(base+`/api/sim/incidents/${id}/postmortem`)).status,200);
});
test('simulation endpoints maintain HTTP origin, field and query validation',async t=>{
 const base=await setup(t);const before=await (await fetch(base+'/api/sim/state')).json();
 assert.equal((await post(base,'/api/sim/faults',{scenarioId:'bad-release'},{Origin:'https://untrusted.example'})).status,403);
 assert.equal((await post(base,'/api/sim/reset',{seed:1,unexpected:true})).status,400);
 assert.equal((await post(base,'/api/sim/control',{action:'tick',steps:61})).status,400);
 assert.equal((await post(base,'/api/sim/faults',{scenarioId:'bad-release',intensity:4})).status,400);
 assert.equal((await fetch(base+'/api/sim/state?q=x')).status,400);
 assert.equal((await fetch(base+`/api/sim/runs/${before.runId}?tick=0&tick=1`)).status,400);
 assert.equal((await fetch(base+`/api/sim/runs/${before.runId}?tick=-1`)).status,400);
 assert.equal((await fetch(base+`/api/sim/runs/${before.runId}?tick=999`)).status,404);
 const after=await (await fetch(base+'/api/sim/state')).json();assert.equal(after.runId,before.runId);assert.equal(after.incidents.length,0);assert.equal(after.clock.tick,0);
});
