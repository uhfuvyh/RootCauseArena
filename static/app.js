/**
 * RootCauseArena V3 — Interactive Dashboard Logic
 */

// ═══════════════════════════════════════════════
// State
// ═══════════════════════════════════════════════
const state = {
  sessionId: null,
  tasks: [],
  selectedTask: null,
  selectedTarget: null,
  currentObs: null,
  totalReward: 0,
  running: false,
  startTime: null,
};

// ═══════════════════════════════════════════════
// DOM refs
// ═══════════════════════════════════════════════
const $ = id => document.getElementById(id);

const DOM = {
  serverBadge:    $('server-status-badge'),
  taskGrid:       $('task-grid'),
  statStep:       $('stat-step'),
  statReward:     $('stat-reward'),
  statInspections:$('stat-inspections'),
  statMax:        $('stat-max'),
  progressFill:   $('progress-fill'),
  progressPct:    $('progress-pct'),
  actionTargets:  $('action-targets'),
  actionButtons:  $('action-buttons'),
  btnNoOp:        $('btn-no-op'),
  btnRunBaseline: $('btn-run-baseline'),
  componentsGrid: $('components-grid'),
  noSessionOvl:   $('no-session-overlay'),
  episodeBadge:   $('episode-badge'),
  logConsole:     $('log-console'),
  btnClearLogs:   $('btn-clear-logs'),
  baselineSection:$('baseline-section'),
  baselineTbody:  $('baseline-tbody'),
  modalOverlay:   $('modal-overlay'),
  modalTitle:     $('modal-title'),
  modalBody:      $('modal-body'),
  modalConfirm:   $('modal-confirm'),
  modalCancel:    $('modal-cancel'),
};

// ═══════════════════════════════════════════════
// Utility
// ═══════════════════════════════════════════════
const COMPONENT_ICONS = {
  database: '🗄️',
  api:      '🌐',
  cache:    '⚡',
  queue:    '📬',
};

const ACTION_LABELS = {
  repair_database: '🔧 Repair DB',
  restart_service: '🔄 Restart Service',
  clear_cache:     '🧹 Clear Cache',
  scale_up:        '📈 Scale Up',
  inspect_database:'🔍 Inspect DB',
  inspect_api:     '🔍 Inspect API',
  inspect_cache:   '🔍 Inspect Cache',
  inspect_queue:   '🔍 Inspect Queue',
};

const TARGET_ACTION_MAP = {
  database: ['repair_database', 'inspect_database'],
  api:      ['restart_service', 'inspect_api'],
  cache:    ['clear_cache',     'inspect_cache'],
  queue:    ['scale_up',        'inspect_queue'],
};

function formatReward(r) {
  if (r === null || r === undefined || isNaN(r)) return '—';
  return (r >= 0 ? '+' : '') + r.toFixed(2);
}

