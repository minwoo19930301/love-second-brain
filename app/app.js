// ===================== Love Second Brain — frontend =====================
let currentTab = 'graph';
let allNodes = [];          // /api/nodes (full, with body)
let graphData = { nodes: [], links: [] };
let statsData = {};
let rawList = [];

const TYPE_COLORS = {
  claim: '#10b981', concept: '#0ea5e9', decision: '#f59e0b',
  source: '#94a3b8', person: '#ec4899', event: '#8b5cf6', stub: '#cbb5c2',
};
const TYPE_LABEL = {
  claim: 'claim', concept: 'concept', decision: 'decision',
  source: 'source', person: 'person', event: 'event', stub: 'stub',
};

// 핑크 테마 — 차트/그래프 공용 색 (라이트 배경 기준)
const TH = {
  text2:  '#99607e',                  // 축·범례 글자
  grid:   'rgba(236,72,153,.09)',     // 격자선
  border: '#ffffff',                  // 도넛 조각 테두리(흰 카드 위)
  accent: '#ec4899',
  accent2:'#f472b6',
  me:     '#ec4899',                  // me
  wife:   '#8b5cf6',                  // partner
  raw:    '#f9a8d4',
};

document.addEventListener('DOMContentLoaded', () => {
  lucide.createIcons();
  if (typeof marked !== 'undefined') marked.setOptions({ breaks: true });
  switchTab('graph');
  loadStats();
  loadHealth();

  const sendBtn = document.getElementById('chat-send-btn');
  const chatInput = document.getElementById('chatbot-input');
  sendBtn.addEventListener('click', () => sendChatMessage());
  // 한글 IME 조합 중 Enter는 무시 (isComposing/keyCode 229) → 중복 전송 방지
  chatInput.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' || e.shiftKey || e.isComposing || e.keyCode === 229) return;
    e.preventDefault();
    sendChatMessage();
  });
});

function switchTab(name) {
  currentTab = name;
  document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
  document.getElementById(`nav-${name}`)?.classList.add('active');
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.getElementById(`tab-${name}`).classList.add('active');
  const titles = { dashboard: '대시보드', graph: '지식 그래프', explorer: '노드 탐색기', raw: '원본 소스 (raw)', domains: '도메인 뷰', timeline: '최근 변경', chatbot: 'AI 질의응답' };
  document.getElementById('page-title').textContent = titles[name];

  if (name === 'graph') renderGraph();
  else if (name === 'explorer') loadNodes();
  else if (name === 'raw') loadRaw();
  else if (name === 'domains') loadDomains();
  else if (name === 'timeline') loadTimeline();
}

// ----------------------------- 1. DASHBOARD -----------------------------
let typeChart = null, domainChart = null;

// log.md action 종류별 라벨·색
const ACTION_META = {
  ingest:  { label: '수집',  color: '#22d3ee' },
  distill: { label: '정제',  color: '#a78bfa' },
  update:  { label: '갱신',  color: '#fbbf24' },
  fix:     { label: '수정',  color: '#34d399' },
  lint:    { label: '린트',  color: '#94a3b8' },
  move:    { label: '이동',  color: '#fb923c' },
  merge:   { label: '병합',  color: '#f472b6' },
};
const actionColor = a => (ACTION_META[a] || {}).color || TH.accent;
const actionLabel = a => (ACTION_META[a] || {}).label || a;

async function loadStats() {
  try {
    const r = await fetch('/api/stats');
    statsData = await r.json();
  } catch (e) { console.error(e); return; }

  const wiki = statsData.wiki_count || 0, edges = statsData.edge_count || 0;
  const nDomains = Object.keys(statsData.by_domain || {}).length;
  document.getElementById('stat-raw').textContent = statsData.raw_count;
  document.getElementById('stat-wiki').textContent = wiki;
  document.getElementById('stat-edges').textContent = edges;
  document.getElementById('stat-domains').textContent = nDomains;
  document.getElementById('stat-degree').textContent = wiki ? (edges / wiki).toFixed(1) : '0';
  document.getElementById('brain-badge').textContent =
    `${statsData.wiki_count} nodes · ${statsData.raw_count} raw docs`;

  renderTypeChart();
  renderDomainChart();
  renderTagCloud();
  renderLog();
  loadChatStats();
}

// ---- 카톡 통계 (대시보드 상단) ----
let chatStats = null;
let senderChart = null, msgMonthlyChart = null, msgYearChart = null, hourChart = null, weekdayChart = null;
const fmt = n => (n == null ? '0' : Number(n).toLocaleString('ko-KR'));

async function loadChatStats() {
  if (!chatStats) {
    try { chatStats = await (await fetch('/api/chat_stats')).json(); }
    catch (e) { console.error(e); return; }
  }
  renderChatCards();
  renderSenderChart();
  renderMsgMonthlyChart();
  renderMsgYearChart();
  renderHourChart();
  renderWeekdayChart();
}

function renderChatCards() {
  const s = chatStats || {};
  const box = document.getElementById('chat-cards');
  if (!box) return;
  const total = s.total || 0;
  const me = (s.by_sender || {})['나'] || 0;
  const wife = (s.by_sender || {})['아내'] || 0;
  const pct = n => total ? Math.round(n / total * 100) : 0;
  const years = s.first_date && s.last_date
    ? `${s.first_date.slice(0, 4)}.${s.first_date.slice(5, 7)} ~ ${s.last_date.slice(0, 4)}.${s.last_date.slice(5, 7)}` : '—';
  const bm = s.busiest_month || {};
  const cards = [
    { cls: 'card accent', emoji: '💬', title: '총 메시지', value: fmt(total), sub: `${fmt(s.days_span)}일간 · 대화한 날 ${fmt(s.active_days)}일` },
    { cls: 'card', emoji: '🧑', title: '내가 보낸', value: fmt(me), sub: `전체의 ${pct(me)}%`, color: 'var(--me)' },
    { cls: 'card', emoji: '👩', title: '상대가 보낸', value: fmt(wife), sub: `전체의 ${pct(wife)}%`, color: 'var(--wife)' },
    { cls: 'card', emoji: '📅', title: '대화 기간', value: years, sub: `하루 평균 ${fmt(s.avg_per_day)}개` },
    { cls: 'card', emoji: '🔥', title: '가장 뜨거웠던 달', value: bm.month || '—', sub: bm.total ? `${fmt(bm.total)}개 메시지` : '' },
  ];
  box.innerHTML = cards.map(c => `
    <div class="${c.cls}">
      <span class="card-emoji">${c.emoji}</span>
      <div class="card-title">${c.title}</div>
      <div class="card-value"${c.color ? ` style="color:${c.color}"` : ''}>${c.value}</div>
      <div class="card-subtext">${c.sub}</div>
    </div>`).join('');
}

function renderSenderChart() {
  const s = chatStats || {};
  const me = (s.by_sender || {})['나'] || 0, wife = (s.by_sender || {})['아내'] || 0;
  const ctx = document.getElementById('sender-chart').getContext('2d');
  if (senderChart) senderChart.destroy();
  senderChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: [`나 ${fmt(me)}`, `상대 ${fmt(wife)}`],
      datasets: [{ data: [me, wife], backgroundColor: [TH.me, TH.wife], borderColor: TH.border, borderWidth: 3 }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: '62%',
      plugins: { legend: { position: 'bottom', labels: { color: TH.text2, font: { family: 'Inter', size: 13 }, padding: 16 } } },
    },
  });
}

function renderMsgMonthlyChart() {
  const months = (chatStats || {}).by_month || [];
  const ctx = document.getElementById('msg-monthly-chart').getContext('2d');
  if (msgMonthlyChart) msgMonthlyChart.destroy();
  msgMonthlyChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: months.map(m => m.month),
      datasets: [
        { label: '나', data: months.map(m => m['나']), backgroundColor: TH.me },
        { label: '상대', data: months.map(m => m['아내']), backgroundColor: TH.wife },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { labels: { color: TH.text2 } } },
      scales: {
        x: { stacked: true, ticks: { color: TH.text2, maxRotation: 90, autoSkip: true, maxTicksLimit: 24 }, grid: { display: false } },
        y: { stacked: true, ticks: { color: TH.text2, precision: 0 }, grid: { color: TH.grid } },
      },
    },
  });
}

