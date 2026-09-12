import { randomUUID, createHash } from 'node:crypto';
import { LabError, identifier } from './store.mjs';

const EPOCH = Date.UTC(2026, 0, 1);
const TICK_MS = 5000;
const HISTORY_LIMIT = 120;
const SNAPSHOT_LIMIT = 360;
const RUN_LIMIT = 10;
const NODES = [
  {id:'edge-gateway',name:'Edge Gateway',tier:'edge',latency:18,rps:1200,cpu:18,deps:[['checkout-api',.5],['catalog-api',.3],['identity-api',.2]]},
  {id:'checkout-api',name:'Checkout API',tier:'application',latency:35,rps:600,cpu:26,deps:[['orders-api',.45],['payment-api',.35],['identity-api',.2]]},
  {id:'catalog-api',name:'Catalog API',tier:'application',latency:25,rps:900,cpu:22,deps:[['redis-cache',1]]},
  {id:'orders-api',name:'Orders API',tier:'application',latency:28,rps:550,cpu:25,deps:[['orders-db',.75],['redis-cache',.25]]},
  {id:'payment-api',name:'Payment API',tier:'application',latency:45,rps:450,cpu:20,deps:[['identity-api',1]]},
  {id:'identity-api',name:'Identity API',tier:'application',latency:20,rps:800,cpu:18,deps:[['redis-cache',1]]},
  {id:'redis-cache',name:'Redis Cache',tier:'storage',latency:3,rps:1800,cpu:14,deps:[]},
  {id:'orders-db',name:'Orders Database',tier:'storage',latency:12,rps:500,cpu:24,deps:[]},
];
export const FAULT_SCENARIOS = [
  {id:'query-lock',title:'Database Query Lock',description:'잠긴 Query가 Orders와 Checkout 경로에 지연을 전파합니다.',rootService:'orders-db',expectedAction:'unlock-query',latency:500,error:7,cpu:43},
  {id:'cache-eviction',title:'Cache Eviction Storm',description:'Cache miss로 공통 의존 Service의 부하와 오류가 증가합니다.',rootService:'redis-cache',expectedAction:'warm-cache',latency:110,error:5,cpu:32},
  {id:'identity-expiry',title:'Identity Token Expiry',description:'인증 실패가 Payment와 Checkout의 요청 경로에 전파됩니다.',rootService:'identity-api',expectedAction:'rotate-identity',latency:95,error:22,cpu:18},
  {id:'bad-release',title:'Checkout Bad Release',description:'잘못된 Release의 오류가 Edge까지 전파됩니다.',rootService:'checkout-api',expectedAction:'rollback-release',latency:270,error:16,cpu:28},
];
export const RUNBOOKS = [
  {id:'unlock-query',title:'Release Query Lock',description:'합성 Query lock을 해제하고 처리 대기를 줄입니다.',scenarioId:'query-lock',serviceId:'orders-db',effect:'Fault magnitude reduced 65% immediately, then drained over 4 ticks.'},
  {id:'warm-cache',title:'Warm Cache',description:'합성 Cache를 재적재하여 miss와 연쇄 부하를 줄입니다.',scenarioId:'cache-eviction',serviceId:'redis-cache',effect:'Cache hit ratio recovers and downstream pressure drains over 4 ticks.'},
  {id:'rotate-identity',title:'Rotate Identity Key',description:'합성 인증 Key를 정렬하여 Token 검증 실패를 줄입니다.',scenarioId:'identity-expiry',serviceId:'identity-api',effect:'Authentication failures reduced immediately, then recover over 4 ticks.'},
  {id:'rollback-release',title:'Rollback Release',description:'합성 Checkout Release를 이전 정상 Version으로 복원합니다.',scenarioId:'bad-release',serviceId:'checkout-api',effect:'Release fault reduced immediately, then recover over 4 ticks.'},
];
const fail = (code,message,status=400) => {throw new LabError(status,code,message);};
const rounded = value => Math.round(value*100)/100;
const stamp = tick => new Date(EPOCH+tick*TICK_MS).toISOString();
function fields(value, required, optional=[]) {
  if(!value || typeof value!=='object' || Array.isArray(value) || required.some(k=>!Object.hasOwn(value,k)) || Object.keys(value).some(k=>![...required,...optional,'commandId'].includes(k)))fail('INVALID_FIELDS','Unexpected or missing simulation fields.');
  if(value.commandId!==undefined)identifier(value.commandId);
}
function seedValue(value){if(!Number.isInteger(value)||value<0||value>2147483647)fail('INVALID_SEED','seed must be an integer from 0 to 2147483647.');return value;}
function noise(seed,tick,index){let x=((seed|0)^Math.imul(tick+1,1103515245)^Math.imul(index+7,2654435761))>>>0;x^=x>>>16;x=Math.imul(x,2246822507)>>>0;x^=x>>>13;return (x>>>0)/4294967295;}
const publicScenario = ({latency,error,cpu,...item})=>item;