function nowStr() {
  if (!state.startTime) return '00:00';
  const s = Math.floor((Date.now() - state.startTime) / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}

// ═══════════════════════════════════════════════
// Logging
// ═══════════════════════════════════════════════
function addLog(message, type = 'info', tag = null) {
  const entry = document.createElement('div');
  entry.className = `log-entry log-${type}`;

  const tagLabel = tag || type.toUpperCase();
  entry.innerHTML =
    `<span class="log-ts">${nowStr()}</span>` +
    `<span class="log-tag">${tagLabel}</span>` +
    `<span class="log-msg">${message}</span>`;

  DOM.logConsole.appendChild(entry);
  DOM.logConsole.scrollTop = DOM.logConsole.scrollHeight;
}

function renderEnvLogs(logs) {
  if (!logs || !logs.length) return;
  logs.forEach(l => {
    const t = (l.severity || 'INFO').toLowerCase();
    const type = t === 'error' ? 'error' : t === 'warn' ? 'warn' : 'info';
    addLog(l.message, type, l.severity);
  });
}

// ═══════════════════════════════════════════════
// Server Health Check
// ═══════════════════════════════════════════════
async function checkServerHealth() {
  try {
    const res = await fetch('/health');
    if (res.ok) {
      DOM.serverBadge.querySelector('.status-dot').className = 'status-dot online';
      DOM.serverBadge.querySelector('.status-text').textContent = 'API Online';
    } else { throw new Error(); }
  } catch {
    DOM.serverBadge.querySelector('.status-dot').className = 'status-dot error';
    DOM.serverBadge.querySelector('.status-text').textContent = 'API Offline';
  }
}

// ═══════════════════════════════════════════════
// Load Tasks
// ═══════════════════════════════════════════════
async function loadTasks() {
  try {
    const res = await fetch('/tasks');
    const data = await res.json();
    state.tasks = data.tasks || [];
    renderTaskGrid();
    addLog(`Loaded ${state.tasks.length} missions. Select one to begin.`, 'system', 'SYS');
  } catch (e) {
    addLog('Failed to load tasks from API.', 'error', 'ERR');
  }
}

function renderTaskGrid() {
  DOM.taskGrid.innerHTML = '';
  const taskColors = { easy: '#10b981', medium: '#f59e0b', hard: '#ef4444', extreme: '#8b5cf6' };

  state.tasks.forEach(task => {
    const diff = (task.difficulty || 'easy').toLowerCase();
    const color = taskColors[diff] || '#3b82f6';
    const card = document.createElement('div');
    card.className = 'task-card';
    card.dataset.taskId = task.task_id;
    card.style.setProperty('--task-color', color);
    card.innerHTML = `
      <div class="task-card-title">${task.task_id.replace('_', ' ').toUpperCase()}</div>
      <div class="task-card-meta">${task.description.slice(0, 55)}…</div>
      <span class="difficulty-badge difficulty-${diff}">${diff}</span>
    `;
    card.addEventListener('click', () => selectTask(task, card));
    DOM.taskGrid.appendChild(card);
  });
}

function selectTask(task, cardEl) {
  if (state.running) return;
  state.selectedTask = task;
  document.querySelectorAll('.task-card').forEach(c => c.classList.remove('active'));
  cardEl.classList.add('active');
  addLog(`Mission selected: <strong>${task.task_id}</strong> (${task.difficulty}) — ${task.max_steps} max steps`, 'system', 'SYS');
  showStartModal(task);
}

// ═══════════════════════════════════════════════
// Start Modal
// ═══════════════════════════════════════════════
function showStartModal(task) {
  DOM.modalTitle.textContent = `⚡ Launch: ${task.task_id.replace('_', ' ').toUpperCase()}`;
  DOM.modalBody.innerHTML = `
    <strong>Difficulty:</strong> ${task.difficulty}<br>
    <strong>Max Steps:</strong> ${task.max_steps}<br>
    <strong>Optimal Steps:</strong> ${task.optimal_steps}<br><br>
    ${task.description}<br><br>
    <em>Your goal: Diagnose the hidden root cause and repair the system efficiently.</em>
  `;
  DOM.modalOverlay.style.display = 'flex';
}

DOM.modalConfirm.addEventListener('click', async () => {
  DOM.modalOverlay.style.display = 'none';
  await startSession();
});
DOM.modalCancel.addEventListener('click', () => {
  DOM.modalOverlay.style.display = 'none';
});

// ═══════════════════════════════════════════════
// Session: Start
// ═══════════════════════════════════════════════
async function startSession() {
  if (!state.selectedTask) return;
  try {
    addLog(`Initialising environment for: ${state.selectedTask.task_id}…`, 'system', 'SYS');
    const res = await fetch('/session/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: state.selectedTask.task_id }),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();

    state.sessionId = data.session_id;
    state.currentObs = data.observation;
    state.totalReward = 0;
    state.running = true;
    state.startTime = Date.now();

    DOM.noSessionOvl.style.display = 'none';
    setEpisodeBadge('running', 'RUNNING');
    renderComponents(data.observation);
    updateStats(data.observation);
    buildActionTargets();
    enableActions(true);

    addLog(`Episode started. Session: ${state.sessionId.slice(0, 8)}…`, 'success', 'START');
    renderEnvLogs(data.observation.logs);
  } catch (e) {
    addLog(`Failed to start session: ${e.message}`, 'error', 'ERR');
  }
}

// ═══════════════════════════════════════════════
// Session: Step
// ═══════════════════════════════════════════════
async function sendAction(actionType) {
  if (!state.running || !state.sessionId || !state.selectedTarget) return;

  try {
    addLog(`Action: <strong>${actionType}</strong> → ${state.selectedTarget}`, 'warn', 'ACT');

    const res = await fetch('/session/step', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: state.sessionId,
        action_type: actionType,
        target: state.selectedTarget,
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();

    state.currentObs = data.observation;
    state.totalReward += (data.reward || 0);

    renderComponents(data.observation);
    updateStats(data.observation);
    renderEnvLogs(data.observation.logs);

    if (data.reward !== 0) {
      addLog(`Reward: ${formatReward(data.reward)} — ${data.info || ''}`, data.reward > 0 ? 'success' : 'warn', 'RWD');
    }

    if (data.done) {
      state.running = false;
      enableActions(false);
      const success = data.success;
      setEpisodeBadge(success ? 'success' : 'failed', success ? '✅ RESOLVED' : '❌ FAILED');
      addLog(`Episode complete. Total reward: ${formatReward(state.totalReward)} | ${success ? 'SUCCESS' : 'FAILED'}`, success ? 'success' : 'error', 'END');
    }
  } catch (e) {
    addLog(`Step failed: ${e.message}`, 'error', 'ERR');
  }
}

async function sendNoOp() {
  if (!state.running || !state.sessionId) return;
  // No-op uses database target (arbitrary, action is 'no_op')
  try {
    addLog('Action: <strong>no_op</strong> (Wait)', 'info', 'ACT');
    const res = await fetch('/session/step', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: state.sessionId, action_type: 'no_op', target: 'database' }),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();

    state.currentObs = data.observation;
    state.totalReward += (data.reward || 0);
    renderComponents(data.observation);
    updateStats(data.observation);
    renderEnvLogs(data.observation.logs);

    if (data.done) {
      state.running = false;
      enableActions(false);
      const success = data.success;
      setEpisodeBadge(success ? 'success' : 'failed', success ? '✅ RESOLVED' : '❌ FAILED');
      addLog(`Episode complete. Total reward: ${formatReward(state.totalReward)}`, success ? 'success' : 'error', 'END');
    }
  } catch (e) {
    addLog(`No-op failed: ${e.message}`, 'error', 'ERR');
  }
}

// ═══════════════════════════════════════════════
// Render: Components
// ═══════════════════════════════════════════════
function renderComponents(obs) {
  const existingCards = {};
  DOM.componentsGrid.querySelectorAll('.component-card').forEach(c => {
    existingCards[c.dataset.comp] = c;
  });

  const components = ['database', 'api', 'cache', 'queue'];
  components.forEach(compName => {
    const metrics = obs.metrics?.[compName];
    if (!metrics) return;

    const status = inferStatus(metrics);
    let card = existingCards[compName];
    const isNew = !card;

    if (isNew) {
      card = document.createElement('div');
      card.className = 'component-card';
      card.dataset.comp = compName;
      DOM.componentsGrid.appendChild(card);
    }

    card.className = `component-card status-${status}`;
    card.innerHTML = buildComponentHTML(compName, metrics, status);
  });
}

function inferStatus(metrics) {
  if (metrics.error_rate > 0.7 || metrics.latency > 850) return 'down';
  if (metrics.error_rate > 0.25 || metrics.latency > 400) return 'degraded';
  return 'healthy';
}

function buildComponentHTML(name, m, status) {
  const latencyPct  = Math.min(m.latency / 1000 * 100, 100);
  const errorPct    = m.error_rate * 100;
  const queuePct    = Math.min(m.queue_load / 4 * 100, 100);
  const cpuPct      = m.cpu_usage;

  return `
    <div class="comp-header">
      <div class="comp-name">
        <span class="comp-icon">${COMPONENT_ICONS[name] || '⚙️'}</span>
        ${name}
      </div>
      <span class="comp-status-pill pill-${status}">${status}</span>
    </div>
    <div class="metrics-list">
      <div class="metric-row">
        <div class="metric-header">
          <span class="metric-name">Latency</span>
          <span class="metric-val">${m.latency}ms</span>
        </div>
        <div class="metric-track"><div class="metric-fill fill-latency" style="width:${latencyPct}%"></div></div>
      </div>
      <div class="metric-row">
        <div class="metric-header">
          <span class="metric-name">Error Rate</span>
          <span class="metric-val">${(errorPct).toFixed(1)}%</span>
        </div>
        <div class="metric-track"><div class="metric-fill fill-error" style="width:${errorPct}%"></div></div>
      </div>
      <div class="metric-row">
        <div class="metric-header">
          <span class="metric-name">Queue Load</span>
          <span class="metric-val">${m.queue_load.toFixed(2)}</span>
        </div>
        <div class="metric-track"><div class="metric-fill fill-queue" style="width:${queuePct}%"></div></div>
      </div>
      <div class="metric-row">
        <div class="metric-header">
          <span class="metric-name">CPU</span>
          <span class="metric-val">${m.cpu_usage.toFixed(1)}%</span>
        </div>
        <div class="metric-track"><div class="metric-fill fill-cpu" style="width:${cpuPct}%"></div></div>
      </div>
    </div>
  `;
}

// ═══════════════════════════════════════════════
// Render: Action UI
// ═══════════════════════════════════════════════
function buildActionTargets() {
  DOM.actionTargets.innerHTML = '';
  ['database', 'api', 'cache', 'queue'].forEach(t => {
    const btn = document.createElement('button');
    btn.className = 'target-btn';
    btn.textContent = `${COMPONENT_ICONS[t]} ${t}`;
    btn.dataset.target = t;
    btn.addEventListener('click', () => selectTarget(t, btn));
    DOM.actionTargets.appendChild(btn);
  });
}

function selectTarget(target, btn) {
  if (!state.running) return;
  state.selectedTarget = target;
  document.querySelectorAll('.target-btn').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  renderActionButtons(target);
}

function renderActionButtons(target) {
  DOM.actionButtons.innerHTML = '';
  const actions = TARGET_ACTION_MAP[target] || [];
  actions.forEach(actionType => {
    const btn = document.createElement('button');
    btn.className = `btn ${actionType.startsWith('inspect') ? 'btn-secondary' : 'btn-primary'}`;
    btn.textContent = ACTION_LABELS[actionType] || actionType;
    btn.addEventListener('click', () => sendAction(actionType));
    DOM.actionButtons.appendChild(btn);
  });
}

function enableActions(enabled) {
  DOM.btnNoOp.disabled = !enabled;
  DOM.actionTargets.querySelectorAll('.target-btn').forEach(b => b.disabled = !enabled);
}

// ═══════════════════════════════════════════════
// Render: Stats
// ═══════════════════════════════════════════════
function updateStats(obs) {
  DOM.statStep.textContent = obs.step_count ?? '—';
  DOM.statReward.textContent = formatReward(state.totalReward);
  DOM.statInspections.textContent = obs.inspections_remaining ?? '—';
  DOM.statMax.textContent = obs.max_steps ?? '—';

  if (obs.max_steps && obs.step_count !== undefined) {
    const pct = Math.min(obs.step_count / obs.max_steps * 100, 100);
    DOM.progressFill.style.width = `${pct}%`;
    DOM.progressPct.textContent = `${pct.toFixed(0)}%`;
  }
}

function setEpisodeBadge(type, label) {
  DOM.episodeBadge.className = `episode-status-badge ${type}`;
  DOM.episodeBadge.textContent = label;
}

// ═══════════════════════════════════════════════
// Baseline Agent
// ═══════════════════════════════════════════════
DOM.btnRunBaseline.addEventListener('click', async () => {
  DOM.btnRunBaseline.disabled = true;
  DOM.btnRunBaseline.textContent = '⏳ Running…';
  addLog('Dispatching baseline agent across all tasks…', 'system', 'BL');

  try {
    const res = await fetch('/baseline');
    const data = await res.json();
    DOM.baselineTbody.innerHTML = '';
    data.results.forEach(r => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${r.task_id}</td>
        <td>${r.steps_taken}</td>
        <td>${formatReward(r.total_reward)}</td>
        <td>${r.score.toFixed(3)}</td>
        <td>${(r.efficiency * 100).toFixed(1)}%</td>
        <td class="${r.success ? 'result-success' : 'result-fail'}">${r.success ? '✅ PASS' : '❌ FAIL'}</td>
      `;
      DOM.baselineTbody.appendChild(tr);
      addLog(`Task <strong>${r.task_id}</strong>: score ${r.score.toFixed(3)} | ${r.success ? 'PASS' : 'FAIL'}`, r.success ? 'success' : 'error', 'BL');
    });
    DOM.baselineSection.style.display = 'flex';
  } catch (e) {
    addLog(`Baseline run failed: ${e.message}`, 'error', 'ERR');
  } finally {
    DOM.btnRunBaseline.disabled = false;
    DOM.btnRunBaseline.textContent = '🤖 Run Baseline Agent';
  }
});

// ═══════════════════════════════════════════════
// Misc Events
// ═══════════════════════════════════════════════
DOM.btnNoOp.addEventListener('click', sendNoOp);
DOM.btnClearLogs.addEventListener('click', () => { DOM.logConsole.innerHTML = ''; });

// ═══════════════════════════════════════════════
// Boot
// ═══════════════════════════════════════════════
(async () => {
  await checkServerHealth();
  await loadTasks();
})();