function renderMsgYearChart() {
  const years = (chatStats || {}).by_year || [];
  const ctx = document.getElementById('msg-year-chart').getContext('2d');
  if (msgYearChart) msgYearChart.destroy();
  msgYearChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: years.map(y => y.year),
      datasets: [
        { label: '나', data: years.map(y => y['나']), backgroundColor: TH.me },
        { label: '상대', data: years.map(y => y['아내']), backgroundColor: TH.wife },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: TH.text2 } } },
      scales: {
        x: { stacked: true, ticks: { color: TH.text2 }, grid: { display: false } },
        y: { stacked: true, ticks: { color: TH.text2, precision: 0 }, grid: { color: TH.grid } },
      },
    },
  });
}

function renderHourChart() {
  const h = (chatStats || {}).by_hour || { '나': [], '아내': [] };
  const labels = Array.from({ length: 24 }, (_, i) => `${i}`);
  const ctx = document.getElementById('hour-chart').getContext('2d');
  if (hourChart) hourChart.destroy();
  hourChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: '나', data: h['나'] || [], backgroundColor: TH.me },
        { label: '상대', data: h['아내'] || [], backgroundColor: TH.wife },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: TH.text2 } } },
      scales: {
        x: { stacked: true, ticks: { color: TH.text2 }, grid: { display: false } },
        y: { stacked: true, ticks: { color: TH.text2, precision: 0 }, grid: { color: TH.grid } },
      },
    },
  });
}

function renderWeekdayChart() {
  const wd = (chatStats || {}).by_weekday || [];
  const labels = ['월', '화', '수', '목', '금', '토', '일'];
  const ctx = document.getElementById('weekday-chart').getContext('2d');
  if (weekdayChart) weekdayChart.destroy();
  weekdayChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: '메시지', data: wd, borderRadius: 6,
        backgroundColor: labels.map((_, i) => i >= 5 ? TH.wife : TH.accent),
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: TH.text2 }, grid: { display: false } },
        y: { ticks: { color: TH.text2, precision: 0 }, grid: { color: TH.grid } },
      },
    },
  });
}

function renderTypeChart() {
  const entries = Object.entries(statsData.by_type || {});
  const ctx = document.getElementById('type-chart').getContext('2d');
  if (typeChart) typeChart.destroy();
  typeChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: entries.map(e => TYPE_LABEL[e[0]] || e[0]),
      datasets: [{
        data: entries.map(e => e[1]),
        backgroundColor: entries.map(e => TYPE_COLORS[e[0]] || TH.accent),
        borderColor: TH.border, borderWidth: 2,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'right', labels: { color: TH.text2, font: { family: 'Inter' } } } },
    },
  });
}

function renderDomainChart() {
  const wiki = statsData.by_domain || {};
  const raw = statsData.raw_by_domain || {};
  const domains = Array.from(new Set([...Object.keys(wiki), ...Object.keys(raw)])).sort();
  const ctx = document.getElementById('domain-chart').getContext('2d');
  if (domainChart) domainChart.destroy();
  domainChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: domains,
      datasets: [
        { label: 'raw',  data: domains.map(d => raw[d] || 0),  backgroundColor: TH.raw },
        { label: 'wiki', data: domains.map(d => wiki[d] || 0), backgroundColor: TH.accent },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: TH.text2 } } },
      scales: {
        x: { stacked: true, ticks: { color: TH.text2 }, grid: { color: TH.grid } },
        y: { stacked: true, ticks: { color: TH.text2, precision: 0 }, grid: { color: TH.grid } },
      },
    },
  });
}

function renderTagCloud() {
  const box = document.getElementById('tag-cloud');
  box.innerHTML = '';
  const tags = statsData.tags || [];
  if (!tags.length) { box.innerHTML = '<p class="muted">태그 없음</p>'; return; }
  const max = Math.max(...tags.map(t => t[1]));
  const min = Math.min(...tags.map(t => t[1]));
  tags.forEach(([tag, count]) => {
    const chip = document.createElement('span');
    chip.className = 'tag-chip';
    chip.textContent = `${tag} · ${count}`;
    const size = 12 + (max > min ? (count - min) / (max - min) : 0) * 8;
    chip.style.fontSize = `${size}px`;
    chip.style.cursor = 'pointer';
    chip.title = `'${tag}' 노드 보기`;
    chip.onclick = () => { switchTab('explorer'); setTimeout(() => {
      document.getElementById('explorer-search').value = tag; filterNodes();
    }, 50); };
    box.appendChild(chip);
  });
}

function renderLog() {
  const box = document.getElementById('log-timeline');
  box.innerHTML = '';
  const log = statsData.log || [];
  if (!log.length) { box.innerHTML = '<p class="muted">기록 없음</p>'; return; }
  log.forEach(e => {
    const row = document.createElement('div');
    row.className = 'log-row';
    row.innerHTML = `<span class="log-date">${e.date}</span>
      <span class="log-action">${e.action}</span>
      <span class="log-title">${escapeHtml(e.title)}</span>`;
    box.appendChild(row);
  });
}

// ----------------------------- 최근 변경 (타임라인) -----------------------------
let timelineActions = new Set();   // 비어있으면 = 전체

async function loadTimeline() {
  if (!statsData.log) { try { statsData = await (await fetch('/api/stats')).json(); } catch {} }
  buildTimelineFilter();
  renderTimeline();
}
function buildTimelineFilter() {
  const bar = document.getElementById('timeline-filter');
  if (!bar || bar.dataset.built) return;
  const counts = {};
  (statsData.log || []).forEach(e => { counts[e.action] = (counts[e.action] || 0) + 1; });
  bar.innerHTML = '';
  const mk = (label, act, color) => {
    const c = document.createElement('span');
    c.className = 'filter-chip' + (act === null ? ' active' : '');
    if (color) c.innerHTML = `<span class="dot" style="background:${color}"></span>`;
    c.append(label);
    if (act !== null) c.dataset.act = act;
    c.onclick = () => {
      if (act === null) timelineActions.clear();
      else if (timelineActions.has(act)) timelineActions.delete(act);
      else timelineActions.add(act);
      document.querySelectorAll('#timeline-filter .filter-chip').forEach((x, i) => {
        if (i === 0) x.classList.toggle('active', timelineActions.size === 0);
        else x.classList.toggle('active', timelineActions.has(x.dataset.act));
      });
      renderTimeline();
    };
    return c;
  };
  bar.appendChild(mk('전체', null));
  Object.keys(counts).sort((a, b) => counts[b] - counts[a]).forEach(a =>
    bar.appendChild(mk(`${actionLabel(a)} ${counts[a]}`, a, actionColor(a))));
  bar.dataset.built = '1';
}
function renderTimeline() {
  const box = document.getElementById('timeline-list');
  const log = (statsData.log || []).filter(e => timelineActions.size === 0 || timelineActions.has(e.action));
  document.getElementById('timeline-meta').textContent = `${log.length}건`;
  if (!log.length) { box.innerHTML = '<p class="muted center" style="padding:30px;">해당 활동이 없습니다.</p>'; return; }
  // 날짜별 그룹 (이미 최신순 정렬)
  const days = [];
  let cur = null;
  log.forEach(e => {
    if (!cur || cur.date !== e.date) { cur = { date: e.date, items: [] }; days.push(cur); }
    cur.items.push(e);
  });
  box.innerHTML = days.map(d => `
    <div class="tl-day">
      <div class="tl-date">${d.date}<span class="tl-count">${d.items.length}건</span></div>
      <div class="tl-items">${d.items.map(e => `
        <div class="tl-item">
          <span class="tl-dot" style="background:${actionColor(e.action)}"></span>
          <span class="tl-badge" style="background:${actionColor(e.action)}">${actionLabel(e.action)}</span>${escapeHtml(e.title)}
        </div>`).join('')}</div>
    </div>`).join('');
}

