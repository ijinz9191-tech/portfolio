'use strict';
const $ = selector => document.querySelector(selector);
const state = { selected: null, detail: null, busy: false, revision: 0, scenarios: [] };
const labels = { open: 'OPEN', mitigating: 'MITIGATING', resolved: 'RESOLVED' };
function el(tag, text, className) { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node; }
function time(value) { return new Date(value).toLocaleTimeString('ko-KR', {hour12:false}); }
function announce(message, error = false) { const target = $(error ? '#error' : '#notice'); target.textContent = message; target.hidden = false; }
async function api(path, options = {}) {
  const response = await fetch(path, {cache:'no-store', ...options, headers: {'Content-Type':'application/json',...options.headers}});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error?.message || `HTTP ${response.status}`);
  return data;
}
function write(path, body) { return api(path,{method:'POST',body:JSON.stringify(body)}); }
function badge(status) { return el('span',labels[status],`badge ${status}`); }
function actionButton(text, fn, enabled = true, style = '') { const button = el('button',text,`button ${style}`); button.type='button';button.disabled=state.busy || !enabled;button.dataset.write='true';button.addEventListener('click',fn);return button; }
function renderScenarios() {
  $('#scenario-list').replaceChildren(...state.scenarios.map((item,index)=>{
    const card=el('article',undefined,'scenario');const top=el('div',undefined,'scenario-top');top.append(el('span',item.service),el('span',['SQL','KV','SSO'][index] || 'API','scenario-icon'));
    const button=actionButton('시나리오 실행 →',()=>mutate(async()=>{const result=await write('/api/scenarios',{scenario:item.id});state.selected=result.id;announce('합성 이벤트 3건을 저장했습니다. 아래 타임라인에서 조치를 적용하세요.');}));
    card.append(top,el('h3',item.title),el('p',item.description),button);return card;
  }));
}
function renderList(data) {
  for (const status of Object.keys(labels)) $(`#${status}-count`).textContent=data.counts[status];
  $('#event-count').textContent=data.eventCount;$('#matched-count').textContent=data.matched;
  $('#list-caption').textContent=`검색 ${data.matched}건 중 ${data.incidents.length}건 표시 · 최신 ${data.limit}건 · 전체 합성 데이터 집계`;
  if (!data.incidents.length) { $('#incident-list').replaceChildren(el('p','조건에 맞는 장애가 없습니다. 시나리오를 실행하거나 검색 조건을 바꿔보세요.','empty'));return; }
  $('#incident-list').replaceChildren(...data.incidents.map(item=>{
    const row=el('button',undefined,`incident-row${item.id===state.selected?' selected':''}`);row.type='button';row.setAttribute('aria-pressed',String(item.id===state.selected));
    const top=el('div',undefined,'row-top');top.append(el('strong',item.title),badge(item.status));
    const bottom=el('div',undefined,'row-bottom');bottom.append(el('span',item.service),el('span',`${time(item.updatedAt)} · ${item.revision} events`));row.append(top,bottom);
    row.addEventListener('click',async()=>{state.selected=item.id;await refresh();});return row;
  }));
}
function renderDetail(data) {
  if (!data) return;
  const root=el('div');const top=el('div',undefined,'detail-top');top.append(el('p','03 / TRACE & RECOVER','eyebrow'),badge(data.status));
  const meta=el('div',undefined,'detail-meta');meta.append(el('span',data.service),el('span',`${data.events.length} events`),el('span','SYNTHETIC'));
  const actions=el('div',undefined,'action-bar');
  actions.append(actionButton('조치 적용',()=>mutate(async()=>{await write(`/api/incidents/${data.id}/actions`,{action:'mitigate'});announce('조치를 기록했습니다. 다음으로 복구를 확인하세요.');}),data.status==='open'),actionButton('복구 확인',()=>mutate(async()=>{await write(`/api/incidents/${data.id}/actions`,{action:'recover'});announce('복구 이벤트가 저장되었습니다. 전체 타임라인을 확인할 수 있습니다.');}),data.status==='mitigating','teal'),actionButton('중복 재전송',()=>mutate(async()=>{const {sequence,...event}=data.events.at(-1);const result=await write('/api/events',{events:[event]});announce(result.results[0].duplicate?'같은 이벤트를 재전송했습니다. 중복으로 확인되어 저장 건수와 상태가 유지됩니다.':'이벤트가 새로 저장되었습니다.');}),true,'secondary'));
  const hint=data.status==='open'?'먼저 조치를 적용하세요. 조치가 기록되기 전에는 복구 상태로 바뀌지 않습니다.':data.status==='mitigating'?'조치가 기록됐습니다. 합성 Probe의 복구 결과를 확인해 장애를 종료하세요.':'복구가 기록됐습니다. 종료된 장애의 상태는 변경할 수 없습니다. 새로운 장애는 시나리오로 시작하세요.';
  const timeline=el('ol',undefined,'timeline');
  for (const event of data.events) {const row=el('li',undefined,`event ${event.kind}`);const heading=el('div',undefined,'event-head');heading.append(el('strong',event.kind.toUpperCase()),el('time',time(event.occurredAt)));row.append(heading,el('p',event.message),el('code',`#${event.sequence} · ${event.eventId.slice(0,8)} · ${event.occurredAt}`));timeline.append(row);}
  root.append(top,el('h3',data.title,'detail-title'),el('p',data.id,'detail-id'),meta,actions,el('p',hint,'action-help'),el('p','EVENT TIMELINE · UTC ORDER / LOCAL TIME DISPLAY','timeline-title'),timeline);
  $('#detail').replaceChildren(root);
}
function busy(value) {state.busy=value;renderScenarios();if(state.detail)renderDetail(state.detail);}
async function mutate(task) {
  if(state.busy)return;
  $('#error').hidden=true;$('#notice').hidden=true;busy(true);
  try {await task();await refresh();} catch(error){announce(error.message,true);} finally{busy(false);}
}
async function refresh() {
  const revision=++state.revision;
  const query=new URLSearchParams(new FormData($('#filters')));
  $('#refresh').disabled=true;
  try {
    const [health,data]=await Promise.all([api('/api/health'),api('/api/incidents?'+query)]);
    if(revision!==state.revision)return;
    $('#health-dot').className='health-dot';$('#health-label').textContent='API · SQLite 연결됨';$('#health-detail').textContent=`실행 ${health.uptimeSeconds}초 · 로컬 저장`;
    if(!state.selected && data.incidents.length)state.selected=data.incidents[0].id;
    renderList(data);
    if(state.selected) {const detail=await api('/api/incidents/'+state.selected);if(revision!==state.revision)return;state.detail=detail;renderDetail(detail);}
    $('#error').hidden=true;
  }catch(error){if(revision!==state.revision)return;$('#health-dot').className='health-dot offline';$('#health-label').textContent='API 연결 실패';$('#health-detail').textContent='화면의 이전 데이터는 최신 상태가 아닙니다.';announce(error.message+' 서버 실행 상태를 확인한 뒤 새로고침하세요.',true);}
  finally{if(revision===state.revision)$('#refresh').disabled=false;}
}
$('#filters').addEventListener('submit',event=>{event.preventDefault();refresh();});
$('#status-filter').addEventListener('change',refresh);$('#service-filter').addEventListener('change',refresh);
$('#refresh').addEventListener('click',async()=>{try{if(!state.scenarios.length){state.scenarios=(await api('/api/scenarios')).scenarios;renderScenarios();}await refresh();}catch(error){announce(error.message,true);}});
async function init(){
  try{const data=await api('/public.data.json');const url=new URL(data.repositoryUrl);if(url.protocol!=='https:' || url.username || url.password)throw new Error('Invalid repository URL');const link=el('a','GitHub에서 Source 보기 ↗');link.href=url.href;link.rel='noopener noreferrer';$('#repository-link').replaceChildren(link);}catch{announce('Source 링크를 불러오지 못했습니다.',true);}
  try{state.scenarios=(await api('/api/scenarios')).scenarios;renderScenarios();}catch(error){$('#scenario-list').replaceChildren(el('p','시나리오 API에 연결할 수 없습니다. Node 서버를 실행한 뒤 새로고침하세요.','muted'));announce(error.message,true);}
  await refresh();
}
init();
