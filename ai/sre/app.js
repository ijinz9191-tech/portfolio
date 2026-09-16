'use strict';
const $ = selector => document.querySelector(selector);
const NS = 'http://www.w3.org/2000/svg';
const ui = { data: null, selectedService: 'edge-gateway', selectedIncident: null, selectedScenario: null, busy: false, replay: false, connected: false, request: 0, poll: null, scenarioSignature: '', incidentSignature: '', runSignature: '', noticeTimer: null };
const number = (value, decimals = 0) => Number.isFinite(Number(value)) ? Number(value).toLocaleString('en-US', { maximumFractionDigits: decimals, minimumFractionDigits: decimals }) : '—';
const node = (tag, text, className) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (className) n.className = className; return n; };
function svgNode(tag, attrs = {}, text) { const n = document.createElementNS(NS, tag); for (const [key, value] of Object.entries(attrs)) n.setAttribute(key, String(value)); if (text !== undefined) n.textContent = text; return n; }
function announce(message, error = false) {
  const target = $(error ? '#error' : '#notice'); target.textContent = message; target.hidden = false;
  if (!error) { clearTimeout(ui.noticeTimer); ui.noticeTimer = setTimeout(() => { target.hidden = true; }, 6500); }
}
async function api(path, options = {}) {
  const response = await fetch(path, { cache: 'no-store', ...options, headers: { 'Content-Type': 'application/json', ...options.headers } });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error?.message || 'HTTP ' + response.status);
  return data;
}
function connection(ok) { ui.connected = ok; $('#health-label').className = 'connection' + (ok ? '' : ' offline'); $('#health-label').textContent = ok ? 'API · SQLite connected' : 'API 연결 실패 · 이전 상태'; }
function badge(value) { return node('span', String(value).toUpperCase(), 'badge ' + value); }
function updateButtons() {
  const disabled = ui.busy || ui.replay || !ui.connected || !ui.data;
  for (const id of ['run', 'inject', 'reset']) $('#' + id).disabled = disabled;
  $('#step').disabled = disabled || !!ui.data?.clock.running;
  $('#tick-steps').disabled = disabled || !!ui.data?.clock.running;
  $('#inject').disabled = disabled || !ui.selectedScenario;
  $('#load-replay').disabled = ui.busy || !ui.connected || !$('#run-select').value;
  $('#back-live').disabled = ui.busy;
  $('#refresh').disabled = ui.busy;
  document.querySelectorAll('[data-runbook]').forEach(button => { button.disabled = disabled || button.dataset.available !== 'true'; });
}
async function mutation(path, payload, message) {
  if (ui.busy || ui.replay || !ui.connected) return;
  ui.busy = true; ui.request++; updateButtons(); $('#error').hidden = true;
  try { const data = await api(path, { method: 'POST', body: JSON.stringify(payload) }); accept(data); if (message) announce(message); }
  catch (error) { announce(error.message, true); }
  finally { ui.busy = false; updateButtons(); }
}
async function refresh(manual = false) {
  if (ui.busy || (ui.replay && !manual)) return;
  const request = ++ui.request;
  try {
    const data = ui.replay && manual ? await api('/api/sim/runs/' + encodeURIComponent(ui.data.runId) + '?tick=' + ui.data.clock.tick) : await api('/api/sim/state');
    if (request !== ui.request) return; connection(true); $('#error').hidden = true; accept(data);
  } catch (error) { if (request !== ui.request) return; connection(false); announce(error.message + ' · 서버 실행 상태를 확인해 주세요. 표시된 이전 상태는 최신 값이 아닙니다.', true); updateButtons(); }
}
function accept(data) {
  if (!data || data.schemaVersion !== 2 || !Array.isArray(data.services) || !data.clock) throw new Error('Simulation API v2 응답이 필요합니다.');
  ui.data = data; connection(true); render();
}
function chart(target, history, key, compact = false) {
  const root = $(target), width = compact ? 240 : 400, height = compact ? 30 : 140;
  const left = compact ? 0 : 38, right = compact ? 2 : 8, top = compact ? 3 : 12, bottom = compact ? 3 : 24;
  const rows = (history || []).filter(item => Number.isFinite(item[key]));
  root.replaceChildren();
  if (!rows.length) { if (!compact) root.append(svgNode('text', { x: 200, y: 70, 'text-anchor': 'middle', class: 'chart-axis' }, '기록된 Metric 없음')); return; }
  const max = Math.max(...rows.map(item => item[key]), key === 'errorRate' ? 1 : 10) * 1.15;
  const px = index => left + index / Math.max(1, rows.length - 1) * (width - left - right);
  const py = value => top + (1 - value / max) * (height - top - bottom);
  if (!compact) {
    for (let i = 0; i < 3; i++) { const value = max * i / 2, y = py(value); root.append(svgNode('line', { x1: left, y1: y, x2: width - right, y2: y, class: 'chart-grid' }), svgNode('text', { x: left - 7, y: y + 3, 'text-anchor': 'end', class: 'chart-axis' }, number(value, max < 5 ? 1 : 0))); }
    root.append(svgNode('text', { x: left, y: height - 4, class: 'chart-axis' }, 'T' + rows[0].tick), svgNode('text', { x: width - right, y: height - 4, 'text-anchor': 'end', class: 'chart-axis' }, 'T' + rows.at(-1).tick));
  }
  const points = rows.map((item, i) => [px(i), py(item[key])]);
  const line = points.map(([x, y], i) => (i ? 'L' : 'M') + x.toFixed(2) + ',' + y.toFixed(2)).join(' ');
  if (points.length > 1) root.append(svgNode('path', { d: line + ' L' + points.at(-1)[0] + ',' + (height - bottom) + ' L' + left + ',' + (height - bottom) + ' Z', class: 'chart-area' }));
  root.append(svgNode('path', { d: line, class: 'chart-line' }), svgNode('circle', { cx: points.at(-1)[0], cy: points.at(-1)[1], r: compact ? 2 : 3, class: 'chart-point' }));
  root.setAttribute('aria-label', key + ': ' + rows.length + '개 Snapshot, 현재 ' + number(rows.at(-1)[key], 1) + ', Tick ' + rows[0].tick + '부터 ' + rows.at(-1).tick);
}
const positions = { 'edge-gateway': [450, 45], 'identity-api': [105, 155], 'checkout-api': [450, 155], 'catalog-api': [765, 155], 'orders-api': [330, 255], 'payment-api': [570, 255], 'redis-cache': [765, 345], 'orders-db': [330, 345] };
function renderTopology() {
  const data = ui.data, map = $('#topology-map'); map.replaceChildren();
  const defs = svgNode('defs'), marker = svgNode('marker', { id: 'edge-arrow', viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 4, markerHeight: 4, orient: 'auto-start-reverse' });
  marker.append(svgNode('path', { d: 'M 0 0 L 10 5 L 0 10 z', fill: '#647a93' })); defs.append(marker); map.append(defs);
  map.append(svgNode('text', { x: 16, y: 40, class: 'map-zone' }, 'INGRESS'), svgNode('text', { x: 16, y: 238, class: 'map-zone' }, 'APPLICATION'), svgNode('text', { x: 16, y: 348, class: 'map-zone' }, 'DATA LAYER'));
  for (const edge of data.topology.edges) {
    const a = positions[edge.source], b = positions[edge.target]; if (!a || !b) continue;
    const dependency = data.services.find(service => service.id === edge.target);
    const impacted = dependency && dependency.status !== 'healthy';
    let d;
    if (Math.abs(a[1] - b[1]) < 10) {
      const direction = a[0] < b[0] ? 1 : -1;
      d = 'M' + (a[0] + 87 * direction) + ',' + a[1] + ' C' + ((a[0] + b[0]) / 2) + ',' + (a[1] - 45) + ' ' + ((a[0] + b[0]) / 2) + ',' + (b[1] - 45) + ' ' + (b[0] - 87 * direction) + ',' + b[1];
    } else {
      const down = b[1] > a[1] ? 1 : -1, y1 = a[1] + 30 * down, y2 = b[1] - 30 * down;
      d = 'M' + a[0] + ',' + y1 + ' C' + a[0] + ',' + ((y1 + y2) / 2) + ' ' + b[0] + ',' + ((y1 + y2) / 2) + ' ' + b[0] + ',' + y2;
    }
    const path = svgNode('path', { d, class: 'topology-edge' + (impacted ? ' impacted' : ''), 'marker-end': 'url(#edge-arrow)' });
    path.append(svgNode('title', {}, edge.source + ' → ' + edge.target + ' 의존' + (impacted ? ' · 장애 영향' : ''))); map.append(path);
  }
  for (const service of data.services) {
    const point = positions[service.id]; if (!point) continue;
    const g = svgNode('g', { transform: 'translate(' + point.join(',') + ')', class: 'topology-node ' + service.status + (service.id === ui.selectedService ? ' selected' : ''), role: 'button', tabindex: 0, 'aria-label': service.name + ', ' + service.status + ', Latency ' + number(service.metrics.latencyMs) + 'ms', 'aria-pressed': String(service.id === ui.selectedService), 'data-focus': 'service-' + service.id });
    g.append(svgNode('rect', { x: -87, y: -30, width: 174, height: 60, rx: 7, class: 'node-shell' }), svgNode('circle', { cx: -72, cy: -12, r: 3, class: 'node-status' }), svgNode('text', { x: -62, y: -9, class: 'node-name' }, service.name || service.id), svgNode('text', { x: -72, y: 12, class: 'node-metric' }, number(service.metrics.latencyMs) + ' ms'), svgNode('text', { x: 72, y: 12, 'text-anchor': 'end', class: 'node-tier' }, number(service.metrics.errorRate, 1) + '% err'));
    if (service.rootFault) g.append(svgNode('text', { x: 0, y: -39, 'text-anchor': 'middle', class: 'node-root' }, '⚡ ROOT FAULT'));
    const select = () => { ui.selectedService = service.id; render(); };
    g.addEventListener('click', select); g.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(); } }); map.append(g);
  }
  $('#topology-caption').textContent = data.summary.activeIncidents ? data.summary.activeIncidents + ' active incidents · 화살표는 호출 의존 방향' : '모든 Service 정상 · 화살표는 호출 의존 방향';
}
function renderService() {
  const service = ui.data.services.find(s => s.id === ui.selectedService) || ui.data.services[0]; if (!service) return; ui.selectedService = service.id;
  const title = node('div', undefined, 'service-title'); title.append(node('strong', service.name), node('span', service.tier + ' · ' + service.status.toUpperCase()));
  const stat = (label, value) => { const div = node('div', label, 'service-stat'); div.append(node('strong', value)); return div; };
  const roots = (service.causes || []).map(id => ui.data.faults.find(f => f.id === id)?.serviceId).filter(Boolean);
  $('#service-detail').replaceChildren(title, stat('LATENCY', number(service.metrics.latencyMs) + ' ms'), stat('ERROR RATE', number(service.metrics.errorRate, 1) + '%'), stat('CPU', number(service.metrics.cpuPercent, 1) + '%'), stat('THROUGHPUT', number(service.metrics.rps) + ' /s'), node('span', service.rootFault ? 'ROOT · 이 Service에서 시작한 장애' : roots.length ? '영향 원인 · ' + [...new Set(roots)].join(', ') : '현재 감지된 장애 원인 없음', 'cause-label'));
  $('#signal-service').textContent = service.id;
  $('#chart-latency-value').textContent = number(service.metrics.latencyMs, 1);
  $('#chart-error-value').textContent = number(service.metrics.errorRate, 2);
  $('#chart-rps-value').textContent = number(service.metrics.rps);
  chart('#chart-latency', service.history, 'latencyMs'); chart('#chart-error', service.history, 'errorRate'); chart('#chart-rps', service.history, 'rps');
}
function renderScenarios() {
  const scenarios = ui.data.scenarios;
  if (!scenarios.some(s => s.id === ui.selectedScenario)) ui.selectedScenario = scenarios[0]?.id;
  const signature = JSON.stringify(scenarios) + ui.selectedScenario;
  if (signature === ui.scenarioSignature) return; ui.scenarioSignature = signature;
  $('#scenario-list').replaceChildren(...scenarios.map((scenario, index) => {
    const button = node('button', undefined, 'scenario-option' + (scenario.id === ui.selectedScenario ? ' selected' : ''));
    button.type = 'button'; button.setAttribute('aria-pressed', String(scenario.id === ui.selectedScenario)); button.dataset.focus = 'scenario-' + scenario.id;
    const text = node('div'); text.append(node('strong', scenario.title), node('small', scenario.rootService)); button.title = scenario.description;
    button.append(node('span', '0' + (index + 1), 'scenario-number'), text, node('span', undefined, 'scenario-radio'));
    button.addEventListener('click', () => { ui.selectedScenario = scenario.id; renderScenarios(); updateButtons(); $('[data-focus="scenario-' + scenario.id + '"]')?.focus({ preventScroll: true }); });
    return button;
  }));
}
function renderIncidents() {
  const data = ui.data, search = $('#search').value.toLowerCase(), status = $('#status-filter').value;
  const all = [...data.incidents].sort((a, b) => b.startedTick - a.startedTick);
  if (!all.some(i => i.id === ui.selectedIncident)) ui.selectedIncident = all[0]?.id || null;
  const filtered = all.filter(i => (!status || status === i.status) && (!search || (i.title + ' ' + i.service + ' ' + i.id).toLowerCase().includes(search)));
  $('#incident-count').textContent = filtered.length;
  const signature = JSON.stringify(filtered) + ui.selectedIncident;
  if (signature !== ui.incidentSignature) {
    ui.incidentSignature = signature;
    $('#incident-list').replaceChildren(...(filtered.length ? filtered.map(incident => {
      const button = node('button', undefined, 'incident-row' + (incident.id === ui.selectedIncident ? ' selected' : ''));
      button.type = 'button'; button.setAttribute('aria-pressed', String(incident.id === ui.selectedIncident)); button.dataset.focus = 'incident-' + incident.id;
      const top = node('div', undefined, 'row-top'), bottom = node('div', undefined, 'row-bottom');
      top.append(node('strong', incident.title), badge(incident.status)); bottom.append(node('span', incident.service), node('span', 'T' + incident.startedTick + ' · ' + incident.impactServices.length + ' services'));
      button.append(top, bottom); button.addEventListener('click', () => { ui.selectedIncident = incident.id; render(); }); return button;
    }) : [node('p', all.length ? '검색 조건에 맞는 Incident가 없습니다.' : '아직 Incident가 없습니다. Fault를 주입해 보세요.', 'empty')]));
  }
  const incident = all.find(i => i.id === ui.selectedIncident);
  if (!incident) { const empty = node('div', undefined, 'empty spacious'); empty.append(node('span', '↗'), node('h3', '복구는 변화로 증명합니다.'), node('p', 'Fault를 주입하고 Incident를 선택해 Runbook과 복구 효과를 확인하세요.')); $('#detail').replaceChildren(empty); return; }
  const root = node('div'), head = node('div', undefined, 'detail-heading'); head.append(node('p', 'INCIDENT / ' + incident.id.slice(0, 12), 'eyebrow'), badge(incident.status));
  const tags = node('div', undefined, 'impact-tags'); for (const service of incident.impactServices) tags.append(node('span', service));
  const stats = node('div', undefined, 'detail-stats');
  const addStat = (label, value) => { const n = node('div', label); n.append(node('strong', value)); stats.append(n); };
  addStat('PEAK LATENCY', number(incident.peakLatencyMs) + ' ms'); addStat('PEAK ERROR', number(incident.peakErrorRate, 1) + '%'); addStat(incident.status === 'resolved' ? 'RECOVERY TIME' : 'ELAPSED', Math.max(0, (incident.resolvedTick ?? data.clock.tick) - incident.startedTick) + ' ticks');
  const runbook = data.runbooks.find(r => r.scenarioId === incident.scenarioId), card = node('div', undefined, 'runbook-card' + (incident.status !== 'open' ? ' unavailable' : '')), info = node('div');
  if (runbook) {
    info.append(node('strong', runbook.title), node('p', incident.status === 'resolved' ? '복구 완료. Timeline과 Postmortem에서 결과를 확인하세요.' : incident.status === 'mitigating' ? 'Runbook 적용됨. Tick을 진행해 Metric의 회복을 확인하세요.' : runbook.description));
    const button = node('button', incident.status === 'open' ? 'Apply runbook ↗' : incident.status === 'mitigating' ? '조치 적용됨' : '복구 완료 ✓', 'button mint');
    button.type = 'button'; button.dataset.runbook = runbook.id; button.dataset.available = String(incident.status === 'open'); button.dataset.focus = 'runbook-' + incident.id;
    button.addEventListener('click', () => mutation('/api/sim/runbooks', { actionId: runbook.id, incidentId: incident.id }, 'Runbook을 적용했습니다. 다음 Tick의 실제 Metric 변화로 회복을 확인하세요.'));
    card.append(info, button);
  } else { info.append(node('strong', '사용 가능한 Runbook 없음'), node('p', '이 Scenario와 연결된 Runbook을 서버에서 제공하지 않았습니다.')); card.append(info); }
  const foot = node('div', undefined, 'detail-foot'), exportButton = node('button', 'Export postmortem ↓', 'text-button');
  exportButton.type = 'button'; exportButton.dataset.focus = 'export-' + incident.id; exportButton.disabled = ui.replay;
  exportButton.title = ui.replay ? 'Live 화면에서 현재 Incident의 Postmortem을 내보낼 수 있습니다.' : '서버가 생성한 Postmortem JSON 다운로드';
  exportButton.addEventListener('click', () => exportPostmortem(incident.id));
  foot.append(node('span', '조치는 원인에 적용되며 의존 Service에 전파됩니다.'), exportButton);
  root.append(head, node('h3', incident.title, 'detail-title'), node('p', incident.service + ' · START T' + incident.startedTick + ' · SYNTHETIC INCIDENT', 'detail-meta'), tags, stats, node('p', 'RECOMMENDED RUNBOOK', 'runbook-label'), card, foot); $('#detail').replaceChildren(root);
}
function renderAudit() {
  const events = [...ui.data.audit].sort((a, b) => b.tick - a.tick || String(b.at).localeCompare(String(a.at))).slice(0, 30);
  $('#event-count').textContent = ui.data.audit.length + ' events · 최근 최대 30건';
  $('#timeline').replaceChildren(...(events.length ? events.map(event => {
    const row = node('li'), stamp = node('time', 'TICK ' + event.tick); if (event.at) { stamp.dateTime = event.at; stamp.title = event.at; }
    row.append(stamp, node('span', String(event.kind).toUpperCase(), 'event-kind'), node('p', event.message)); return row;
  }) : [node('li', '아직 이벤트가 없습니다.', 'muted')]));
}
function renderRuns() {
  const runs = ui.data.runs || [], select = $('#run-select'), previous = select.value;
  const signature = JSON.stringify(runs);
  if (signature !== ui.runSignature) {
    ui.runSignature = signature;
    select.replaceChildren(...runs.map(run => { const option = node('option', (run.active ? 'LIVE' : 'ARCHIVE') + ' · Seed ' + run.seed + ' · T' + run.latestTick + ' · ' + run.id.slice(0, 10)); option.value = run.id; return option; }));
    if (runs.some(run => run.id === previous)) select.value = previous;
    else if (runs.some(run => run.id === ui.data.runId)) select.value = ui.data.runId;
  }
  setReplayRange();
}
function setReplayRange(reset = false) {
  const run = ui.data?.runs?.find(r => r.id === $('#run-select').value); if (!run) return;
  const range = $('#replay-tick'); range.min = run.earliestTick ?? 0; range.max = run.latestTick;
  if (reset || Number(range.value) > run.latestTick) range.value = run.latestTick;
  if (Number(range.value) < Number(range.min)) range.value = range.min;
  $('#replay-tick-label').textContent = 'TICK ' + range.value;
}
function render() {
  const focusKey = document.activeElement?.dataset?.focus;
  const data = ui.data, summary = data.summary, edge = data.services.find(s => s.id === 'edge-gateway');
  $('#tick-value').textContent = number(data.clock.tick);
  $('#sim-time').textContent = '1 tick = ' + (data.clock.secondsPerTick ?? 5) + 's simulated · SEED ' + data.clock.seed;
  $('#run-label').textContent = ui.replay ? 'REPLAY' : data.clock.running ? 'RUNNING' : 'PAUSED';
  $('#run-indicator').className = 'indicator' + (ui.replay ? ' replay' : data.clock.running ? '' : ' paused');
  $('#run').textContent = data.clock.running ? 'Ⅱ Pause simulation' : '▶ Run simulation';
  $('#replay-banner').hidden = !ui.replay;
  $('#health-count').textContent = summary.healthy; $('#health-caption').textContent = summary.critical ? summary.critical + ' critical' : summary.degraded ? summary.degraded + ' degraded' : 'ALL HEALTHY';
  $('#health-segments').replaceChildren(...data.services.map(service => { const n = node('span', undefined, service.status); n.title = service.id + ': ' + service.status; return n; }));
  $('#latency-value').textContent = number(summary.edgeLatencyMs); $('#error-value').textContent = number(summary.edgeErrorRate, 1);
  $('#active-value').textContent = summary.activeIncidents; $('#incident-caption').textContent = summary.activeIncidents ? 'NEEDS ATTENTION' : 'ALL CLEAR';
  $('#throughput-value').textContent = number(summary.throughputRps);
  chart('#latency-spark', edge?.history, 'latencyMs', true); chart('#error-spark', edge?.history, 'errorRate', true);
  renderScenarios(); renderTopology(); renderService(); renderIncidents(); renderAudit(); renderRuns(); updateButtons();
  if (focusKey) document.querySelector('[data-focus="' + CSS.escape(focusKey) + '"]')?.focus({ preventScroll: true });
}
async function loadReplay() {
  if (ui.busy) return; ui.busy = true; ui.request++; updateButtons();
  try { const data = await api('/api/sim/runs/' + encodeURIComponent($('#run-select').value) + '?tick=' + Number($('#replay-tick').value)); ui.replay = true; accept(data); announce('저장된 Snapshot입니다. Live Simulation의 진행 상태는 변경하지 않습니다.'); }
  catch (error) { announce(error.message, true); } finally { ui.busy = false; updateButtons(); }
}
async function backLive() { if (ui.busy) return; ui.replay = false; ui.selectedIncident = null; await refresh(true); }
async function exportPostmortem(id) {
  try {
    const response = await fetch('/api/sim/incidents/' + encodeURIComponent(id) + '/export', { cache: 'no-store' });
    if (!response.ok) { const data = await response.json(); throw new Error(data.error?.message || 'Export 실패'); }
    const blob = await response.blob(), url = URL.createObjectURL(blob), link = node('a'); link.href = url; link.download = 'incident-' + id + '-postmortem.json'; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); announce('서버에서 생성한 Postmortem JSON을 다운로드했습니다.');
  } catch (error) { announce(error.message, true); }
}
$('#run').addEventListener('click', () => mutation('/api/sim/control', { action: ui.data.clock.running ? 'pause' : 'run' }));
$('#step').addEventListener('click', () => mutation('/api/sim/control', { action: 'tick', steps: Number($('#tick-steps').value) }));
$('#inject').addEventListener('click', () => mutation('/api/sim/faults', { scenarioId: ui.selectedScenario, intensity: Number($('#intensity').value) }, 'Fault가 주입되었습니다. Tick을 진행해 의존 Service로 전파되는 영향을 관찰하세요.'));
$('#reset').addEventListener('click', () => { const seed = Number($('#seed').value); if (!Number.isSafeInteger(seed) || seed < 0 || seed > 2147483647) { announce('Seed는 0~2147483647의 정수로 입력하세요.', true); return; } ui.selectedIncident = null; mutation('/api/sim/reset', { seed }, '새 Run을 시작했습니다. 이전 기록은 Replay archive에 보존됩니다.'); });
$('#refresh').addEventListener('click', () => refresh(true));
$('#intensity').addEventListener('input', () => { const n = Number($('#intensity').value); $('#intensity-label').textContent = ['', 'Low', 'Moderate', 'High'][n] + ' · ' + n; });
$('#filters').addEventListener('submit', event => { event.preventDefault(); if (ui.data) renderIncidents(); updateButtons(); });
$('#search').addEventListener('input', () => { if (ui.data) renderIncidents(); updateButtons(); });
$('#status-filter').addEventListener('change', () => { if (ui.data) renderIncidents(); updateButtons(); });
$('#run-select').addEventListener('change', () => setReplayRange(true));
$('#replay-tick').addEventListener('input', () => { $('#replay-tick-label').textContent = 'TICK ' + $('#replay-tick').value; });
$('#load-replay').addEventListener('click', loadReplay); $('#back-live').addEventListener('click', backLive);
document.querySelectorAll('.nav-item').forEach(link => link.addEventListener('click', () => { document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active')); link.classList.add('active'); }));
async function init() {
  try { const data = await api('/public.data.json'), url = new URL(data.repositoryUrl); if (url.protocol !== 'https:' || url.username || url.password) throw new Error('Invalid repository URL'); const link = node('a', 'View source on GitHub ↗'); link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; $('#repository-link').replaceChildren(link); } catch { /* Source link is optional; Simulation health remains separately visible. */ }
  await refresh(); ui.poll = setInterval(() => { if (!document.hidden) refresh(); }, 1000);
}
document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
init();
