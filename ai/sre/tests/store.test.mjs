import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { LabStore } from '../src/store.mjs';
const sample = (overrides={}) => ({eventId:'e1',incidentId:'i1',service:'checkout-api',kind:'alert',message:'Synthetic timeout',occurredAt:'2026-09-12T00:00:00.000Z',...overrides});
function use(t){const store=new LabStore();t.after(()=>store.close());return store;}
function code(fn,expected){assert.throws(fn,error=>error.code===expected);}

test('state machine requires alert then mitigation before recovery',t=>{
 const s=use(t);code(()=>s.ingest([sample({kind:'note'})]),'ALERT_REQUIRED');assert.equal(s.list().eventCount,0);
 s.ingest([sample()]);code(()=>s.ingest([sample({eventId:'e2',kind:'recovery'})]),'MITIGATION_REQUIRED');
 s.ingest([sample({eventId:'e3',kind:'mitigation'}),sample({eventId:'e4',kind:'recovery'})]);
 const detail=s.detail('i1');assert.equal(detail.status,'resolved');assert.equal(detail.revision,3);assert.deepEqual(detail.events.map(e=>e.kind),['alert','mitigation','recovery']);
 code(()=>s.ingest([sample({eventId:'e5',kind:'note'})]),'INCIDENT_RESOLVED');
});
test('same event ID and normalized payload return existing sequence without mutating state',t=>{
 const s=use(t);const first=s.ingest([sample()]);const reordered=Object.fromEntries(Object.entries(sample()).reverse());const retry=s.ingest([reordered]);
 assert.equal(retry[0].duplicate,true);assert.equal(retry[0].sequence,first[0].sequence);assert.equal(s.list().eventCount,1);assert.equal(s.detail('i1').revision,1);
 code(()=>s.ingest([sample({message:'Conflicting payload'})]),'IDEMPOTENCY_CONFLICT');
});
test('batch failure rolls back earlier events and aggregate mutations',t=>{
 const s=use(t);s.ingest([sample()]);code(()=>s.ingest([sample({eventId:'e2',kind:'mitigation'}),sample({message:'ID conflict'})]),'IDEMPOTENCY_CONFLICT');
 assert.equal(s.detail('i1').status,'open');assert.equal(s.list().eventCount,1);assert.equal(s.detail('i1').revision,1);
});
test('timestamps and service boundaries reject invalid input before persistence',t=>{
 const s=use(t);s.ingest([sample()]);
 code(()=>s.ingest([sample({eventId:'e2',kind:'note',occurredAt:'2026-09-11T23:59:59.000Z'})]),'OUT_OF_ORDER');
 code(()=>s.ingest([sample({eventId:'e2',kind:'note',service:'identity-api'})]),'SERVICE_CONFLICT');
 for(const event of [sample({occurredAt:'2026-02-30T00:00:00.000Z'}),sample({occurredAt:'tomorrow'}),sample({message:''}),sample({service:'private-service'}),{...sample(),password:'not-allowed'}])assert.throws(()=>s.ingest([event]));
 assert.equal(s.list().eventCount,1);
});
test('search treats SQL metacharacters literally and validates query bounds',t=>{
 const s=use(t);s.ingest([sample({message:'100%_synthetic'}),sample({eventId:'e2',incidentId:'i2',message:'unrelated'})]);
 assert.equal(s.list(new URLSearchParams({q:'%_'})).matched,1);
 assert.equal(s.list(new URLSearchParams({q:"' OR 1=1 --"})).matched,0);
 for(const query of ['limit=0','limit=101','limit=1.5','limit=-1','limit=1&limit=2','foo=bar','status=deleted','service=unknown','q='+ 'a'.repeat(81)])code(()=>s.list(new URLSearchParams(query)),'INVALID_QUERY');
 assert.equal(s.list(new URLSearchParams('limit=1')).incidents.length,1);assert.equal(s.list().matched,2);
});
test('timeline and idempotency survive closing and reopening SQLite',async t=>{
 const dir=await mkdtemp(join(tmpdir(),'incident-lab-test-'));t.after(()=>rm(dir,{recursive:true,force:true}));const path=join(dir,'test.sqlite');
 let s=new LabStore(path);s.ingest([sample(),sample({eventId:'e2',kind:'mitigation'}),sample({eventId:'e3',kind:'recovery'})]);const before=s.detail('i1');s.close();
 s=new LabStore(path);try{assert.deepEqual(s.detail('i1'),before);assert.equal(s.ingest([sample()])[0].duplicate,true);assert.equal(s.list().eventCount,3);}finally{s.close();}
});
test('synthetic scenario actions drive real stored state without fabricated metrics',t=>{
 const s=use(t),first=s.scenario('checkout-timeout');assert.equal(first.events.length,3);assert.equal(first.synthetic,true);
 assert.equal(s.action(first.id,'mitigate').status,'mitigating');assert.equal(s.action(first.id,'recover').status,'resolved');
 assert.equal(s.list().eventCount,5);assert.deepEqual(s.list().counts,{open:0,mitigating:0,resolved:1});
 code(()=>s.action(first.id,'mitigate'),'INVALID_ACTION_STATE');code(()=>s.scenario('unknown'),'INVALID_SCENARIO');
});