// ----------------------------- 2. KNOWLEDGE GRAPH -----------------------------
let selectedSlug = null;
let activeGraphGroups = new Set();   // 비어있으면 = 전체
let _gDraw = null;
let _ambRaf = null;                  // 상시 ambient(부유) 애니메이션 프레임 핸들
let _graphPrelaid = false;           // 첫 진입 시 1회만 레이아웃 사전 수렴(이후 재진입은 기존 좌표 재사용)
let _graphIntroPlayed = false;       // 빅뱅 인트로는 최초 1회만 재생

// 모든 탭의 공통 필터 = 최상위 도메인 (비어있어도 칩으로 노출)
const CANON_DOMAINS = ['person', 'love', 'taste', 'events', 'marriage', 'rules', 'lexicon', 'life'];
const CANON_LABEL = { person: '인물', love: '애정', taste: '취향', events: '추억', marriage: '결혼', rules: '규칙', lexicon: '은어', life: '일상' };

function nodeGroup(n) {
  // 항상 최상위 도메인으로 그룹핑 (person / love / taste / …)
  const p = (n.path || '').split('/');
  if (p.length >= 2) return p[1];                // wiki/love/... → love
  return n.domain || 'stub';
}
function gVisible(n) {
  return activeGraphGroups.size === 0 || activeGraphGroups.has(nodeGroup(n));
}
function buildGraphFilter() {
  const bar = document.getElementById('graph-filter-bar');
  if (!bar || bar.dataset.built) return;
  // 노드가 실제 존재하는 도메인 집계 (칩에 개수 표시)
  const counts = {};
  graphData.nodes.forEach(n => { const g = nodeGroup(n); counts[g] = (counts[g] || 0) + 1; });
  bar.innerHTML = '';
  const mk = (label, grp) => {
    const c = document.createElement('span');
    c.className = 'filter-chip' + (grp === null ? ' active' : '');
    c.textContent = label;
    if (grp !== null) c.dataset.grp = grp;
    c.onclick = () => {
      if (grp === null) activeGraphGroups.clear();
      else if (activeGraphGroups.has(grp)) activeGraphGroups.delete(grp);
      else activeGraphGroups.add(grp);
      refreshGraphChips();
      if (_gDraw) _gDraw();
    };
    return c;
  };
  bar.appendChild(mk('All', null));
  // 정규 도메인은 비어있어도 모두 노출, 그 외 도메인(있으면)은 뒤에
  const extra = Object.keys(counts).filter(g => !CANON_DOMAINS.includes(g)).sort();
  [...CANON_DOMAINS, ...extra].forEach(g => {
    const n = counts[g] || 0;
    const chip = mk(`${CANON_LABEL[g] || g} ${n}`, g);
    if (n === 0) chip.classList.add('empty');
    bar.appendChild(chip);
  });
  bar.dataset.built = '1';
}
function refreshGraphChips() {
  document.querySelectorAll('#graph-filter-bar .filter-chip').forEach((c, i) => {
    if (i === 0) c.classList.toggle('active', activeGraphGroups.size === 0);
    else c.classList.toggle('active', activeGraphGroups.has(c.dataset.grp));
  });
}