export class SimulationEngine {
  constructor(db,{intervalMs=1000}={}) {
    this.db=db;this.intervalMs=intervalMs;this.timer=null;
    db.exec(`CREATE TABLE IF NOT EXISTS sim_runs (id TEXT PRIMARY KEY, seed INTEGER NOT NULL, latest_tick INTEGER NOT NULL, state_json TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS sim_meta (id INTEGER PRIMARY KEY CHECK(id=1), active_run TEXT NOT NULL REFERENCES sim_runs(id));
      CREATE TABLE IF NOT EXISTS sim_snapshots (run_id TEXT NOT NULL REFERENCES sim_runs(id) ON DELETE CASCADE, tick INTEGER NOT NULL, state_json TEXT NOT NULL, PRIMARY KEY(run_id,tick));
      CREATE TABLE IF NOT EXISTS sim_commands (command_id TEXT PRIMARY KEY, signature TEXT NOT NULL);`);
    const row=db.prepare('SELECT r.state_json FROM sim_meta m JOIN sim_runs r ON r.id=m.active_run WHERE m.id=1').get();
    if(row){this.state=JSON.parse(row.state_json);if(this.state.clock.running){this.state.clock.running=false;this.audit('restored',null,null,'Process restarted; simulation restored in paused mode.');this.persist();}}
    else{this.state=this.fresh(42);this.calculate();this.audit('reset',null,null,'New deterministic simulation created.');this.persist();}
  }
  fresh(seed){return {schemaVersion:2,simulation:true,runId:randomUUID(),clock:{tick:0,simulatedAt:stamp(0),running:false,intervalMs:this.intervalMs,secondsPerTick:5,seed},services:[],faults:[],incidents:[],audit:[],auditSequence:0};}
  close(){if(this.timer){clearInterval(this.timer);this.timer=null;}}
  audit(kind,serviceId,incidentId,message,extra={}){
    const entry={id:`${this.state.runId}-${++this.state.auditSequence}`,tick:this.state.clock.tick,at:this.state.clock.simulatedAt,kind,serviceId,incidentId,message,...extra};
    this.state.audit.push(entry);this.state.audit=this.state.audit.slice(-300);
    const item=this.state.incidents.find(item=>item.id===incidentId);if(item)item.timeline.push(entry);
    return entry;
  }
  persist(){
    const serialized=JSON.stringify(this.state);
    this.db.prepare('INSERT INTO sim_runs VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET latest_tick=excluded.latest_tick,state_json=excluded.state_json').run(this.state.runId,this.state.clock.seed,this.state.clock.tick,serialized);
    this.db.prepare('INSERT INTO sim_meta VALUES (1,?) ON CONFLICT(id) DO UPDATE SET active_run=excluded.active_run').run(this.state.runId);
    this.db.prepare('INSERT INTO sim_snapshots VALUES (?,?,?) ON CONFLICT(run_id,tick) DO UPDATE SET state_json=excluded.state_json').run(this.state.runId,this.state.clock.tick,serialized);
    this.db.prepare('DELETE FROM sim_snapshots WHERE run_id=? AND tick<?').run(this.state.runId,Math.max(0,this.state.clock.tick-SNAPSHOT_LIMIT+1));
    const old=this.db.prepare('SELECT id FROM sim_runs WHERE id<>? ORDER BY rowid DESC LIMIT -1 OFFSET ?').all(this.state.runId,RUN_LIMIT-1);
    for(const row of old)this.db.prepare('DELETE FROM sim_runs WHERE id=?').run(row.id);
  }
  runs(){return this.db.prepare('SELECT id,seed,latest_tick,state_json FROM sim_runs ORDER BY rowid DESC').all().map(row=>({id:row.id,seed:row.seed,latestTick:row.latest_tick,incidentCount:JSON.parse(row.state_json).incidents.length,active:row.id===this.state.runId,earliestTick:Math.max(0,row.latest_tick-SNAPSHOT_LIMIT+1)}));}
  view(state=this.state,replay=false){
    const result=structuredClone(state);delete result.auditSequence;
    result.replay=replay;result.scenarios=FAULT_SCENARIOS.map(publicScenario);result.runbooks=RUNBOOKS;
    result.topology={edges:NODES.flatMap(node=>node.deps.map(([target,weight])=>({source:node.id,target,weight})))};
    result.runs=this.runs();result.retention={historyTicks:HISTORY_LIMIT,replayTicks:SNAPSHOT_LIMIT,runs:RUN_LIMIT};
    const edge=result.services.find(node=>node.id==='edge-gateway');
    result.summary={healthy:result.services.filter(s=>s.status==='healthy').length,degraded:result.services.filter(s=>s.status==='degraded').length,critical:result.services.filter(s=>s.status==='critical').length,activeIncidents:result.incidents.filter(i=>i.status!=='resolved').length,edgeLatencyMs:edge.metrics.latencyMs,edgeErrorRate:edge.metrics.errorRate,throughputRps:edge.metrics.rps};
    return result;
  }
  replay(runId,tick){identifier(runId);if(!Number.isInteger(tick)||tick<0)fail('INVALID_TICK','Replay tick must be a nonnegative integer.');const row=this.db.prepare('SELECT state_json FROM sim_snapshots WHERE run_id=? AND tick=?').get(runId,tick);if(!row)fail('SNAPSHOT_NOT_FOUND','Snapshot unavailable or outside retention.',404);return this.view(JSON.parse(row.state_json),true);}
  command(type,input){
    const value=input || {};const commandId=value.commandId;const signature=JSON.stringify({type,payload:Object.fromEntries(Object.entries(value).filter(([k])=>k!=='commandId').sort(([a],[b])=>a.localeCompare(b)))});
    if(commandId!==undefined){identifier(commandId);const prior=this.db.prepare('SELECT signature FROM sim_commands WHERE command_id=?').get(commandId);if(prior){if(prior.signature!==signature)fail('IDEMPOTENCY_CONFLICT','Command ID already exists with different input.',409);return {...this.view(),lastCommand:{commandId,duplicate:true}};}}
    const before=structuredClone(this.state);this.db.exec('BEGIN IMMEDIATE');
    try{
      if(type==='control')this.control(value);
      else if(type==='reset'){fields(value,['seed']);seedValue(value.seed);this.state.clock.running=false;this.persist();this.state=this.fresh(value.seed);this.calculate();this.audit('reset',null,null,'New run created; previous run retained for replay.');}
      else if(type==='fault')this.inject(value);
      else if(type==='runbook')this.runbook(value);
      else fail('INVALID_COMMAND','Unknown simulation command.');
      this.persist();if(commandId!==undefined)this.db.prepare('INSERT INTO sim_commands VALUES (?,?)').run(commandId,signature);
      this.db.exec('COMMIT');
    }catch(error){this.db.exec('ROLLBACK');this.state=before;throw error;}
    this.syncTimer();return {...this.view(),lastCommand:{commandId:commandId||null,duplicate:false}};
  }
  control(value){
    fields(value,['action'],['steps']);if(!['run','pause','tick'].includes(value.action))fail('INVALID_ACTION','Use run, pause or tick.');
    if(value.steps!==undefined && value.action!=='tick')fail('INVALID_STEPS','steps is only valid for tick.');
    if(value.action==='tick'){
      const steps=value.steps??1;if(!Number.isInteger(steps)||steps<1||steps>60)fail('INVALID_STEPS','steps must be an integer from 1 to 60.');
      if(this.state.clock.running)fail('SIMULATION_RUNNING','Pause before manual ticks.',409);
      for(let i=0;i<steps;i++)this.advance();
    }else{const running=value.action==='run';if(this.state.clock.running!==running){this.state.clock.running=running;this.audit(value.action,null,null,running?'Automatic clock started.':'Automatic clock paused.');}}
  }
  syncTimer(){
    if(this.state.clock.running&&!this.timer){this.timer=setInterval(()=>{
      const before=structuredClone(this.state);
      try{this.db.exec('BEGIN IMMEDIATE');this.advance();this.persist();this.db.exec('COMMIT');}
      catch(error){try{this.db.exec('ROLLBACK');}catch{}this.state=before;this.state.clock.running=false;this.state.engineError='Simulation paused after a persistence error.';this.close();console.error('Simulation timer stopped:',error.code||error.name);}
    },this.intervalMs);this.timer.unref();}
    if(!this.state.clock.running)this.close();
  }
  advance(){
    this.state.clock.tick++;this.state.clock.simulatedAt=stamp(this.state.clock.tick);
    for(const fault of this.state.faults){
      if(fault.status==='mitigated'&&this.state.clock.tick-fault.mitigatedTick>=4){fault.status='resolved';fault.resolvedTick=this.state.clock.tick;const incident=this.state.incidents.find(i=>i.id===fault.incidentId);incident.status='resolved';incident.resolvedTick=this.state.clock.tick;this.audit('recovery',fault.serviceId,incident.id,'Fault drained after 4 ticks; synthetic recovery probe passed.');}
    }
    this.calculate();this.persist();
  }
  inject(value){
    fields(value,['scenarioId'],['intensity']);const scenario=FAULT_SCENARIOS.find(s=>s.id===value.scenarioId);if(!scenario)fail('INVALID_SCENARIO','Unknown fault scenario.');
    const intensity=value.intensity??2;if(!Number.isInteger(intensity)||intensity<1||intensity>3)fail('INVALID_INTENSITY','intensity must be 1, 2 or 3.');
    if(this.state.faults.some(f=>f.scenarioId===scenario.id&&f.status!=='resolved'))fail('FAULT_ALREADY_ACTIVE','Resolve the existing fault before injecting the same scenario again.',409);
    if(this.state.incidents.length>=100)fail('RUN_CAPACITY','Start a new run after 100 incidents.',409);
    const incidentId=randomUUID(),faultId=randomUUID();
    this.state.incidents.push({id:incidentId,scenarioId:scenario.id,title:scenario.title,service:scenario.rootService,status:'open',startedTick:this.state.clock.tick,mitigatedTick:null,resolvedTick:null,impactServices:[],peakLatencyMs:0,peakErrorRate:0,timeline:[],metricHistory:[],intensity});
    this.state.faults.push({id:faultId,scenarioId:scenario.id,incidentId,serviceId:scenario.rootService,status:'active',startedTick:this.state.clock.tick,mitigatedTick:null,resolvedTick:null,intensity});
    this.audit('fault_injected',scenario.rootService,incidentId,`Injected ${scenario.title}, intensity ${intensity}.`,{faultId,intensity});this.calculate();
  }
  runbook(value){
    fields(value,['actionId','incidentId']);identifier(value.incidentId);
    const book=RUNBOOKS.find(b=>b.id===value.actionId);if(!book)fail('INVALID_RUNBOOK','Unknown runbook.');
    const incident=this.state.incidents.find(i=>i.id===value.incidentId);if(!incident)fail('NOT_FOUND','Incident not found in the active run.',404);
    if(book.scenarioId!==incident.scenarioId)fail('RUNBOOK_MISMATCH','This runbook does not address the incident root cause.',409);
    if(incident.status!=='open')fail('INVALID_ACTION_STATE','Runbook already applied or incident resolved.',409);
    const fault=this.state.faults.find(f=>f.incidentId===incident.id),before=structuredClone(this.state.services.find(s=>s.id===incident.service).metrics);
    fault.magnitudeAtMitigation=1+Math.min(this.state.clock.tick-fault.startedTick,6)*.08;fault.status='mitigated';fault.mitigatedTick=this.state.clock.tick;incident.status='mitigating';incident.mitigatedTick=this.state.clock.tick;
    this.calculate();const after=this.state.services.find(s=>s.id===incident.service).metrics;
    this.audit('runbook_applied',incident.service,incident.id,`${book.title} applied; causal fault pressure reduced 65%.`,{actionId:book.id,before,after:structuredClone(after)});
  }
  calculate(){
    const old=new Map(this.state.services.map(s=>[s.id,s])),results=new Map(),tick=this.state.clock.tick,seed=this.state.clock.seed;
    const build=(id)=>{
      if(results.has(id))return results.get(id);
      const node=NODES.find(n=>n.id===id),index=NODES.indexOf(node),deps=node.deps.map(([id,weight])=>({service:build(id),weight}));
      const jitter=1+(noise(seed,tick,index)-.5)*.08;
      const baseLatency=node.latency + Math.max(0,...deps.map(d=>d.service.baseline.latencyMs*.65));
      let latency=baseLatency*jitter,error=.08+noise(seed,tick,index+12)*.12,cpu=node.cpu*jitter,cacheHit=id==='redis-cache'?97:null;
      const causes=new Set(),local=[];
      for(const fault of this.state.faults.filter(f=>f.serviceId===id&&f.status!=='resolved')){
        const config=FAULT_SCENARIOS.find(s=>s.id===fault.scenarioId),age=tick-fault.startedTick;
        const magnitude=fault.status==='active'?(1+Math.min(age,6)*.08):(fault.magnitudeAtMitigation??1)*.35*Math.max(0,1-(tick-fault.mitigatedTick)/4);
        const factor=fault.intensity*magnitude;latency+=config.latency*factor;error+=config.error*factor;cpu+=config.cpu*factor;
        if(id==='redis-cache')cacheHit=Math.max(1,97-28*factor);
        if(factor>0){causes.add(fault.id);local.push(fault.id);}
      }
      for(const {service,weight} of deps){latency+=Math.max(0,service.metrics.latencyMs-service.baseline.latencyMs)*weight*.85;error=100*(1-(1-Math.min(error,95)/100)*(1-Math.min(service.metrics.errorRate,95)/100*weight*.9));cpu+=Math.max(0,service.metrics.latencyMs-service.baseline.latencyMs)*weight*.025;for(const cause of service.causes)causes.add(cause);}
      error=Math.min(99,error);const offered=node.rps*(1+(noise(seed,tick,index+30)-.5)*.12);
      const metrics={latencyMs:rounded(latency),errorRate:rounded(error),rps:Math.round(offered*(1-error/100)),cpuPercent:rounded(Math.min(99,cpu)),cacheHitPercent:cacheHit===null?null:rounded(cacheHit)};
      const status=error>=10||latency>baseLatency*6+100?'critical':error>=2||latency>baseLatency*2+30?'degraded':'healthy';
      const point={tick,...metrics};const history=[...(old.get(id)?.history||[])];if(history.at(-1)?.tick===tick)history[history.length-1]=point;else history.push(point);
      const result={id,name:node.name,tier:node.tier,dependencies:node.deps.map(([id])=>id),status,metrics,baseline:{latencyMs:rounded(baseLatency),rps:node.rps,cpuPercent:node.cpu},history:history.slice(-HISTORY_LIMIT),causes:[...causes].sort(),rootFault:local.length>0};results.set(id,result);return result;
    };
    this.state.services=NODES.map(n=>build(n.id));
    for(const incident of this.state.incidents){
      if(incident.finalized)continue;
      const fault=this.state.faults.find(f=>f.incidentId===incident.id),affected=this.state.services.filter(s=>s.causes.includes(fault.id));
      const prior=incident.impactServices.join(',');incident.impactServices=[...new Set([...incident.impactServices,...affected.map(s=>s.id)])].sort();
      if(prior!==incident.impactServices.join(','))this.audit('propagation',incident.service,incident.id,`Causal impact reached ${incident.impactServices.join(', ')}.`,{impactServices:[...incident.impactServices]});
      if(incident.status==='resolved'&&incident.resolvedTick!==tick)continue;
      const impacted=this.state.services.filter(s=>incident.impactServices.includes(s.id));
      const point={tick,latencyMs:Math.max(0,...impacted.map(s=>s.metrics.latencyMs)),errorRate:Math.max(0,...impacted.map(s=>s.metrics.errorRate)),impactedCount:affected.length};
      incident.peakLatencyMs=Math.max(incident.peakLatencyMs,point.latencyMs);incident.peakErrorRate=Math.max(incident.peakErrorRate,point.errorRate);
      if(incident.metricHistory.at(-1)?.tick===tick)incident.metricHistory[incident.metricHistory.length-1]=point;else incident.metricHistory.push(point);
      incident.metricHistory=incident.metricHistory.slice(-HISTORY_LIMIT);
      if(incident.status==='resolved')incident.finalized=true;
    }
  }
  postmortem(id){
    identifier(id);let owner=this.state,item=owner.incidents.find(i=>i.id===id);
    if(!item){for(const row of this.db.prepare('SELECT state_json FROM sim_runs ORDER BY rowid DESC').all()){const run=JSON.parse(row.state_json),found=run.incidents.find(i=>i.id===id);if(found){owner=run;item=found;break;}}}
    if(!item)fail('NOT_FOUND','Incident postmortem not found within retained runs.',404);
    const fault=owner.faults.find(f=>f.incidentId===id),scenario=FAULT_SCENARIOS.find(s=>s.id===item.scenarioId);
    const paths=[];const walk=(node,path)=>{const parents=NODES.filter(n=>n.deps.some(([dep])=>dep===node));if(!parents.length)paths.push(path);for(const parent of parents)walk(parent.id,[...path,parent.id]);};walk(item.service,[item.service]);
    const content={schemaVersion:1,simulation:true,runId:owner.runId,seed:owner.clock.seed,incident:structuredClone(item),rootCause:{scenarioId:scenario.id,serviceId:item.service,intensity:fault.intensity,description:scenario.description},causalPaths:paths,timing:{startedTick:item.startedTick,mitigatedTick:item.mitigatedTick,resolvedTick:item.resolvedTick,detectionToMitigationSeconds:item.mitigatedTick===null?null:(item.mitigatedTick-item.startedTick)*5,recoverySeconds:item.resolvedTick===null?null:(item.resolvedTick-item.startedTick)*5},correctiveAction:RUNBOOKS.find(b=>b.id===scenario.expectedAction),outcome:item.status==='resolved'?'Resolved in deterministic synthetic model':'Still active in synthetic model',limitations:['All metrics are generated by the documented deterministic model, not production observations.','Dependency propagation is a weighted acyclic model, not a network or load generator.','Replay retains latest 360 ticks per run and 10 runs; incident metrics retain latest 120 ticks.']};
    return {...content,integrity:{algorithm:'SHA-256',scope:'JSON.stringify(report without integrity)',sha256:createHash('sha256').update(JSON.stringify(content)).digest('hex')}};
  }
}
