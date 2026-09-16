import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { LabStore } from '../src/store.mjs';
import { SimulationEngine } from '../src/simulation.mjs';
function setup(t,options={}){const store=new LabStore();const engine=new SimulationEngine(store.db,options);t.after(()=>{engine.close();store.close();});return {store,engine};}
const metrics = state => state.services.map(({id,status,metrics,history})=>({id,status,metrics,history}));
const assertCode = (fn,code)=>assert.throws(fn,error=>error.code===code);

test('same seed and command schedule reproduce all metrics and dependency histories',t=>{
 const {engine:a}=setup(t),{engine:b}=setup(t);
 for(const engine of [a,b]){engine.command('reset',{seed:812});engine.command('control',{action:'tick',steps:3});const state=engine.command('fault',{scenarioId:'query-lock',intensity:2});engine.command('control',{action:'tick',steps:6});engine.command('runbook',{actionId:'unlock-query',incidentId:state.incidents[0].id});engine.command('control',{action:'tick',steps:4});}
 assert.deepEqual(metrics(a.view()),metrics(b.view()));assert.deepEqual(a.view().summary,b.view().summary);assert.equal(a.view().clock.tick,13);
 assert.equal(a.view().services.length,8);assert.equal(a.view().topology.edges.length,11);assert.equal(a.view().scenarios.length,4);
});
test('query fault propagates along causal dependency paths only',t=>{
 const {engine}=setup(t),baseline=engine.view();const after=engine.command('fault',{scenarioId:'query-lock',intensity:2});const item=after.incidents[0];
 assert.deepEqual(item.impactServices,['checkout-api','edge-gateway','orders-api','orders-db']);
 for(const id of item.impactServices){const node=after.services.find(s=>s.id===id);assert.ok(node.metrics.latencyMs>baseline.services.find(s=>s.id===id).metrics.latencyMs);assert.ok(node.causes.includes(after.faults[0].id));}
 for(const id of ['catalog-api','identity-api','payment-api','redis-cache'])assert.deepEqual(after.services.find(s=>s.id===id).metrics,baseline.services.find(s=>s.id===id).metrics);
 assert.deepEqual(engine.postmortem(item.id).causalPaths,[['orders-db','orders-api','checkout-api','edge-gateway']]);
});
test('intensity and runbook change generated metrics; recovery follows four ticks',t=>{
 const {engine:a}=setup(t),{engine:b}=setup(t);a.command('fault',{scenarioId:'cache-eviction',intensity:1});const state=b.command('fault',{scenarioId:'cache-eviction',intensity:3});const incident=state.incidents[0];
 const root=s=>s.services.find(s=>s.id==='redis-cache').metrics;
 assert.ok(root(b.view()).latencyMs>root(a.view()).latencyMs);assert.ok(root(b.view()).cacheHitPercent<root(a.view()).cacheHitPercent);
 const before=b.view();assertCode(()=>b.command('runbook',{actionId:'rollback-release',incidentId:incident.id}),'RUNBOOK_MISMATCH');assert.deepEqual(b.view(),before);
 const action=b.command('runbook',{actionId:'warm-cache',incidentId:incident.id});assert.equal(action.incidents[0].status,'mitigating');assert.ok(root(action).latencyMs<root(before).latencyMs);assert.ok(root(action).cacheHitPercent>root(before).cacheHitPercent);
 const audit=action.audit.find(e=>e.kind==='runbook_applied');assert.ok(audit.before.latencyMs>audit.after.latencyMs);
 b.command('control',{action:'tick',steps:3});assert.equal(b.view().incidents[0].status,'mitigating');b.command('control',{action:'tick'});assert.equal(b.view().incidents[0].status,'resolved');assert.equal(b.view().summary.healthy,8);
 assertCode(()=>b.command('runbook',{actionId:'warm-cache',incidentId:incident.id}),'INVALID_ACTION_STATE');
});
test('resolving one root fault leaves independent failures active',t=>{
 const {engine}=setup(t);const one=engine.command('fault',{scenarioId:'query-lock'}).incidents[0];engine.command('fault',{scenarioId:'identity-expiry'});
 engine.command('runbook',{actionId:'unlock-query',incidentId:one.id});engine.command('control',{action:'tick',steps:4});const state=engine.view();
 assert.equal(state.incidents.find(i=>i.id===one.id).status,'resolved');assert.equal(state.summary.activeIncidents,1);assert.ok(state.summary.critical>0);assert.ok(state.services.find(s=>s.id==='identity-api').metrics.errorRate>10);
});
test('simulation commands are idempotent and reject conflicting replay',t=>{
 const {engine}=setup(t);const first=engine.command('fault',{scenarioId:'bad-release',intensity:2,commandId:'once'});const duplicate=engine.command('fault',{commandId:'once',intensity:2,scenarioId:'bad-release'});
 assert.equal(duplicate.lastCommand.duplicate,true);assert.equal(duplicate.incidents.length,1);assert.equal(duplicate.incidents[0].id,first.incidents[0].id);
 assertCode(()=>engine.command('fault',{scenarioId:'query-lock',commandId:'once'}),'IDEMPOTENCY_CONFLICT');
 engine.command('control',{action:'tick',steps:3,commandId:'tick-once'});engine.command('control',{action:'tick',steps:3,commandId:'tick-once'});assert.equal(engine.view().clock.tick,3);
 assertCode(()=>engine.command('fault',{scenarioId:'bad-release'}),'FAULT_ALREADY_ACTIVE');
});
test('invalid simulation input cannot mutate the persisted run',t=>{
 const {engine}=setup(t);const before=engine.view();
 for(const [kind,input] of [['control',{action:'tick',steps:0}],['control',{action:'tick',steps:61}],['control',{action:'tick',steps:1.5}],['control',{action:'run',steps:1}],['reset',{seed:-1}],['reset',{seed:1.5}],['fault',{scenarioId:'query-lock',intensity:0}],['fault',{scenarioId:'query-lock',intensity:4}],['fault',{scenarioId:'unknown'}],['reset',{seed:1,unknown:true}]])assert.throws(()=>engine.command(kind,input));
 assert.deepEqual(engine.view(),before);
});
test('recorded replay is read-only and reset preserves earlier incident export',t=>{
 const {engine}=setup(t);const first=engine.command('fault',{scenarioId:'query-lock'});engine.command('control',{action:'tick',steps:2});const prior=engine.view(),reset=engine.command('reset',{seed:900});
 assert.equal(reset.clock.tick,0);assert.equal(reset.incidents.length,0);assert.equal(reset.runs.length,2);assert.notEqual(reset.runId,prior.runId);
 const replay=engine.replay(prior.runId,2);assert.equal(replay.replay,true);assert.deepEqual(metrics(replay),metrics(prior));assert.equal(engine.view().runId,reset.runId);
 const report=engine.postmortem(first.incidents[0].id);assert.equal(report.runId,prior.runId);assert.equal(report.simulation,true);
 const {integrity,...content}=report;assert.equal(integrity.sha256,createHash('sha256').update(JSON.stringify(content)).digest('hex'));
 assertCode(()=>engine.replay(prior.runId,999),'SNAPSHOT_NOT_FOUND');
});
test('simulation state and command IDs survive database reopen, timer resumes paused',async t=>{
 const dir=await mkdtemp(join(tmpdir(),'sim-lab-test-'));t.after(()=>rm(dir,{recursive:true,force:true}));const path=join(dir,'lab.sqlite');
 let store=new LabStore(path),engine=new SimulationEngine(store.db,{intervalMs:100000});engine.command('fault',{scenarioId:'identity-expiry',commandId:'persistent-command'});engine.command('control',{action:'tick',steps:3});const before=metrics(engine.view());engine.command('control',{action:'run'});engine.close();store.close();
 store=new LabStore(path);engine=new SimulationEngine(store.db);try{assert.equal(engine.view().clock.running,false);assert.deepEqual(metrics(engine.view()),before);assert.equal(engine.command('fault',{scenarioId:'identity-expiry',commandId:'persistent-command'}).lastCommand.duplicate,true);assert.equal(engine.view().incidents.length,1);}finally{engine.close();store.close();}
});
test('automatic clock runs server-side and pause prevents later changes',async t=>{
 const {engine}=setup(t,{intervalMs:20});engine.command('control',{action:'run'});assertCode(()=>engine.command('control',{action:'tick'}),'SIMULATION_RUNNING');await new Promise(resolve=>setTimeout(resolve,90));engine.command('control',{action:'pause'});const tick=engine.view().clock.tick;assert.ok(tick>=1);await new Promise(resolve=>setTimeout(resolve,60));assert.equal(engine.view().clock.tick,tick);
});
test('metric, snapshot and archived run retention is bounded',t=>{
 const {engine,store}=setup(t);for(let i=0;i<7;i++)engine.command('control',{action:'tick',steps:60});const state=engine.view();assert.equal(state.clock.tick,420);assert.equal(state.services[0].history.length,120);
 assert.equal(store.db.prepare('SELECT COUNT(*) AS n FROM sim_snapshots WHERE run_id=?').get(state.runId).n,360);assertCode(()=>engine.replay(state.runId,0),'SNAPSHOT_NOT_FOUND');assert.equal(engine.replay(state.runId,61).clock.tick,61);
 for(let i=0;i<12;i++)engine.command('reset',{seed:i});assert.equal(engine.runs().length,10);assert.equal(store.db.prepare('SELECT COUNT(*) AS n FROM sim_snapshots LEFT JOIN sim_runs ON sim_runs.id=sim_snapshots.run_id WHERE sim_runs.id IS NULL').get().n,0);
});

test('aged fault runbook reduces current causal latency pressure by exactly 65 percent',t=>{
 const {engine}=setup(t);const {engine:baseline}=setup(t);const injected=engine.command('fault',{scenarioId:'query-lock',intensity:2});engine.command('control',{action:'tick',steps:8});baseline.command('control',{action:'tick',steps:8});
 const latency=e=>e.view().services.find(s=>s.id==='orders-db').metrics.latencyMs;const healthy=latency(baseline),before=latency(engine);engine.command('runbook',{actionId:'unlock-query',incidentId:injected.incidents[0].id});const after=latency(engine);
 assert.ok(Math.abs((after-healthy)/(before-healthy)-.35)<.0001);
});
test('resolved postmortem is frozen even when a new fault is injected in the same tick',t=>{
 const {engine}=setup(t);const first=engine.command('fault',{scenarioId:'query-lock'}).incidents[0];engine.command('runbook',{actionId:'unlock-query',incidentId:first.id});engine.command('control',{action:'tick',steps:4});const completed=engine.postmortem(first.id);
 engine.command('fault',{scenarioId:'bad-release',intensity:3});engine.command('control',{action:'tick',steps:2});assert.deepEqual(engine.postmortem(first.id),completed);
});