async function renderGraph() {
  const container = document.getElementById('graph-container');
  const canvas = document.getElementById('graph-canvas');
  const ctx = canvas.getContext('2d');
  const width = container.clientWidth, height = container.clientHeight;

  if (!graphData.nodes.length) {
    try { graphData = await (await fetch('/api/graph')).json(); }
    catch { ctx.fillStyle = '#ef4444'; ctx.fillText('그래프 로드 실패', 20, 20); return; }
  }
  if (!allNodes.length) { try { allNodes = await (await fetch('/api/nodes')).json(); } catch {} }
  renderLegend();

  const dpr = window.devicePixelRatio || 1;
  canvas.width = width * dpr; canvas.height = height * dpr;
  canvas.style.width = width + 'px'; canvas.style.height = height + 'px';
  ctx.scale(dpr, dpr);

  let transform = d3.zoomIdentity;
  // 둥근 "뇌" 모양: 약한 반발 + 짧고 강한 링크 + 중심으로 끌어당기는 중력(forceX/Y).
  // distanceMax로 멀리 떨어진 노드끼리는 서로 밀지 않게 해 전체가 흩어지는 걸 방지.
  const sim = d3.forceSimulation(graphData.nodes)
    .force('link', d3.forceLink(graphData.links).id(d => d.slug).distance(70).strength(.35))
    .force('charge', d3.forceManyBody().strength(-160).distanceMax(330))
    .force('x', d3.forceX(width / 2).strength(.028))
    .force('y', d3.forceY(height / 2).strength(.028))
    .force('collision', d3.forceCollide().radius(21))
    .alphaDecay(.035);
  sim.on('tick', draw);
  sim.stop();                 // 자동 실행 중지 — 그리기 전에 수동으로 미리 수렴시킨다(확대 churn 방지)
  _gDraw = draw;
  buildGraphFilter();

  const zoom = d3.zoom().scaleExtent([.05, 6]).on('zoom', e => { transform = e.transform; draw(); });
  d3.select(canvas).call(zoom);

  // 전체 노드 구름을 화면에 맞추는 transform 계산(그리지 않음). 카메라 고정용.
  function computeFitTransform() {
    const vis = graphData.nodes.filter(n => gVisible(n) && n.x != null);
    if (!vis.length) return null;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    vis.forEach(n => { minX = Math.min(minX, n.x); maxX = Math.max(maxX, n.x); minY = Math.min(minY, n.y); maxY = Math.max(maxY, n.y); });
    const pad = 50, bw = (maxX - minX) || 1, bh = (maxY - minY) || 1;
    const k = Math.min(2, Math.max(.05, Math.min((width - pad * 2) / bw, (height - pad * 2) / bh)));
    return d3.zoomIdentity.translate(width / 2 - k * (minX + maxX) / 2, height / 2 - k * (minY + maxY) / 2).scale(k);
  }

  // ── 상시 ambient(부유): 브레인이 살아있는 듯 잔잔하게 떠다님. 레이아웃(sim)은 안 건드리고 draw에서만.
  const AMB = 6;
  function ambient(n) {
    const t = (typeof performance !== 'undefined' ? performance.now() : Date.now()) / 1000, ph = (n.index || 0);
    return { x: Math.sin(t * .5 + ph * .7) * AMB, y: Math.cos(t * .42 + ph * 1.3) * AMB };
  }

  // ── 호버 dimple: 커서 주변만 살짝 갈라짐(돋보기X·잔잔하게). 중심(커서 바로 아래)은 밀림 0 → 클릭 대상 제자리.
  let mouseG = null, hoverNode = null;     // 커서 그래프좌표 / 호버 중인 노드(라벨 표시용)
  let hoverK = 0, hoverTarget = 0;         // 0~1 세기(ease in/out)
  const HOVER_R = 72, HOVER_PUSH = 13;
  function disp(n) {
    if (!mouseG || hoverK < .001 || n.x == null) return n;
    const dx = n.x - mouseG.x, dy = n.y - mouseG.y, d = Math.hypot(dx, dy);
    if (d >= HOVER_R || d < 1e-3) return n;
    const amt = Math.sin(Math.PI * (d / HOVER_R)) * HOVER_PUSH * hoverK;
    return { x: n.x + (dx / d) * amt, y: n.y + (dy / d) * amt };
  }
  // 최종 그리기 좌표 = base + 호버변위 + ambient 부유. (인트로 spread는 sim이 직접 n.x/y를 움직임)
  function pos(n) {
    const dp = disp(n), a = ambient(n);
    return { x: dp.x + a.x, y: dp.y + a.y };
  }
  // 상시 프레임 루프: 호버 보간 + 매 프레임 재draw → 항상 살아 움직임. 그래프 탭 떠나면 정지.
  function frame() {
    if (currentTab !== 'graph') { _ambRaf = null; return; }
    hoverK += (hoverTarget - hoverK) * .18;
    if (hoverK < .002 && hoverTarget === 0) { hoverK = 0; mouseG = null; }
    draw();
    _ambRaf = requestAnimationFrame(frame);
  }

  function draw() {
    ctx.save();
    ctx.clearRect(0, 0, width, height);
    ctx.translate(transform.x, transform.y);
    ctx.scale(transform.k, transform.k);

    // edges
    ctx.lineWidth = .8 / transform.k;
    graphData.links.forEach(l => {
      if (!l.source.x) return;
      if (!gVisible(l.source) || !gVisible(l.target)) return;
      ctx.strokeStyle = l.type === 'contradicts' ? 'rgba(244,63,94,.45)' : 'rgba(236,72,153,.22)';
      const s = pos(l.source), t = pos(l.target);
      ctx.beginPath(); ctx.moveTo(s.x, s.y); ctx.lineTo(t.x, t.y); ctx.stroke();
    });

    // nodes
    graphData.nodes.forEach(n => {
      if (!gVisible(n)) return;
      const r = n.type === 'stub' ? 6 : 9, p = pos(n);
      ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, 2 * Math.PI);
      ctx.fillStyle = TYPE_COLORS[n.type] || TH.accent;
      if (n.type === 'stub') { ctx.globalAlpha = .55; }
      ctx.fill(); ctx.globalAlpha = 1;
      if (selectedSlug === n.slug || hoverNode === n) {
        ctx.strokeStyle = '#fff'; ctx.lineWidth = 2.5 / transform.k; ctx.stroke();
      }
    });

    // labels — 전부 띄우지 않고, 호버 중인 노드(+선택 노드)만 읽기 쉽게 표시
    const labelNodes = [];
    if (hoverNode && gVisible(hoverNode)) labelNodes.push(hoverNode);
    if (selectedSlug && selectedSlug !== (hoverNode && hoverNode.slug)) {
      const sn = graphData.nodes.find(n => n.slug === selectedSlug);
      if (sn && gVisible(sn)) labelNodes.push(sn);
    }
    labelNodes.forEach(n => {
      const r = n.type === 'stub' ? 6 : 9, p = pos(n), k = transform.k;
      const fs = 13 / k, padX = 7 / k, h = fs + 8 / k;
      ctx.font = `600 ${fs}px Inter, sans-serif`;
      ctx.textBaseline = 'middle';
      const tw = ctx.measureText(n.slug).width;
      const lx = p.x + r + 6 / k, ly = p.y;
      ctx.fillStyle = 'rgba(11,16,32,.86)';
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(lx - padX, ly - h / 2, tw + padX * 2, h, 5 / k);
      else ctx.rect(lx - padX, ly - h / 2, tw + padX * 2, h);
      ctx.fill();
      ctx.fillStyle = '#fff';
      ctx.fillText(n.slug, lx, ly);
    });
    ctx.restore();
  }

  function pick(mx, my) {
    const x = (mx - transform.x) / transform.k, y = (my - transform.y) / transform.k;
    let best = null, md = 22 / transform.k;
    graphData.nodes.forEach(n => { if (!gVisible(n)) return; const p = pos(n); const d = Math.hypot(p.x - x, p.y - y); if (d < md) { best = n; md = d; } });
    return best;
  }

  let _dragging = false;
  d3.select(canvas).on('mousemove', (e) => {
    if (_dragging) return;
    const [mx, my] = d3.pointer(e);
    mouseG = { x: (mx - transform.x) / transform.k, y: (my - transform.y) / transform.k };
    hoverNode = pick(mx, my);                 // 호버 노드 → 라벨 표시
    canvas.style.cursor = hoverNode ? 'pointer' : 'default';
    hoverTarget = 1;
  });
  d3.select(canvas).on('mouseleave', () => { hoverTarget = 0; hoverNode = null; });

  d3.select(canvas).on('click', (e) => {
    const [mx, my] = d3.pointer(e);
    const n = pick(mx, my);
    if (n) { selectedSlug = n.slug; showNodeDetail(n.slug); }
  });

  d3.select(canvas).call(d3.drag().container(canvas)
    .subject((e) => pick(e.x, e.y))
    .on('start', (e) => { _dragging = true; mouseG = null; hoverNode = null; hoverK = 0; hoverTarget = 0; if (!e.active) sim.alphaTarget(.3).restart(); e.subject.fx = e.subject.x; e.subject.fy = e.subject.y; })
    .on('drag', (e) => { e.subject.fx = (e.x - transform.x) / transform.k; e.subject.fy = (e.y - transform.y) / transform.k; })
    .on('end', (e) => { _dragging = false; if (!e.active) sim.alphaTarget(0); e.subject.fx = null; e.subject.fy = null; }));

  // ── 진입 인트로(최초 1회): 노드를 중앙 클러스터로 모았다가 시뮬레이션을 "보이게" 빠르게 재생
  //   → 전 노드가 한꺼번에 바깥으로 쭉 퍼지며 ~2~3초에 자리잡음(방향성 없는 균일 확산). 카메라는 사전측정 fit 고정.
  //   (재진입 시엔 인트로 없이 바로 fit)
  if (!_graphPrelaid) {
    sim.alpha(1);
    for (let i = 0; i < 220; i++) sim.tick();   // 측정용 비가시 수렴
    sim.stop();
    _graphPrelaid = true;
  }
  const fitT = computeFitTransform();           // settle된 레이아웃 기준 최종 fit(카메라 고정용)

  if (!_graphIntroPlayed) {
    _graphIntroPlayed = true;
    const cgx = fitT ? (width / 2 - fitT.x) / fitT.k : width / 2;
    const cgy = fitT ? (height / 2 - fitT.y) / fitT.k : height / 2;
    graphData.nodes.forEach(n => {              // 중앙 작은 원반에 모음(균일 random)
      const a = Math.random() * 2 * Math.PI, rr = Math.sqrt(Math.random()) * 110;
      n.x = cgx + Math.cos(a) * rr; n.y = cgy + Math.sin(a) * rr; n.vx = 0; n.vy = 0;
    });
    if (fitT) d3.select(canvas).call(zoom.transform, fitT);   // 흩뿌린 상태가 fit 화면에 보이도록 카메라 고정
    sim.alphaDecay(0.05).alpha(1).restart();    // 빠르게(~2~3초) 바깥으로 퍼지며 settle
  } else if (fitT) {
    d3.select(canvas).call(zoom.transform, fitT);
  }

  // 상시 ambient 루프 시작 (재진입 시 이전 루프 정리)
  if (_ambRaf) cancelAnimationFrame(_ambRaf);
  _ambRaf = requestAnimationFrame(frame);
}

function renderLegend() {
  const used = Array.from(new Set(graphData.nodes.map(n => n.type)));
  document.getElementById('graph-legend').innerHTML = used.map(t =>
    `<span><span class="legend-dot" style="background:${TYPE_COLORS[t] || TH.accent}"></span>${TYPE_LABEL[t] || t}</span>`
  ).join('');
}

function showNodeDetail(slug) {
  const panel = document.getElementById('graph-node-details');
  const n = allNodes.find(x => x.slug === slug);
  if (!n) {
    panel.innerHTML = `<span class="type-tag type-stub">stub</span>
      <p style="margin-top:12px;" class="muted">'${escapeHtml(slug)}' — 참조만 존재하고 아직 노드가 작성되지 않았습니다.</p>`;
    return;
  }
  panel.innerHTML = nodeDetailHTML(n);
  bindWikiLinks(panel);
  lucide.createIcons();
}

