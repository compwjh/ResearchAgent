/* Spec027 Task04/05: independent research-task workspace. No app.js private bindings are used. */
(function exposeResearchTasks(root, factory) {
  const api = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root && root.document) api.boot(root.document);
}(typeof globalThis !== 'undefined' ? globalThis : this, function researchTasksFactory(root) {
  const TERMINAL_STATUSES = new Set(['partial', 'completed', 'failed', 'cancelled', 'interrupted']);
  const EVENT_TYPES = ['task', 'plan', 'worker', 'model', 'coverage', 'report', 'terminal'];
  const STATUS_TEXT = {
    draft: '草稿', planning: '规划中', running: '执行中', waiting_approval: '等待计划审核',
    partial: '部分完成', completed: '已完成', failed: '失败', cancelled: '已取消', interrupted: '已中断',
  };
  const ERROR_TEXT = {
    TASK_DELETED: '任务已被删除，请刷新任务列表。',
    RESEARCH_CASCADE_FAILED: '任务关联数据清理失败，请稍后重试。',
    INTERNAL_ERROR: '研究任务发生内部错误，请稍后重试。',
    TASK_NOT_FOUND: '找不到该研究任务，请刷新任务列表。',
    TASK_TERMINAL_CONFLICT: '任务已经结束，不能再次执行此操作。',
    PLAN_VALIDATION_FAILED: '研究目标或计划参数不符合要求，请检查后重试。',
    BUDGET_EXCEEDED: '已达到研究预算上限，系统停止新增研究节点。',
    SOURCE_DEGRADED: '部分研究来源失败或降级，结果可能不完整。',
    SOURCE_UNAVAILABLE: '研究来源暂时不可用，结果可能不完整。',
    RESOURCE_PROBE_FAILED: '资源探针不可用，Worker 已按降级额度运行。',
    MODEL_ESCALATED: 'fast 模型重试后已升级到 strong 模型。',
    NO_NEW_EVIDENCE: '连续轮次没有新增有效证据，系统停止补搜。',
    NO_NEW_PAPERS: '连续轮次没有新增论文证据，系统停止补搜。',
    REPORT_NOT_READY: '报告尚未生成，任务完成后会自动显示。',
  };
  const PLAN_STATUS_TEXT = {
    proposed: '待执行', active: '执行中', superseded: '已被新版本替代',
    completed: '已完成', rejected: '已拒绝',
  };
  const EVIDENCE_TEXT = { catalog: '目录证据', abstract: '摘要证据' };
  const TASK_TYPE_TEXT = {
    search_catalog: '目录检索', evaluate_papers: '论文评估', check_coverage: '覆盖检查',
    replan: 'Re-plan', synthesize_preliminary_report: '报告合成',
  };
  const ROLE_TEXT = {
    planner: '规划器', 'search-worker': '搜索 Worker', 'paper-evaluator': '论文评估器',
    'research-critic': '研究 Critic', synthesizer: '报告合成器',
  };
  const STOP_REASON_TEXT = {
    budget_exhausted: '预算已耗尽，停止新增节点。',
    no_new_evidence: '没有新增有效证据，停止补搜。',
    no_new_papers: '没有新增论文证据，停止补搜。',
    source_degraded: '来源降级，保留已有证据并收敛。',
    source_unavailable: '来源不可用，保留已有证据并收敛。',
  };
  const state = {
    document: null,
    conversationId: null,
    conversation: null,
    tasks: [],
    selectedTaskId: null,
    selectedTask: null,
    events: new Map(),
    selectedPapers: new Set(),
    selectedPaperCount: null,
    reportSelections: [],
    report: null,
    terminal: null,
    lastSeq: 0,
    eventSource: null,
    reconnectTimer: null,
    streamGeneration: 0,
    streamEnded: false,
    booted: false,
    loading: false,
    approvalInFlight: false,
    statusNotice: '',
  };

  function parseConversationId(location = root.location) {
    const pathname = String(location?.pathname || '');
    const match = pathname.match(/^\/c\/([^/?#]+)/);
    if (!match) return null;
    try { return decodeURIComponent(match[1]); } catch (_) { return match[1]; }
  }

  function byId(id) { return state.document?.getElementById(id) || null; }

  function text(value, fallback = '—') {
    if (value === null || value === undefined || value === '') return fallback;
    return String(value);
  }

  function setText(id, value, fallback = '') {
    const node = byId(id);
    if (node) node.textContent = value === null || value === undefined ? fallback : String(value);
    return node;
  }

  function statusLabel(status) { return STATUS_TEXT[status] || '未知状态'; }

  function planStatusLabel(status) { return PLAN_STATUS_TEXT[status] || '未知计划状态'; }

  function evidenceLabel(level) { return EVIDENCE_TEXT[level] || '未知证据等级'; }

  function safeList(value, limit = 20) {
    if (!Array.isArray(value)) return [];
    return [...new Set(value.filter((item) => ['string', 'number'].includes(typeof item) && String(item).trim()).map(String))].slice(0, limit);
  }

  function safePositiveInteger(value) {
    const number = Number(value);
    return Number.isInteger(number) && number > 0 ? number : null;
  }

  function safeCode(payload) {
    if (!payload || typeof payload !== 'object') return '';
    const value = payload.code || payload.error_code;
    return typeof value === 'string' && /^[A-Z][A-Z0-9_]{1,63}$/.test(value) ? value : '';
  }

  function eventStopReason(payload) {
    if (!payload || typeof payload !== 'object') return '';
    const code = safeCode(payload);
    if (code === 'MODEL_ESCALATED') return '';
    if (ERROR_TEXT[code]) return ERROR_TEXT[code];
    const reason = typeof payload.stop_reason === 'string' ? payload.stop_reason : '';
    if (STOP_REASON_TEXT[reason]) return STOP_REASON_TEXT[reason];
    return '';
  }

  function errorFromResponse(response, data) {
    const body = data && typeof data === 'object' ? data : {};
    const error = body.error || body.detail || body;
    const code = typeof error === 'object' ? error.code : body.code;
    const message = typeof error === 'object' ? error.message : (typeof error === 'string' ? error : body.message);
    const result = new Error(message || ERROR_TEXT[code] || '研究任务请求失败。');
    result.code = code || '';
    result.status = response.status;
    return result;
  }

  async function requestJson(url, options = {}) {
    let response;
    try {
      response = await root.fetch(url, options);
    } catch (error) {
      const network = new Error('无法连接本地服务，请确认后端已启动。');
      network.code = 'NETWORK_ERROR';
      network.cause = error;
      throw network;
    }
    let data = null;
    try { data = await response.json(); } catch (_) { data = null; }
    if (!response.ok) throw errorFromResponse(response, data);
    return data;
  }

  function userError(error, fallback = '研究任务请求失败。') {
    if (!error) return fallback;
    if (error.code && ERROR_TEXT[error.code]) return ERROR_TEXT[error.code];
    if (error.code && error.code !== 'NETWORK_ERROR') return '研究任务暂时不可用，错误码未知，请稍后重试。';
    return error.message || fallback;
  }

  function showView() {
    const doc = state.document;
    doc.querySelectorAll('.main-area').forEach((section) => { section.hidden = section.id !== 'research-view'; });
    doc.querySelectorAll('.nav-item').forEach((item) => {
      const current = item.dataset.view === 'research';
      item.classList.toggle('active', current);
      item.setAttribute('aria-current', current ? 'page' : 'false');
    });
    const hash = '#research-view';
    if (root.location.hash !== hash) root.history.replaceState({}, '', `${root.location.pathname}${root.location.search}${hash}`);
  }

  function closeResearchView() {
    closeStream();
    const view = byId('research-view');
    if (view) view.hidden = true;
    const nav = state.document?.querySelector('[data-view="research"]');
    if (nav) {
      nav.classList.remove('active');
      nav.setAttribute('aria-current', 'false');
    }
  }

  function closeStream({ keepTimer = false } = {}) {
    state.streamGeneration += 1;
    if (state.eventSource) { state.eventSource.close(); state.eventSource = null; }
    if (!keepTimer && state.reconnectTimer) { root.clearTimeout(state.reconnectTimer); state.reconnectTimer = null; }
  }

  function conversationFromUrl() {
    state.conversationId = parseConversationId();
    const id = state.conversationId;
    if (!id) {
      setText('research-current-conversation', '尚未打开会话。请先打开一个会话，再创建研究任务。');
      setText('research-create-status', '请从会话 URL（/c/{conversation_id}）进入，或先打开一个会话。');
      return Promise.resolve(null);
    }
    setText('research-current-conversation', `当前会话：${id}`);
    return requestJson(`/api/conversations/${encodeURIComponent(id)}`).then((conversation) => {
      state.conversation = conversation;
      const title = conversation.title || id;
      setText('research-current-conversation', `当前会话：${title} · ${id}`);
      setText('research-create-status', '研究任务会绑定当前会话，普通聊天模式不会自动创建长任务。');
      return conversation;
    }).catch((error) => {
      state.conversation = null;
      setText('research-current-conversation', `当前会话不可用：${userError(error, '请先打开一个有效会话。')}`);
      setText('research-create-status', '无法读取当前会话。请从左侧会话卡片重新打开后再试。');
      return null;
    });
  }

  function clearNode(node) { if (node) node.replaceChildren(); }

  function createTaskCard(task) {
    const doc = state.document;
    const item = doc.createElement('div');
    item.setAttribute('role', 'listitem');
    const button = doc.createElement('button');
    button.type = 'button';
    button.className = 'research-task-card';
    button.dataset.taskId = text(task.research_task_id, '');
    button.classList.toggle('is-selected', task.research_task_id === state.selectedTaskId);
    const title = doc.createElement('span');
    title.className = 'research-task-card-title';
    title.textContent = text(task.goal_excerpt, '未命名研究任务');
    const badge = doc.createElement('span');
    badge.className = 'research-badge';
    badge.dataset.status = text(task.status, '');
    badge.textContent = statusLabel(task.status);
    const meta = doc.createElement('span');
    meta.className = 'research-task-card-meta';
    meta.textContent = `${text(task.research_task_id, '无 ID')} · 计划 v${text(task.current_plan_version, '—')} · ${text(task.quality_profile, 'balanced')}`;
    button.append(title, badge, meta);
    button.addEventListener('click', () => { selectTask(task.research_task_id); });
    item.appendChild(button);
    return item;
  }

  function renderTaskList() {
    const list = byId('research-task-list');
    const empty = byId('research-list-empty');
    if (!list) return;
    clearNode(list);
    const tasks = [...state.tasks].sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')));
    tasks.forEach((task) => list.appendChild(createTaskCard(task)));
    if (empty) empty.hidden = tasks.length > 0;
    setText('research-list-status', tasks.length ? `共 ${tasks.length} 个任务` : '当前会话或工作区暂无任务。');
  }

  async function loadTasks() {
    setText('research-list-status', '正在加载任务…');
    try {
      const data = await requestJson('/api/research-tasks?limit=100');
      state.tasks = Array.isArray(data?.research_tasks) ? data.research_tasks : [];
      renderTaskList();
      return state.tasks;
    } catch (error) {
      state.tasks = [];
      renderTaskList();
      setText('research-list-status', userError(error, '任务列表加载失败。'));
      return [];
    }
  }

  function setDetailVisibility(visible) {
    const empty = byId('research-detail-empty');
    if (empty) empty.hidden = visible;
    ['research-plan-section', 'research-timeline-section', 'research-selection-section'].forEach((id) => { const node = byId(id); if (node && !visible) node.hidden = true; });
  }

  function renderTaskHeader(task) {
    const status = byId('research-detail-status');
    if (status) { status.dataset.status = text(task?.status, ''); status.textContent = statusLabel(task?.status); }
    setText('research-detail-title', task?.goal_excerpt || '选择一个任务');
    setText('research-detail-meta', task ? `${text(task.research_task_id)} · 会话 ${text(task.conversation_id)} · 更新于 ${text(task.updated_at || task.created_at)}` : '刷新后会先恢复任务详情，再连接实时事件。');
    const approve = byId('research-approve-button');
    const waitingApproval = task?.status === 'waiting_approval';
    if (approve) {
      approve.hidden = !waitingApproval;
      approve.disabled = !waitingApproval || state.approvalInFlight;
      approve.textContent = state.approvalInFlight ? '正在批准…' : '批准计划并开始执行';
      approve.setAttribute('aria-busy', state.approvalInFlight ? 'true' : 'false');
    }
    const cancel = byId('research-cancel-button');
    if (cancel) cancel.disabled = !task || TERMINAL_STATUSES.has(task.status);
  }

  function renderPlan(plan) {
    const section = byId('research-plan-section');
    if (!section) return;
    const planEvents = [...state.events.values()].filter((event) => event.type === 'plan').sort((a, b) => a.seq - b.seq);
    const latestEventVersion = planEvents.reduce((max, event) => Math.max(max, safePositiveInteger(event.payload?.plan_version) || 0), 0);
    section.hidden = !plan && planEvents.length === 0;
    if (plan) {
      const currentVersion = Math.max(safePositiveInteger(plan.plan_version) || 0, latestEventVersion);
      setText('research-plan-meta', `当前计划 v${text(currentVersion)} · ${planStatusLabel(plan.status)} · Planner ${text(plan.planner_model, '未指定')}`);
      setText('research-plan-rationale', text(plan.rationale_summary, '暂无计划理由。'));
    } else {
      setText('research-plan-meta', '等待计划摘要…');
      setText('research-plan-rationale', '已收到计划事件，当前详情接口尚未返回计划摘要。');
    }
    const facets = byId('research-plan-facets');
    clearNode(facets);
    const values = Array.isArray(plan?.facets) ? plan.facets : [];
    values.forEach((facet) => { const li = state.document.createElement('li'); li.textContent = selectionFacetText(facet); facets.appendChild(li); });
    if (!values.length) { const li = state.document.createElement('li'); li.textContent = '暂无 facets'; facets.appendChild(li); }

    let history = byId('research-plan-history');
    let historyTitle = byId('research-plan-history-title');
    if (!history) {
      historyTitle = state.document.createElement('p');
      historyTitle.id = 'research-plan-history-title';
      historyTitle.className = 'research-plan-label';
      historyTitle.textContent = '计划版本历史';
      section.appendChild(historyTitle);
      history = state.document.createElement('ol');
      history.id = 'research-plan-history';
      history.className = 'research-timeline';
      section.appendChild(history);
    }
    if (historyTitle) historyTitle.hidden = planEvents.length === 0;
    clearNode(history);
    planEvents.forEach((event) => {
      const payload = event.payload || {};
      const version = safePositiveInteger(payload.plan_version);
      const item = state.document.createElement('li');
      item.className = 'research-event';
      const title = state.document.createElement('div');
      title.className = 'research-event-title';
      title.textContent = version && version > 1 ? `Re-plan · 计划 v${version}` : `首轮计划 · v${version || '—'}`;
      const meta = state.document.createElement('div');
      meta.className = 'research-event-meta';
      meta.textContent = `${text(event.timestamp, '事件时间未知')} · ${payload.status ? planStatusLabel(payload.status) : '计划事件已记录'}`;
      const summary = state.document.createElement('p');
      summary.className = 'research-event-summary';
      summary.textContent = payload.rationale_summary || (Array.isArray(payload.facets) ? `覆盖方向：${safeList(payload.facets).join('、') || '未提供'}` : '计划版本已记录。');
      item.append(title, meta, summary);
      history.appendChild(item);
    });
  }

  function payloadText(payload) {
    if (!payload || typeof payload !== 'object') return '收到安全事件摘要';
    const parts = [];
    if (STATUS_TEXT[payload.status]) parts.push(`状态：${statusLabel(payload.status)}`);
    const code = safeCode(payload);
    if (code) parts.push(eventStopReason(payload) || `事件码：${code}`);
    const planVersion = safePositiveInteger(payload.plan_version);
    if (planVersion) parts.push(`计划 v${planVersion}`);
    const round = safePositiveInteger(payload.round);
    if (round) parts.push(`第 ${round} 轮`);
    if (TASK_TYPE_TEXT[payload.task_type]) parts.push(`节点：${TASK_TYPE_TEXT[payload.task_type]}`);
    if (ROLE_TEXT[payload.role]) parts.push(`角色：${ROLE_TEXT[payload.role]}`);
    if (typeof payload.worker_slot === 'string' && payload.worker_slot) parts.push(`Worker：${payload.worker_slot}`);
    if (payload.model_tier === 'fast' || payload.model_tier === 'strong') parts.push(`档位：${payload.model_tier}`);
    if (typeof payload.resolved_model === 'string' && payload.resolved_model) parts.push(`模型：${payload.resolved_model}`);
    if (payload.from_tier === 'fast' && payload.to_tier === 'strong') parts.push('路由：fast → strong');
    if (Number.isFinite(Number(payload.selected_count))) parts.push(`已选：${Number(payload.selected_count)}`);
    if (Number.isFinite(Number(payload.candidate_count))) parts.push(`候选：${Number(payload.candidate_count)}`);
    const gaps = safeList(payload.gaps);
    if (gaps.length) parts.push(`覆盖缺口：${gaps.join('、')}`);
    const failedSources = safeList(payload.failed_sources).length || safeList(payload.degraded_sources).length;
    if (failedSources) parts.push(`受影响来源：${failedSources} 个`);
    if (EVIDENCE_TEXT[payload.evidence_level]) parts.push(`证据：${evidenceLabel(payload.evidence_level)}`);
    if (typeof payload.reason === 'string' && payload.reason.length <= 180) parts.push(`说明：${payload.reason}`);
    return parts.join(' · ') || '收到安全事件摘要';
  }

  function eventTitle(type) {
    return { task: '任务状态', plan: '研究计划', worker: 'Worker', model: '模型', coverage: '覆盖度', report: '报告', terminal: '任务终态' }[type] || '研究事件';
  }

  function renderTimeline() {
    const list = byId('research-timeline');
    const section = byId('research-timeline-section');
    if (!list || !section) return;
    clearNode(list);
    const events = [...state.events.values()].sort((a, b) => a.seq - b.seq);
    section.hidden = events.length === 0;
    events.forEach((event) => {
      const item = state.document.createElement('li'); item.className = 'research-event';
      const title = state.document.createElement('div'); title.className = 'research-event-title'; title.textContent = `#${event.seq} · ${eventTitle(event.type)}`;
      const meta = state.document.createElement('div'); meta.className = 'research-event-meta'; meta.textContent = text(event.timestamp || event.created_at, '事件时间未知');
      const summary = state.document.createElement('p'); summary.className = 'research-event-summary'; summary.textContent = payloadText(event.payload);
      item.append(title, meta, summary); list.appendChild(item);
    });
    const hasRealTerminal = events.some((event) => event.type === 'terminal');
    if (state.terminal && state.terminal.synthetic && !hasRealTerminal) {
      const item = state.document.createElement('li'); item.className = 'research-event';
      const title = state.document.createElement('div'); title.className = 'research-event-title'; title.textContent = '任务终态 · SSE 收尾';
      const summary = state.document.createElement('p'); summary.className = 'research-event-summary'; summary.textContent = payloadText(state.terminal.payload);
      item.append(title, summary); list.appendChild(item);
    }
  }

  function renderSelection() {
    const section = byId('research-selection-section');
    const list = byId('research-selection-list');
    if (!section || !list) return;
    clearNode(list);
    const values = [...state.selectedPapers];
    const reportValues = Array.isArray(state.reportSelections) ? state.reportSelections : [];
    section.hidden = values.length === 0 && state.selectedPaperCount === null && reportValues.length === 0;
    reportValues.forEach((selection) => {
      if (!selection || typeof selection !== 'object') return;
      const item = state.document.createElement('li');
      const paperId = state.document.createElement('strong');
      paperId.textContent = `目录论文：${text(selection.catalog_paper_id, '未知 ID')}`;
      const meta = state.document.createElement('span');
      meta.textContent = `相关性：${text(selection.relevance)} · ${evidenceLabel(selection.evidence_level)}`;
      const facets = state.document.createElement('span');
      facets.textContent = `facets：${selectionFacetText(selection.facets)}`;
      item.append(paperId, meta, facets);
      list.appendChild(item);
    });
    if (state.selectedPaperCount !== null) {
      const count = state.document.createElement('li'); count.textContent = `已选 ${state.selectedPaperCount} 篇论文（目录 ID 仅在安全事件摘要中提供）`; list.appendChild(count);
    }
    values.filter((paperId) => !reportValues.some((selection) => selection?.catalog_paper_id === paperId)).forEach((paperId) => {
      const item = state.document.createElement('li'); item.textContent = `目录论文：${paperId} · 证据等级待报告确认`; list.appendChild(item);
    });
  }

  function selectionFacetText(value) {
    const values = Array.isArray(value) ? value : value == null ? [] : [value];
    return values.map((facet) => {
      if (facet === null || facet === undefined || facet === '') return '';
      if (typeof facet !== 'object') return String(facet);
      return Object.entries(facet)
        .filter(([key, item]) => !/(title|abstract)/i.test(key) && ['string', 'number', 'boolean'].includes(typeof item))
        .map(([key, item]) => `${key}: ${String(item)}`)
        .join(', ');
    }).filter(Boolean).join('、') || '—';
  }

  function renderSummary() {
    const list = byId('research-summary-list');
    clearNode(list);
    const events = [...state.events.values()];
    const workers = events.filter((event) => event.type === 'worker');
    const coverage = [...events].reverse().find((event) => event.type === 'coverage');
    const plans = events.filter((event) => event.type === 'plan');
    const replans = plans.filter((event) => safePositiveInteger(event.payload?.plan_version) > 1 || event.payload?.task_type === 'replan');
    const terminalPayload = state.terminal?.payload || {};
    const terminalStatus = STATUS_TEXT[terminalPayload.status] ? terminalPayload.status : state.selectedTask?.status;
    const gaps = safeList(coverage?.payload?.gaps || terminalPayload.gaps);
    const modelEvents = events.filter((event) => event.type === 'model' || (event.payload?.from_tier === 'fast' && event.payload?.to_tier === 'strong'));
    const modelEscalations = modelEvents.filter((event) => safeCode(event.payload) === 'MODEL_ESCALATED' || (event.payload?.from_tier === 'fast' && event.payload?.to_tier === 'strong'));
    const issues = events.map((event) => eventStopReason(event.payload)).filter(Boolean);
    const terminalIssue = eventStopReason(terminalPayload);
    if (terminalIssue) issues.push(terminalIssue);
    const uniqueIssues = [...new Set(issues)];
    const evidenceLevels = [...new Set(
      (state.reportSelections || []).map((selection) => selection?.evidence_level).filter((level) => EVIDENCE_TEXT[level]),
    )];
    const entries = [
      ['Worker 事件', workers.length ? `${workers.length} 条` : '暂无'],
      ['最终状态', terminalStatus ? statusLabel(terminalStatus) : '等待终态事件'],
      ['计划版本', plans.length ? `${plans.length} 个版本 · 当前 v${text(state.selectedTask?.current_plan_version, '—')}` : '等待计划事件'],
      ['覆盖缺口', coverage ? (gaps.length ? gaps.join('、') : '当前未发现缺口') : '等待 coverage 事件'],
      ['Re-plan', replans.length ? `${replans.length} 次 · 最新 v${text(replans.at(-1).payload?.plan_version, '—')}` : '暂无 Re-plan 事件'],
      ['模型升级', modelEscalations.length ? `${modelEscalations.length} 次 · fast → strong` : (modelEvents.length ? payloadText(modelEvents.at(-1).payload) : '暂无升级事件')],
      ['停止/失败原因', uniqueIssues.length ? uniqueIssues.join(' · ') : '暂无已报告原因'],
      ['证据摘要', evidenceLevels.length ? evidenceLevels.map(evidenceLabel).join('、') : '报告选集尚未提供证据等级'],
    ];
    entries.forEach(([label, value]) => { const dt = state.document.createElement('dt'); dt.textContent = label; const dd = state.document.createElement('dd'); dd.textContent = value; const row = state.document.createElement('div'); row.className = 'research-summary-item'; row.append(dt, dd); list.appendChild(row); });
    setText('research-summary-text', state.statusNotice || (state.selectedTask ? `已接收 ${events.length} 条真实事件；断线重连游标为 ${state.lastSeq}。` : '等待任务事件。'));
  }

  function renderSafeMarkdown(node, markdown) {
    if (!node) return;
    node.replaceChildren();
    const source = text(markdown, '');
    const purify = root.DOMPurify;
    const marked = root.marked;
    const parse = typeof marked === 'function' ? marked : marked?.parse;
    if (!source) { node.hidden = true; return; }
    if (typeof purify?.sanitize !== 'function' || typeof parse !== 'function' || typeof root.DOMParser !== 'function') {
      node.textContent = source;
      node.hidden = false;
      return;
    }
    try {
      const html = parse(source, { async: false, breaks: true });
      const safeHtml = purify.sanitize(html, { USE_PROFILES: { html: true } });
      const parsed = new root.DOMParser().parseFromString(safeHtml, 'text/html');
      [...parsed.body.childNodes].forEach((child) => node.appendChild(node.ownerDocument.importNode(child, true)));
      node.hidden = false;
    } catch (_) {
      node.textContent = source;
      node.hidden = false;
    }
  }

  function limitationText(limitations) {
    if (!limitations || typeof limitations !== 'object' || Array.isArray(limitations)) return '';
    const lines = [];
    const missingFacets = safeList(limitations.missing_facets);
    if (missingFacets.length) lines.push(`覆盖缺口：${missingFacets.join('、')}`);
    const degradedSources = safeList(limitations.degraded_sources);
    const failedSources = safeList(limitations.failed_sources);
    if (degradedSources.length || failedSources.length) {
      lines.push(`来源限制：${degradedSources.length + failedSources.length} 个来源摘要标记为失败或降级`);
    }
    if (EVIDENCE_TEXT[limitations.evidence_level]) lines.push(`证据范围：${evidenceLabel(limitations.evidence_level)}`);
    if (limitations.budget_exhausted === true || limitations.stop_reason === 'budget_exhausted') {
      lines.push(STOP_REASON_TEXT.budget_exhausted);
    }
    if (limitations.no_new_evidence === true || limitations.stop_reason === 'no_new_evidence') {
      lines.push(STOP_REASON_TEXT.no_new_evidence);
    }
    const stopReason = STOP_REASON_TEXT[limitations.stop_reason];
    if (stopReason && !lines.includes(stopReason)) lines.push(stopReason);
    const known = new Set(['missing_facets', 'degraded_sources', 'failed_sources', 'evidence_level', 'budget_exhausted', 'no_new_evidence', 'stop_reason']);
    if (Object.keys(limitations).some((key) => !known.has(key))) lines.push('另有未展开的限制摘要。');
    return lines.join(' · ');
  }

  async function loadReport(taskId) {
    const stateNode = byId('research-report-state');
    const reportNode = byId('research-report-markdown');
    if (stateNode) stateNode.textContent = '正在读取报告…';
    if (reportNode) { reportNode.hidden = true; reportNode.replaceChildren(); }
    state.reportSelections = [];
    state.report = null;
    renderSelection();
    try {
      const report = await requestJson(`/api/research-tasks/${encodeURIComponent(taskId)}/report`);
      state.report = report;
      state.reportSelections = Array.isArray(report.selections) ? report.selections : [];
      renderSelection();
      renderSummary();
      renderSafeMarkdown(reportNode, report.markdown);
      if (stateNode) stateNode.textContent = `报告 v${text(report.plan_version)} · ${statusLabel(report.status)}`;
      const limitations = limitationText(report.limitations);
      setText('research-report-limitations', limitations ? `限制：${limitations}` : '');
      return report;
    } catch (error) {
      state.reportSelections = [];
      state.report = null;
      renderSelection();
      renderSummary();
      if (stateNode) stateNode.textContent = error.code === 'REPORT_NOT_READY' ? ERROR_TEXT.REPORT_NOT_READY : userError(error, '报告暂时不可用。');
      setText('research-report-limitations', '');
      return null;
    }
  }

  function applyEvent(event) {
    const payload = event.payload && typeof event.payload === 'object' ? event.payload : {};
    const paperIds = [...safeList(payload.selected_paper_ids), ...safeList(payload.catalog_paper_ids)];
    paperIds.forEach((paperId) => { if (paperId) state.selectedPapers.add(String(paperId)); });
    if (payload.selected_count !== undefined && Number.isFinite(Number(payload.selected_count))) state.selectedPaperCount = Number(payload.selected_count);
    if (event.type === 'plan') {
      const version = safePositiveInteger(payload.plan_version);
      if (version && state.selectedTask) {
        state.selectedTask = { ...state.selectedTask, current_plan_version: Math.max(Number(state.selectedTask.current_plan_version) || 0, version) };
        state.tasks = state.tasks.map((task) => task.research_task_id === state.selectedTaskId
          ? { ...task, current_plan_version: state.selectedTask.current_plan_version }
          : task);
      }
    }
    if (payload.status && STATUS_TEXT[payload.status] && state.selectedTask) {
      state.selectedTask = { ...state.selectedTask, status: payload.status };
      state.tasks = state.tasks.map((task) => task.research_task_id === state.selectedTaskId ? { ...task, status: payload.status } : task);
      renderTaskHeader(state.selectedTask);
    }
    if (event.type === 'terminal') {
      state.statusNotice = '';
      state.terminal = { payload, synthetic: !event.seq };
      state.streamEnded = true;
      if (payload.code || payload.error_code) setText('research-summary-text', eventStopReason(payload) || '任务已结束，但错误码未知。');
      if (payload.status === 'deleted') renderTaskHeader({ ...state.selectedTask, status: 'failed' });
      if (state.selectedTaskId) loadReport(state.selectedTaskId);
    }
    renderPlan(state.selectedTask?.plan);
    renderTimeline();
    renderSelection();
    renderSummary();
    renderTaskList();
  }

  function handleSseEvent(type, message, generation) {
    if (generation !== state.streamGeneration || !state.selectedTaskId) return;
    let data;
    try { data = JSON.parse(message.data || '{}'); } catch (_) { return; }
    const seq = Number(data.event_seq);
    if (type !== 'terminal' && (!Number.isInteger(seq) || seq <= 0)) return;
    if (Number.isInteger(seq) && seq > 0) {
      if (seq <= state.lastSeq) return;
      state.lastSeq = seq;
      state.events.set(seq, { seq, type, timestamp: data.timestamp, payload: data.payload || {} });
    }
    // Synthetic terminal frames deliberately have event_seq=null and no id; they never move lastSeq.
    applyEvent({ type, seq: Number.isInteger(seq) && seq > 0 ? seq : null, timestamp: data.timestamp, payload: data.payload || {} });
    if (type === 'terminal') closeStream();
  }

  function scheduleReconnect(generation) {
    if (generation !== state.streamGeneration || state.streamEnded || state.reconnectTimer || !state.selectedTaskId) return;
    state.reconnectTimer = root.setTimeout(() => {
      state.reconnectTimer = null;
      connectStream(generation);
    }, 1200);
  }

  function connectStream(generation = state.streamGeneration) {
    if (!state.selectedTaskId || generation !== state.streamGeneration || state.streamEnded) return;
    closeStream({ keepTimer: true });
    const currentGeneration = state.streamGeneration;
    const query = new URLSearchParams({ after_seq: String(state.lastSeq) });
    const url = `/api/research-tasks/${encodeURIComponent(state.selectedTaskId)}/events?${query}`;
    if (typeof root.EventSource !== 'function') { setText('research-summary-text', state.statusNotice || '当前浏览器不支持实时事件，将保留刷新恢复。'); return; }
    const source = new root.EventSource(url);
    state.eventSource = source;
    EVENT_TYPES.forEach((type) => source.addEventListener(type, (message) => handleSseEvent(type, message, currentGeneration)));
    source.onerror = () => {
      if (currentGeneration !== state.streamGeneration || state.streamEnded) return;
      source.close();
      if (state.eventSource === source) state.eventSource = null;
      setText('research-summary-text', `实时连接中断，将从 event_seq ${state.lastSeq} 之后重连。`);
      scheduleReconnect(currentGeneration);
    };
  }

  async function selectTask(taskId) {
    if (!taskId) return;
    closeStream();
    state.selectedTaskId = taskId;
    state.selectedTask = null;
    state.events = new Map();
    state.selectedPapers = new Set();
    state.selectedPaperCount = null;
    state.reportSelections = [];
    state.report = null;
    state.terminal = null;
    state.lastSeq = 0;
    state.streamEnded = false;
    state.approvalInFlight = false;
    state.statusNotice = '';
    renderTaskList();
    setDetailVisibility(false);
    renderTaskHeader(null);
    setText('research-summary-text', '正在恢复任务详情…');
    try {
      const task = await requestJson(`/api/research-tasks/${encodeURIComponent(taskId)}`);
      if (state.selectedTaskId !== taskId) return;
      state.selectedTask = task;
      renderTaskHeader(task);
      renderPlan(task.plan);
      setDetailVisibility(true);
      await loadReport(taskId);
      if (state.selectedTaskId !== taskId) return;
      connectStream();
    } catch (error) {
      setText('research-detail-empty', userError(error, '任务详情加载失败。'));
      setDetailVisibility(false);
      setText('research-summary-text', userError(error));
    }
  }

  async function refreshWorkspace() {
    await conversationFromUrl();
    const tasks = await loadTasks();
    const current = state.selectedTaskId && tasks.some((task) => task.research_task_id === state.selectedTaskId)
      ? state.selectedTaskId
      : tasks.find((task) => task.conversation_id === state.conversationId)?.research_task_id || null;
    if (current) await selectTask(current);
    else {
      closeStream(); state.selectedTaskId = null; state.selectedTask = null; state.events = new Map(); state.selectedPapers = new Set(); state.selectedPaperCount = null; state.reportSelections = []; state.lastSeq = 0; state.approvalInFlight = false; state.statusNotice = '';
      renderTaskHeader(null); setDetailVisibility(false); renderSummary();
      state.report = null; state.terminal = null;
      const report = byId('research-report-markdown'); if (report) { report.hidden = true; report.replaceChildren(); }
      setText('research-report-state', '任务完成后显示报告。');
      setText('research-report-limitations', '');
    }
  }

  async function createTask(event) {
    event.preventDefault();
    const goal = (byId('research-goal')?.value || '').trim();
    if (!state.conversationId) { setText('research-create-status', '请先打开一个会话；研究任务必须绑定会话。'); return; }
    if (!goal) { setText('research-create-status', '请填写研究目标。'); byId('research-goal')?.focus(); return; }
    const button = byId('research-create-button'); if (button) button.disabled = true;
    setText('research-create-status', '正在创建研究任务…');
    const payload = {
      goal,
      conversation_id: state.conversationId,
      quality_profile: byId('research-quality')?.value || 'balanced',
      target_paper_count: Number(byId('research-target-count')?.value || 12),
      language: byId('research-language')?.value || 'zh',
      review_plan_first: Boolean(byId('research-review-plan')?.checked),
    };
    try {
      const task = await requestJson('/api/research-tasks', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      state.tasks = [task, ...state.tasks.filter((item) => item.research_task_id !== task.research_task_id)];
      renderTaskList();
      setText('research-create-status', '研究任务已创建，正在连接事件流。');
      await selectTask(task.research_task_id);
    } catch (error) {
      setText('research-create-status', userError(error, '研究任务创建失败。'));
    } finally { if (button) button.disabled = false; }
  }

  async function cancelTask() {
    if (!state.selectedTaskId || !state.selectedTask || TERMINAL_STATUSES.has(state.selectedTask.status)) return;
    const button = byId('research-cancel-button'); if (button) button.disabled = true;
    setText('research-summary-text', '正在取消研究任务…');
    try {
      const result = await requestJson(`/api/research-tasks/${encodeURIComponent(state.selectedTaskId)}/cancel`, { method: 'POST' });
      state.selectedTask = { ...state.selectedTask, ...result };
      state.statusNotice = '';
      renderTaskHeader(state.selectedTask); renderTaskList();
      setText('research-summary-text', `任务已取消，收敛 ${text(result.cancelled_work_items, '0')} 个 WorkItem。`);
    } catch (error) {
      setText('research-summary-text', userError(error, '取消任务失败。'));
      if (button) button.disabled = false;
    }
  }

  async function approveTask() {
    if (!state.selectedTaskId || !state.selectedTask || state.selectedTask.status !== 'waiting_approval' || state.approvalInFlight) return;
    const taskId = state.selectedTaskId;
    const button = byId('research-approve-button');
    state.approvalInFlight = true;
    renderTaskHeader(state.selectedTask);
    setText('research-summary-text', '正在批准计划…');
    try {
      const result = await requestJson(`/api/research-tasks/${encodeURIComponent(taskId)}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'approve' }),
      });
      if (state.selectedTaskId !== taskId || !state.selectedTask || state.selectedTask.research_task_id !== taskId) return;
      state.selectedTask = { ...state.selectedTask, ...result };
      state.tasks = state.tasks.map((task) => task.research_task_id === taskId ? { ...task, ...result } : task);
      state.statusNotice = '已批准，开始执行';
      renderTaskHeader(state.selectedTask);
      renderTaskList();
      renderSummary();
      if (state.streamEnded) {
        state.streamEnded = false;
        connectStream();
      } else if (!state.eventSource && !state.reconnectTimer) {
        connectStream();
      }
    } catch (error) {
      state.statusNotice = '';
      setText('research-summary-text', userError(error, '批准计划失败。'));
      if (button) button.disabled = false;
    } finally {
      state.approvalInFlight = false;
      if (state.selectedTask) renderTaskHeader(state.selectedTask);
    }
  }

  function openForConversation(conversationId) {
    if (!conversationId) return;
    root.history.replaceState({}, '', `/c/${encodeURIComponent(conversationId)}#research-view`);
    state.conversationId = conversationId;
    showView();
    conversationFromUrl().catch(() => {});
    refreshWorkspace();
  }

  function decorateConversationCards() {
    const doc = state.document;
    doc.querySelectorAll('.conversation-item[data-conversation-id]').forEach((row) => {
      if (row.querySelector('.research-conversation-action')) return;
      const conversationId = row.dataset.conversationId;
      if (!conversationId) return;
      const button = doc.createElement('button');
      button.type = 'button'; button.className = 'research-conversation-action'; button.textContent = '研究';
      button.title = '从此会话创建深度研究任务';
      button.setAttribute('aria-label', '从此会话创建深度研究任务');
      button.addEventListener('click', (event) => { event.preventDefault(); event.stopPropagation(); openForConversation(conversationId); });
      row.appendChild(button);
    });
  }

  function bindModeGuard() {
    const mode = byId('mode-select');
    const hint = byId('mode-hint');
    const form = byId('chat-form');
    const update = () => {
      if (!mode || !hint) return;
      if (mode.value === 'research') hint.textContent = '深度研究模式 · 请在工作台确认创建，不会直接发送普通聊天任务';
      else if (mode.value === 'developer') hint.textContent = 'Developer 模式 · 单次最多 20,000 字 · 显示调试信息';
      else hint.textContent = 'Normal 模式 · 单次最多 2,000 字';
    };
    mode?.addEventListener('change', () => { update(); root.setTimeout(update, 0); });
    form?.addEventListener('submit', (event) => {
      if (mode?.value !== 'research') return;
      event.preventDefault(); event.stopImmediatePropagation();
      const question = (byId('question')?.value || '').trim();
      if (question && byId('research-goal')) byId('research-goal').value = question;
      showView(); refreshWorkspace(); byId('research-goal')?.focus();
    }, true);
    update();
  }

  function bindNavigation() {
    const nav = state.document.querySelector('[data-view="research"]');
    nav?.addEventListener('click', (event) => { event.preventDefault(); event.stopImmediatePropagation(); showView(); refreshWorkspace(); }, true);
    nav?.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault(); event.stopImmediatePropagation(); showView(); refreshWorkspace();
    }, true);
    byId('research-refresh-button')?.addEventListener('click', refreshWorkspace);
    byId('research-create-form')?.addEventListener('submit', createTask);
    byId('research-approve-button')?.addEventListener('click', approveTask);
    byId('research-cancel-button')?.addEventListener('click', cancelTask);

    // app.js owns the other views and its private showView/openConversation functions.
    // Capture their DOM/history signals so its later handlers cannot leave this view visible.
    state.document.addEventListener('click', (event) => {
      if (event.target?.closest('#research-view, [data-view="research"]')) return;
      if (event.target?.closest('.nav-item[data-view], .new-chat')) closeResearchView();
    }, true);
    const history = root.history;
    if (history && !history.__researchTasksNavigationGuard) {
      ['pushState', 'replaceState'].forEach((method) => {
        const original = history[method];
        if (typeof original !== 'function') return;
        history[method] = function guardedHistoryMethod(...args) {
          const result = original.apply(this, args);
          if (root.location.hash !== '#research-view') closeResearchView();
          return result;
        };
      });
      history.__researchTasksNavigationGuard = true;
    }
    const syncHistoryView = () => {
      if (root.location.hash === '#research-view') showView();
      else closeResearchView();
    };
    root.addEventListener('popstate', syncHistoryView);
    root.addEventListener('hashchange', syncHistoryView);
  }

  function bindConversationObserver() {
    const observer = new root.MutationObserver(() => decorateConversationCards());
    ['conversation-list', 'project-list'].forEach((id) => { const node = byId(id); if (node) observer.observe(node, { childList: true, subtree: true }); });
    decorateConversationCards();
  }

  function boot(documentRef) {
    if (state.booted) return;
    state.document = documentRef; state.booted = true; state.conversationId = parseConversationId();
    if (!byId('research-view')) return;
    bindModeGuard(); bindNavigation(); bindConversationObserver();
    conversationFromUrl();
    loadTasks();
    if (root.location.hash === '#research-view') root.setTimeout(() => { showView(); refreshWorkspace(); }, 0);
  }

  return { boot, parseConversationId, statusLabel, userError, renderSafeMarkdown };
}));