// ----------------------------- 3. NODE EXPLORER -----------------------------
async function loadNodes() {
  const box = document.getElementById('node-cards');
  if (!allNodes.length) {
    box.innerHTML = '<p class="muted center" style="grid-column:1/-1;">로딩 중…</p>';
    try { allNodes = await (await fetch('/api/nodes')).json(); }
    catch { box.innerHTML = '<p class="center" style="color:#ef4444;grid-column:1/-1;">로딩 실패</p>'; return; }
  }
  renderNodeCards(allNodes);
}

function renderNodeCards(nodes) {
  const box = document.getElementById('node-cards');
  box.innerHTML = '';
  if (!nodes.length) { box.innerHTML = '<p class="muted center" style="grid-column:1/-1;padding:40px;">검색 결과 없음</p>'; return; }
  nodes.forEach(n => {
    const card = document.createElement('div');
    card.className = 'node-card';
    card.onclick = () => openNodeDetail(n.slug);
    card.innerHTML = `
      <span class="type-tag type-${n.type}">${TYPE_LABEL[n.type] || n.type}</span>
      <h4>${escapeHtml(n.slug)}</h4>
      <div class="tldr">${escapeHtml(n.tldr || '(tldr 없음)')}</div>
      <div class="node-tags">${(n.tags || []).map(t => `<span class="node-tag">${escapeHtml(t)}</span>`).join('')}</div>
      <div class="node-meta">${escapeHtml(n.path)} · updated ${n.updated || '—'}</div>`;
    box.appendChild(card);
  });
}

function filterNodes() {
  const q = document.getElementById('explorer-search').value.toLowerCase();
  const type = document.getElementById('explorer-type-filter').value;
  const filtered = allNodes.filter(n => {
    const matchQ = !q || n.slug.toLowerCase().includes(q) || (n.tldr || '').toLowerCase().includes(q)
      || (n.body || '').toLowerCase().includes(q) || (n.tags || []).some(t => t.toLowerCase().includes(q));
    return matchQ && (!type || n.type === type);
  });
  renderNodeCards(filtered);
}

function openNodeDetail(slug) {
  const n = allNodes.find(x => x.slug === slug);
  if (!n) return;
  const box = document.getElementById('node-cards');
  const wrap = document.createElement('div');
  wrap.style.gridColumn = '1/-1';
  wrap.innerHTML = `
    <button class="chat-btn" style="padding:8px 16px;margin-bottom:18px;font-size:.82rem;" onclick="renderNodeCards(allNodes);filterNodes()">← 목록</button>
    <div class="viz-card">${nodeDetailHTML(n, true)}</div>`;
  box.innerHTML = '';
  box.appendChild(wrap);
  bindWikiLinks(wrap);
  lucide.createIcons();
}

// shared node detail renderer (graph panel + explorer)
function nodeDetailHTML(n, big = false) {
  const sources = (n.sources || []).map(s => {
    const url = s.url || '';
    const label = `[${s.platform || 'src'}] ${s.date || ''}`;
    if (/^https?:/.test(url)) return `<a class="src-item" href="${url}" target="_blank" rel="noopener">${label} — ${escapeHtml(url)}</a>`;
    if (url.includes('raw/')) {
      const p = url.replace(/^(\.\.\/)+/, '');
      return `<span class="src-item link-item" data-raw="${escapeHtml(p)}">${label} — ${escapeHtml(p)} ↗</span>`;
    }
    return `<span class="src-item">${label} — ${escapeHtml(url)}</span>`;
  }).join('') || '<p class="muted" style="font-size:.8rem;">출처 없음</p>';

  const links = (n.links || []).map(l => `<span class="link-item" data-slug="${escapeHtml(l[0])}">${escapeHtml(l[0])} <span class="muted">(${l[1]})</span></span>`).join('')
    || '<p class="muted" style="font-size:.8rem;">연결된 노드 없음</p>';

  return `
    <span class="type-tag type-${n.type}">${TYPE_LABEL[n.type] || n.type}</span>
    <h4 style="font-size:${big ? '1.3rem' : '1.1rem'};font-weight:800;margin:12px 0 6px;color:#fff;">${escapeHtml(n.slug)}</h4>
    <p style="color:var(--text-2);font-size:.88rem;margin-bottom:8px;">${escapeHtml(n.tldr || '')}</p>
    <div class="node-tags" style="margin-bottom:16px;">${(n.tags || []).map(t => `<span class="node-tag">${escapeHtml(t)}</span>`).join('')}</div>
    <div class="node-detail-section">
      <h5>본문</h5>
      <div class="node-body">${renderMarkdown(n.body || '')}</div>
    </div>
    <div class="node-detail-section">
      <h5>출처 (sources)</h5>${sources}
    </div>
    <div class="node-detail-section">
      <h5>연결 (links)</h5>${links}
    </div>
    <p class="muted" style="font-size:.74rem;font-family:ui-monospace,monospace;">${escapeHtml(n.path)}</p>`;
}

// ----------------------------- 4. RAW SOURCES (전체 연속 채팅 + 캘린더 점프) -----------------------------
let grepTokens = [];
let rawBuilt = false;
let calDays = {}, calMonths = [];        // /api/chat_calendar
let calState = { y: 0, m: 0 };           // 캘린더에 표시 중인 연/월
const monthText = {};                    // ym → 원문(text) 캐시
const loadedMonths = new Set();          // 현재 DOM에 버블이 그려진 월
let monthObserver = null;
const MAX_LOADED = 6;                    // 동시에 그려두는 월 수 상한(가상화)
const EST_ROW = 30, EST_DIV = 44;        // 높이 추정용(px)

const CHAT_PATH_RE = /raw\/chat\/(\d{4})\/(\d{4})-(\d{2})\.md$/;
const CHAT_MSG_RE = /^(\d{1,2}:\d{2})\s+(나|아내):\s?(.*)$/;
const CHAT_DATE_RE = /^##\s+(\d{4})-(\d{2})-(\d{2})\s*(?:\(([^)]*)\))?/;
const DOW_KO = ['일', '월', '화', '수', '목', '금', '토'];
const ymOf = d => d.slice(0, 7);
const monthPath = ym => `raw/chat/${ym.slice(0, 4)}/${ym}.md`;

async function loadRaw() {
  bindGrep();
  if (rawBuilt) return;
  let cal;
  try { cal = await (await fetch('/api/chat_calendar')).json(); }
  catch { document.getElementById('chat-scroll').innerHTML = '<p class="muted center" style="margin-top:40px;">대화를 불러오지 못했어요.</p>'; return; }
  calDays = cal.days || {};
  calMonths = cal.months || [];
  if (!calMonths.length) {
    document.getElementById('chat-scroll').innerHTML = '<p class="muted center" style="margin-top:40px;">아직 적재된 카톡 대화가 없어요.</p>';
    document.getElementById('raw-calendar').innerHTML = '<p class="muted center">대화 없음</p>';
    rawBuilt = true; return;
  }
  buildContinuous();
  const last = calMonths[calMonths.length - 1];
  calState = { y: +last.slice(0, 4), m: +last.slice(5, 7) };
  renderCalendar();
  rawBuilt = true;
}

// ── 월 카운트 / 높이 추정 ──
function monthMsgCount(ym) { let c = 0; for (const d in calDays) if (ymOf(d) === ym) c += calDays[d]; return c; }
function monthActiveDays(ym) { let n = 0; for (const d in calDays) if (ymOf(d) === ym) n++; return n; }
function estMonthHeight(ym) { return Math.max(80, monthMsgCount(ym) * EST_ROW + monthActiveDays(ym) * EST_DIV + 40); }

// ── 연속 채팅 뼈대(월별 플레이스홀더) + 지연 로딩 옵저버 ──
function buildContinuous() {
  const scroll = document.getElementById('chat-scroll');
  const reader = document.getElementById('raw-reader');
  scroll.innerHTML = '';
  calMonths.forEach(ym => {
    const sec = document.createElement('div');
    sec.className = 'chat-month pending';
    sec.dataset.ym = ym;
    sec.style.minHeight = estMonthHeight(ym) + 'px';
    sec.textContent = `${+ym.slice(0, 4)}년 ${+ym.slice(5, 7)}월 …`;
    scroll.appendChild(sec);
  });
  if (monthObserver) monthObserver.disconnect();
  monthObserver = new IntersectionObserver((entries) => {
    entries.forEach(e => { if (e.isIntersecting) loadMonth(e.target.dataset.ym); });
  }, { root: reader, rootMargin: '900px 0px 900px 0px' });
  scroll.querySelectorAll('.chat-month').forEach(s => monthObserver.observe(s));
  showChat();
  // 최신 월부터 보이게: 맨 아래로
  loadMonth(calMonths[calMonths.length - 1]).then(() => { reader.scrollTop = reader.scrollHeight; });
}

async function ensureMonthText(ym) {
  if (monthText[ym] != null) return monthText[ym];
  try {
    const data = await (await fetch(`/api/raw?path=${encodeURIComponent(monthPath(ym))}`)).json();
    monthText[ym] = data.content || '';
  } catch { monthText[ym] = ''; }
  return monthText[ym];
}

async function loadMonth(ym) {
  const sec = document.querySelector(`.chat-month[data-ym="${ym}"]`);
  if (!sec || loadedMonths.has(ym)) return;
  const text = await ensureMonthText(ym);
  if (loadedMonths.has(ym)) return;       // 동시 호출 경쟁 방지
  const reader = document.getElementById('raw-reader');
  const wasAbove = sec.getBoundingClientRect().bottom <= reader.getBoundingClientRect().top + 1;
  const before = sec.offsetHeight;
  sec.classList.remove('pending');
  sec.style.minHeight = '';
  sec.innerHTML = renderChatInner(text, ym);
  loadedMonths.add(ym);
  const delta = sec.offsetHeight - before;
  if (wasAbove && delta) reader.scrollTop += delta;   // 위쪽 로딩 시 스크롤 점프 방지
  pruneMonths(ym);
}

function unloadMonth(ym) {
  const sec = document.querySelector(`.chat-month[data-ym="${ym}"]`);
  if (!sec || !loadedMonths.has(ym)) return;
  sec.style.minHeight = sec.offsetHeight + 'px';      // 높이 유지 → 스크롤 점프 없음
  sec.classList.add('pending');
  sec.innerHTML = `${+ym.slice(0, 4)}년 ${+ym.slice(5, 7)}월 …`;
  loadedMonths.delete(ym);
}

function pruneMonths(keepYm) {
  if (loadedMonths.size <= MAX_LOADED) return;
  const center = calMonths.indexOf(keepYm);
  [...loadedMonths]
    .sort((a, b) => Math.abs(calMonths.indexOf(b) - center) - Math.abs(calMonths.indexOf(a) - center))
    .slice(0, loadedMonths.size - MAX_LOADED)
    .forEach(ym => { if (ym !== keepYm) unloadMonth(ym); });
}

// ── 한 달치 → 버블 HTML (idx는 월 내부 순번 = grep idx와 일치) ──
function renderChatInner(content, ym) {
  const lines = (content || '').split('\n');
  let html = `<div class="chat-month-label">${+ym.slice(0, 4)}년 ${+ym.slice(5, 7)}월</div>`;
  let idx = -1, lastSender = null;
  for (const ln of lines) {
    const dm = ln.match(CHAT_DATE_RE);
    if (dm) {
      const wd = dm[4] ? ` (${dm[4]})` : '';
      html += `<div class="chat-date-divider" data-date="${dm[1]}-${dm[2]}-${dm[3]}">${+dm[1]}년 ${+dm[2]}월 ${+dm[3]}일${wd}</div>`;
      lastSender = null; continue;
    }
    const mm = ln.match(CHAT_MSG_RE);
    if (!mm) continue;
    idx++;
    const time = mm[1], sender = mm[2], text = mm[3];
    const me = sender === '나';
    const grouped = sender === lastSender;
    if (!me && !grouped) html += `<div class="chat-sender">상대</div>`;
    html += `<div class="chat-row ${me ? 'me' : 'wife'}${grouped ? ' grouped' : ''}" data-idx="${idx}">` +
            `<div class="chat-bubble">${highlightHtml(text, grepTokens)}</div><span class="chat-time">${time}</span></div>`;
    lastSender = sender;
  }
  return html;
}

// ── 점프 ──
function flashEl(el) { if (el) { el.classList.add('flash'); setTimeout(() => el.classList.remove('flash'), 1900); } }

async function jumpToMonthIdx(ym, idx) {
  showChat();
  await loadMonth(ym);
  requestAnimationFrame(() => {
    const sec = document.querySelector(`.chat-month[data-ym="${ym}"]`);
    const row = sec && sec.querySelector(idx != null ? `.chat-row[data-idx="${idx}"]` : '.chat-row');
    if (row) { row.scrollIntoView({ block: 'center' }); flashEl(row.querySelector('.chat-bubble')); }
    else if (sec) sec.scrollIntoView({ block: 'start' });
  });
}

async function jumpToDate(dateStr) {
  showChat();
  const ym = ymOf(dateStr);
  await loadMonth(ym);
  requestAnimationFrame(() => {
    const div = document.querySelector(`.chat-date-divider[data-date="${dateStr}"]`);
    if (div) { div.scrollIntoView({ block: 'start' }); flashEl(div); }
    else jumpToMonthIdx(ym);
  });
  document.querySelectorAll('.cal-day.jumped').forEach(d => d.classList.remove('jumped'));
  const cell = document.querySelector(`.cal-day[data-date="${dateStr}"]`);
  if (cell) cell.classList.add('jumped');
}

// citations / 노드 출처 링크에서 호출 (path = 월 파일, jumpIdx = 월 내부 순번)
async function openRaw(path, _el, jumpIdx) {
  const m = (path || '').match(CHAT_PATH_RE);
  if (!m) return;
  await loadRaw();
  jumpToMonthIdx(`${m[2]}-${m[3]}`, jumpIdx == null ? null : jumpIdx);
}

// ── grep: 대화 전체 즉석 검색 (AI 아님) ──
function showChat() { document.getElementById('chat-scroll').style.display = ''; document.getElementById('grep-panel').style.display = 'none'; }
function showGrep() { document.getElementById('chat-scroll').style.display = 'none'; document.getElementById('grep-panel').style.display = ''; }

function bindGrep() {
  const input = document.getElementById('grep-input');
  if (!input || input.dataset.bound) return;
  input.dataset.bound = '1';
  let timer = null;
  input.addEventListener('input', () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 2) { grepTokens = []; if (q.length === 0) showChat(); return; }
    timer = setTimeout(() => runGrep(q), 280);
  });
}

async function runGrep(q) {
  const panel = document.getElementById('grep-panel');
  showGrep();
  panel.innerHTML = '<p class="muted center" style="margin-top:30px;">검색 중…</p>';
  grepTokens = q.toLowerCase().split(/\s+/).filter(Boolean);
  let data;
  try { data = await (await fetch(`/api/grep?q=${encodeURIComponent(q)}`)).json(); }
  catch { panel.innerHTML = '<p class="center" style="color:#e11d48;">검색 실패</p>'; return; }
  if (!data.results.length) {
    panel.innerHTML = `<div class="grep-stat">"<b>${escapeHtml(q)}</b>" — 일치하는 메시지가 없어요.</div>`; return;
  }
  const head = `<div class="grep-stat">"<b>${escapeHtml(q)}</b>" — 총 <b>${fmt(data.total)}</b>번 등장${
    data.truncated ? ` · 시간순 상위 <b>${data.results.length}</b>개` : ''} · 클릭하면 그 대화로 점프</div>`;
  const items = data.results.map(r => {
    const m = r.path.match(CHAT_PATH_RE); const ym = m ? `${m[2]}-${m[3]}` : '';
    return `<div class="grep-item" data-ym="${ym}" data-idx="${r.idx}">
      <span class="grep-meta">${r.date} ${r.time}</span>
      <span class="grep-sender ${r.sender === '나' ? 'me' : 'wife'}">${r.sender === '나' ? '나' : '상대'}</span>
      <span class="grep-text">${highlightHtml(r.text, grepTokens)}</span></div>`;
  }).join('');
  panel.innerHTML = head + `<div class="grep-results">${items}</div>`;
  panel.querySelectorAll('.grep-item').forEach(it => {
    it.onclick = () => jumpToMonthIdx(it.dataset.ym, parseInt(it.dataset.idx, 10));
  });
}

// ── 캘린더 (오른쪽: 날짜 점프) ──
function renderCalendar() {
  const box = document.getElementById('raw-calendar');
  const { y, m } = calState;
  const ymStr = `${y}-${String(m).padStart(2, '0')}`;
  const first = calMonths[0], last = calMonths[calMonths.length - 1];
  const firstDow = new Date(y, m - 1, 1).getDay();
  const ndays = new Date(y, m, 0).getDate();
  let cells = '';
  for (let i = 0; i < firstDow; i++) cells += '<div class="cal-day empty"></div>';
  for (let d = 1; d <= ndays; d++) {
    const ds = `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    const c = calDays[ds] || 0;
    if (c > 0) {
      const lvl = c >= 120 ? 'lvl3' : c >= 30 ? 'lvl2' : '';
      cells += `<div class="cal-day active ${lvl}" data-date="${ds}" title="${c.toLocaleString('ko-KR')}개 메시지">${d}</div>`;
    } else cells += `<div class="cal-day inactive">${d}</div>`;
  }
  box.innerHTML =
    `<div class="cal-head">
       <div class="cal-nav">
         <button class="cal-btn" data-go="py" ${y <= +first.slice(0, 4) ? 'disabled' : ''}>«</button>
         <button class="cal-btn" data-go="pm" ${ymStr <= first ? 'disabled' : ''}>‹</button>
       </div>
       <div class="cal-title">${y}년 ${m}월</div>
       <div class="cal-nav">
         <button class="cal-btn" data-go="nm" ${ymStr >= last ? 'disabled' : ''}>›</button>
         <button class="cal-btn" data-go="ny" ${y >= +last.slice(0, 4) ? 'disabled' : ''}>»</button>
       </div>
     </div>
     <div class="cal-grid">${DOW_KO.map((d, i) => `<div class="cal-dow ${i === 0 ? 'sun' : i === 6 ? 'sat' : ''}">${d}</div>`).join('')}${cells}</div>
     <div class="cal-foot">점 = 그날 대화 있음(진할수록 많음). 날짜를 누르면 그 대화로 점프해요.
       <div class="cal-jump-row">
         <button class="cal-first">⏮ 맨 처음</button>
         <button class="cal-last">가장 최근 ⏭</button>
       </div>
     </div>`;
  box.querySelectorAll('.cal-day.active').forEach(c => c.onclick = () => jumpToDate(c.dataset.date));
  box.querySelectorAll('.cal-btn[data-go]').forEach(b => b.onclick = () => calNav(b.dataset.go));
  box.querySelector('.cal-first').onclick = () => jumpFirstLast(first, true);
  box.querySelector('.cal-last').onclick = () => jumpFirstLast(last, false);
}

function calNav(go) {
  let { y, m } = calState;
  if (go === 'pm') { m--; if (m < 1) { m = 12; y--; } }
  else if (go === 'nm') { m++; if (m > 12) { m = 1; y++; } }
  else if (go === 'py') y--;
  else if (go === 'ny') y++;
  calState = { y, m };
  renderCalendar();
}

function datesOfMonth(ym) { return Object.keys(calDays).filter(d => ymOf(d) === ym).sort(); }
function jumpFirstLast(ym, isFirst) {
  calState = { y: +ym.slice(0, 4), m: +ym.slice(5, 7) };
  renderCalendar();
  const ds = datesOfMonth(ym);
  const target = isFirst ? ds[0] : ds[ds.length - 1];
  if (target) jumpToDate(target);
}

function highlightHtml(text, tokens) {
  let html = escapeHtml(text);
  if (tokens && tokens.length) {
    const re = new RegExp('(' + tokens.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')', 'gi');
    html = html.replace(re, '<mark class="hl">$1</mark>');
  }
  return html;
}

// ----------------------------- helpers -----------------------------
function renderMarkdown(text) {
  // 레거시 [[slug|label]] / [[slug]] → wikilink anchor (raw/·log 뷰에 잔존; marked 전 변환)
  const withLinks = (text || '').replace(/\[\[([^\]]+)\]\]/g, (_, inner) => {
    const slug = inner.split('|')[0].split('#')[0].trim();
    const label = inner.includes('|') ? inner.split('|')[1].trim() : inner;
    return `<a href="#" class="wikilink" data-slug="${slug.toLowerCase()}">${escapeHtml(label)}</a>`;
  });
  let html = (typeof marked !== 'undefined') ? marked.parse(withLinks) : escapeHtml(withLinks);
  // OKF: marked가 만든 본문 마크다운 링크 <a href="….md"> → 인앱 네비 wikilink로 (외부·raw 대상 제외)
  html = html.replace(/<a href="([^"]*\.md)(?:#[^"]*)?"([^>]*)>/g, (m, path, rest) => {
    if (/^https?:/i.test(path) || /(^|\/)raw\//.test(path)) return m;
    const slug = path.replace(/^.*\//, '').replace(/\.md$/, '').toLowerCase();
    return `<a href="#" class="wikilink" data-slug="${slug}"${rest}>`;
  });
  return html;
}

function bindWikiLinks(scope) {
  scope.querySelectorAll('.wikilink, .link-item[data-slug]').forEach(a => {
    a.addEventListener('click', (e) => { e.preventDefault(); locateNode(a.dataset.slug); });
  });
  scope.querySelectorAll('[data-raw]').forEach(s => {
    s.addEventListener('click', () => { switchTab('raw'); loadRaw().then(() => openRaw(s.dataset.raw)); });
  });
}

function locateNode(slug) {
  const n = allNodes.find(x => x.slug === slug);
  if (n) { switchTab('explorer'); setTimeout(() => openNodeDetail(slug), 60); }
  else { switchTab('graph'); setTimeout(() => { selectedSlug = slug; showNodeDetail(slug); }, 60); }
}

// ----------------------------- 5. DOMAIN VIEW -----------------------------
let domainData = [];

const DOMAIN_COLORS = ['#ec4899','#8b5cf6','#f472b6','#db2777','#a855f7','#f59e0b','#0ea5e9','#10b981'];
function domainColor(name) {
  let h = 0;
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) & 0xffff;
  return DOMAIN_COLORS[h % DOMAIN_COLORS.length];
}
function domainInitial(name) {
  return name.slice(0, 2).toUpperCase();
}

async function loadDomains() {
  const grid = document.getElementById('domain-grid');
  const detail = document.getElementById('domain-detail');
  detail.style.display = 'none';
  grid.style.display = 'grid';
  if (!domainData.length) {
    grid.innerHTML = '<p class="muted center" style="grid-column:1/-1;padding:40px;">로딩 중…</p>';
    try { domainData = await (await fetch('/api/domains')).json(); }
    catch { grid.innerHTML = '<p class="center" style="color:#ef4444;grid-column:1/-1;">로딩 실패</p>'; return; }
  }
  renderDomainGrid();
  document.getElementById('domain-back-btn').onclick = () => {
    detail.style.display = 'none';
    grid.style.display = 'grid';
  };
}

function renderDomainGrid() {
  const grid = document.getElementById('domain-grid');
  grid.innerHTML = '';
  domainData.forEach(d => {
    const color = domainColor(d.name);
    const card = document.createElement('div');
    card.className = 'domain-card';
    card.onclick = () => openDomain(d.name);

    const typeChips = Object.entries(d.by_type || {}).map(([t, cnt]) =>
      `<span class="domain-type-chip"><span class="domain-type-dot" style="background:${TYPE_COLORS[t]||TH.accent}"></span>${TYPE_LABEL[t]||t} ${cnt}</span>`
    ).join('');

    const tags = (d.tags || []).map(([t]) =>
      `<span class="domain-tag">${escapeHtml(t)}</span>`
    ).join('');

    const recent = (d.recent_nodes || []).map(n =>
      `<div class="domain-recent-item">
        <span class="type-tag type-${n.type}" style="font-size:.62rem;padding:1px 6px;">${n.type}</span>
        <span class="domain-recent-slug">${escapeHtml(n.slug)}</span>
        <span class="domain-recent-tldr">${escapeHtml(n.tldr)}</span>
      </div>`
    ).join('');

    card.innerHTML = `
      <div class="domain-card-header">
        <div class="domain-icon" style="background:${color}">${domainInitial(d.name)}</div>
        <div>
          <div class="domain-name">${escapeHtml(d.name)}</div>
          <div class="domain-stats">wiki ${d.wiki_count}개 · raw ${d.raw_count}개</div>
        </div>
      </div>
      <div class="domain-card-body">
        <div class="domain-type-row">${typeChips || '<span class="muted" style="font-size:.8rem;">노드 없음</span>'}</div>
        ${tags ? `<div class="domain-tags">${tags}</div>` : ''}
        ${recent ? `<div class="domain-recent">${recent}</div>` : ''}
      </div>`;
    grid.appendChild(card);
  });
}

function openDomain(name) {
  const d = domainData.find(x => x.name === name);
  if (!d) return;
  const grid = document.getElementById('domain-grid');
  const detail = document.getElementById('domain-detail');
  grid.style.display = 'none';
  detail.style.display = 'block';

  const color = domainColor(d.name);
  const wikiNodes = allNodes.filter(n => n.domain === name);

  const nodeCardsHTML = wikiNodes.length
    ? wikiNodes.map(n => `
        <div class="node-card" onclick="openNodeDetailFromDomain('${escapeHtml(n.slug)}')">
          <span class="type-tag type-${n.type}">${TYPE_LABEL[n.type]||n.type}</span>
          <h4>${escapeHtml(n.slug)}</h4>
          <div class="tldr">${escapeHtml(n.tldr||'(tldr 없음)')}</div>
          <div class="node-tags">${(n.tags||[]).map(t=>`<span class="node-tag">${escapeHtml(t)}</span>`).join('')}</div>
        </div>`).join('')
    : '<p class="muted">wiki 노드 없음</p>';

  const rawHTML = (d.raw_docs || []).map(doc => `
    <span class="src-item link-item" onclick="openRawFromDomain('${escapeHtml(doc.path)}')" style="cursor:pointer;">
      ${escapeHtml(doc.title)}<span class="muted" style="font-size:.72rem;margin-left:8px;">${escapeHtml(doc.path)}</span>
    </span>`).join('') || '<p class="muted">원본 문서 없음</p>';

  document.getElementById('domain-detail-content').innerHTML = `
    <div class="domain-detail-header">
      <div class="domain-detail-icon" style="background:${color}">${domainInitial(d.name)}</div>
      <div class="domain-detail-meta">
        <h2>${escapeHtml(d.name)}</h2>
        <p>wiki 노드 ${d.wiki_count}개 · 원본 문서 ${d.raw_count}개</p>
      </div>
    </div>
    <div class="domain-section-title">wiki 노드</div>
    <div class="node-cards">${nodeCardsHTML}</div>
    <div class="domain-section-title" style="margin-top:28px;">원본 소스 (raw)</div>
    <div>${rawHTML}</div>`;
}

function openNodeDetailFromDomain(slug) {
  switchTab('explorer');
  if (!allNodes.length) {
    loadNodes().then(() => setTimeout(() => openNodeDetail(slug), 80));
  } else {
    setTimeout(() => openNodeDetail(slug), 60);
  }
}

function openRawFromDomain(path) {
  switchTab('raw');
  loadRaw().then(() => openRaw(path));
}

// ----------------------------- 6. CHATBOT -----------------------------
async function loadHealth() {
  try {
    const r = await fetch('/api/health');
    const data = await r.json();
    const footer = document.getElementById('rag-status');
    if (footer) {
      footer.textContent = data.claude_bin
        ? `RAG: claude CLI (${data.claude_bin.split('/').pop()})`
        : 'RAG: 키워드 폴백 (claude CLI 없음)';
    }
  } catch {}
}

let chatBusy = false;

async function sendChatMessage() {
  if (chatBusy) return;                       // 응답 대기 중 중복 전송 방지
  const input = document.getElementById('chatbot-input');
  const question = input.value.trim();
  if (!question) return;
  input.value = '';

  chatBusy = true;
  appendBubble('user', question);
  const loadingId = appendLoadingBubble();

  try {
    const r = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });
    const data = await r.json();
    removeBubble(loadingId);
    appendBubble('bot', data.answer || '(응답 없음)', data.citations || [], data.engine);
  } catch (e) {
    removeBubble(loadingId);
    appendBubble('bot', `오류가 발생했어요: ${e.message}`);
  } finally {
    chatBusy = false;
  }
}

function appendLoadingBubble() {
  const box = document.getElementById('chatbot-messages');
  const id = 'bubble-loading-' + Date.now();
  const wrap = document.createElement('div');
  wrap.className = 'bot-msg';
  wrap.id = id;
  const label = '생각하는 중…';
  wrap.innerHTML =
    `<div class="bot-avatar">AI</div>
     <div class="bot-text-bubble">
       <div class="typing"><span></span><span></span><span></span></div>
       <span class="typing-label">${label}</span>
     </div>`;
  box.appendChild(wrap);
  box.scrollTop = box.scrollHeight;
  return id;
}

function appendBubble(role, text, citations = [], engine = '') {
  const box = document.getElementById('chatbot-messages');
  const id = 'bubble-' + Date.now() + '-' + Math.random().toString(36).slice(2);

  if (role === 'user') {
    const el = document.createElement('div');
    el.className = 'user-msg';
    el.id = id;
    el.textContent = text;
    box.appendChild(el);
  } else {
    const wrap = document.createElement('div');
    wrap.className = 'bot-msg';
    wrap.id = id;
    const avatar = document.createElement('div');
    avatar.className = 'bot-avatar';
    avatar.textContent = 'AI';
    const bubble = document.createElement('div');
    bubble.className = 'bot-text-bubble';
    bubble.innerHTML = renderMarkdown(text);

    if (citations.length) {
      const cite = document.createElement('div');
      cite.className = 'citations';
      citations.forEach(p => {
        const badge = document.createElement('span');
        badge.className = 'citation-badge';
        badge.textContent = p.split('/').slice(-1)[0];
        badge.title = p;
        badge.onclick = () => openCitation(p);
        cite.appendChild(badge);
      });
      bubble.appendChild(cite);
    }
    if (engine) {
      const eng = document.createElement('div');
      eng.style.cssText = 'font-size:.7rem;color:var(--muted);margin-top:8px;';
      eng.textContent = `engine: ${engine}`;
      bubble.appendChild(eng);
    }
    wrap.appendChild(avatar);
    wrap.appendChild(bubble);
    box.appendChild(wrap);
  }
  box.scrollTop = box.scrollHeight;
  return id;
}

function removeBubble(id) {
  document.getElementById(id)?.remove();
}

function openCitation(path) {
  if (path.startsWith('wiki/')) {
    const slug = path.replace(/^wiki\/[^/]+\//, '').replace(/\.md$/, '');
    locateNode(slug);
  } else if (path.startsWith('raw/')) {
    switchTab('raw');
    loadRaw().then(() => openRaw(path));
  }
}

function escapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
