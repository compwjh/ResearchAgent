/* Spec034 Task09: Research Tab is a Session workspace; legacy task APIs remain
 * a read/debug compatibility seam only.  Creation and listing never bypass the
 * Session/Intake/Plan/Approval state machine. */
(function exposeResearchTasks(root, factory) {
  const api = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else if (root) root.ResearchTasks = api;
  if (root && root.document) api.boot(root.document);
}(typeof globalThis !== 'undefined' ? globalThis : this, function researchTasksFactory(root) {
  const sessionUI = root.ResearchSessionUI || (typeof module === 'object' && typeof require === 'function' ? require('./research-session-ui.js') : null);
  const TERMINAL_STATUSES = new Set(['partial', 'completed', 'failed', 'cancelled', 'interrupted']);
  const EVENT_TYPES = ['task', 'plan', 'worker', 'model', 'coverage', 'report', 'terminal', 'processing_step'];
  const NOTIFICATION_EVENT_TYPES = ['completed', 'partial', 'failed', 'waiting_approval', 'interrupted'];
  const ARTIFACT_TYPES = new Set(['markdown', 'html', 'citation_manifest']);
  const ARTIFACT_ROUTE = /^\/api\/research-sessions\/[A-Za-z0-9._~-]+\/artifacts\/[A-Za-z0-9._~-]+\/download$/;
  const NOTIFICATION_KINDS = new Set(NOTIFICATION_EVENT_TYPES);
  const NOTIFICATION_TEXT = {
    completed: '研究已完成', partial: '研究部分完成', failed: '研究失败',
    waiting_approval: '等待审批', interrupted: '研究已中断',
  };
  const STATUS_TEXT = {
    draft: '草稿', intake_pending: '等待补充研究参数', plan_generating: '生成计划中', plan_pending_approval: '等待计划审核',
    queued: '排队中', planning: '规划中', running: '执行中', paused: '已暂停', waiting_approval: '等待审批', recovery_required: '需要恢复',
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
  const EVIDENCE_TEXT = { catalog: '目录证据', abstract: '摘要证据', fulltext: '全文证据' };
  const ACQUISITION_STATUS_TEXT = {
    existing: '已有知识库', pending: '待导入', queued: '排队中', downloading: '下载中', processing: '处理中',
    indexing: '索引中', completed: '已完成', partial_success: '部分完成', waiting_login: '等待登录',
    needs_login: '需要登录', failed: '失败', unavailable: '来源不可用', cancelled: '已取消', interrupted: '已中断',
  };
  const ACQUISITION_ERROR_TEXT = {
    DOWNLOAD_TIMEOUT: '下载超时，可重试。', IMPORT_INTERRUPTED: '导入被中断，可重试。',
    SEARCH_EXPIRED: '搜索快照已过期，请刷新候选。', INVALID_SEARCH_SNAPSHOT: '搜索候选快照无效。',
  };
  const TASK_TYPE_TEXT = {
    search_catalog: '目录检索', evaluate_papers: '论文评估', check_coverage: '覆盖检查',
    replan: 'Re-plan', synthesize_preliminary_report: '报告合成',
  };
  const ROLE_TEXT = {
    planner: '规划器', 'search-worker': '搜索 Worker', 'paper-evaluator': '论文评估器',
    'research-critic': '研究 Critic', synthesizer: '报告合成器',
  };
  const SESSION_PLAN_FIELDS = [
    ['objective', '目标'], ['scope', '范围'], ['work_items', '研究方向'],
    ['capabilities', '来源与能力'], ['budget', '预算'],
    ['report_structure', '报告结构'], ['safety_summary', '降级策略'],
  ];
  const SESSION_APPROVAL_LABELS = { plan: '计划审批', capability_override: '能力审批', resource_extension: '资源扩容审批' };
  const SESSION_COMMAND_LABELS = {
    approve_plan: '批准计划', revise_plan: '修改计划', cancel_research: '取消研究',
    approve_capability: '批准能力', approve_resource_extension: '批准资源扩容', decline_request: '拒绝请求',
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
    sessions: [],
    selectedTaskId: null,
    selectedSessionId: null,
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
    processingTree: null,
    processingTreeTaskId: null,
    notifications: new Map(),
    notificationLastSeq: 0,
    notificationEventSource: null,
    notificationReconnectTimer: null,
    notificationLoading: false,
    notificationSyncError: '',
    createIdempotencyKey: null,
    triggerMessageId: null,
    taskActionInFlight: false,
    acquisition: {
      preview: [], status: null, links: [], items: [], events: [], evidence: [], selectionVersion: null,
      selectedIds: new Set(), searchId: null, loading: false, confirming: false,
      retrying: new Set(), pollTimer: null, generation: 0,
    },
  };

  const TASK_ACTION_PATHS = Object.freeze({
    pause: 'pause', resume: 'resume', approve: 'feedback', cancel: 'cancel', recover: 'recover',
  });
  const TASK_ACTION_LABELS = Object.freeze({ pause: '暂停研究', resume: '继续研究', approve: '批准计划', cancel: '取消当前任务', recover: '检查并恢复' });
  const TASK_ACTION_CONFIRM_LABELS = Object.freeze({ pause: '再次点击确认暂停', resume: '再次点击确认继续', approve: '再次点击确认批准', cancel: '再次点击确认取消', recover: '再次点击确认恢复' });
  const TASK_ACTION_STATUSES = Object.freeze({
    pause: new Set(['planning', 'running', 'waiting_approval']),
    resume: new Set(['paused']),
    approve: new Set(['waiting_approval']),
    cancel: new Set(['queued', 'planning', 'running', 'paused', 'waiting_approval']),
    recover: new Set(['interrupted', 'recovery_required']),
  });

  function safeArtifactUrl(value) {
    const url = typeof value === 'string' ? value.trim() : '';
    return ARTIFACT_ROUTE.test(url) ? url : '';
  }

  function artifactActionUrl(artifactType, value) {
    const safeUrl = safeArtifactUrl(value);
    if (!safeUrl) return '';
    if (artifactType === 'html') return `${safeUrl}?mode=inline`;
    if (artifactType === 'markdown' || artifactType === 'citation_manifest') return safeUrl;
    return '';
  }

  function normalizeArtifact(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
    const artifactId = typeof value.artifact_id === 'string' && /^[A-Za-z0-9._~-]{1,240}$/.test(value.artifact_id)
      ? value.artifact_id : '';
    const artifactType = typeof value.artifact_type === 'string' && ARTIFACT_TYPES.has(value.artifact_type)
      ? value.artifact_type : '';
    if (!artifactId || !artifactType) return null;
    const downloadUrl = value.download_url == null ? '' : safeArtifactUrl(value.download_url);
    if (value.download_url != null && !downloadUrl) return null;
    return {
      artifact_id: artifactId,
      artifact_type: artifactType,
      report_version: safePositiveInteger(value.report_version),
      content_hash: typeof value.content_hash === 'string' ? value.content_hash.slice(0, 128) : '',
      download_url: downloadUrl,
      created_at: typeof value.created_at === 'string' ? value.created_at.slice(0, 80) : '',
    };
  }

  function normalizeNotification(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
    const notificationId = typeof value.notification_id === 'string' && /^[A-Za-z0-9._~-]{1,240}$/.test(value.notification_id)
      ? value.notification_id : '';
    const eventSeq = Number(value.event_seq);
    const kind = typeof value.notification_kind === 'string' ? value.notification_kind : '';
    if (kind === 'heartbeat') return null; // SSE heartbeat comments are keep-alive only, never a list item.
    if (!notificationId || !Number.isInteger(eventSeq) || eventSeq <= 0 || !NOTIFICATION_KINDS.has(kind)) return null;
    if (value.status !== 'read' && value.status !== 'unread') return null;
    const status = value.status;
    const payload = value.payload && typeof value.payload === 'object' && !Array.isArray(value.payload) ? value.payload : {};
    return {
      notification_id: notificationId,
      research_session_id: typeof value.research_session_id === 'string' ? value.research_session_id.slice(0, 240) : '',
      research_task_id: typeof value.research_task_id === 'string' ? value.research_task_id.slice(0, 240) : '',
      notification_kind: kind,
      status,
      subject_version: safePositiveInteger(value.subject_version),
      event_seq: eventSeq,
      payload,
      created_at: typeof value.created_at === 'string' ? value.created_at.slice(0, 80) : '',
      read_at: typeof value.read_at === 'string' ? value.read_at.slice(0, 80) : '',
    };
  }

  function mergeNotifications(values) {
    const byId = new Map();
    const bySeq = new Map();
    (Array.isArray(values) ? values : []).forEach((value) => {
      const item = normalizeNotification(value);
      if (!item || bySeq.has(item.event_seq)) return;
      if (byId.has(item.notification_id)) return;
      byId.set(item.notification_id, item); bySeq.set(item.event_seq, item.notification_id);
    });
    return [...byId.values()].sort((a, b) => a.event_seq - b.event_seq);
  }

  function notificationKindLabel(kind) { return NOTIFICATION_TEXT[kind] || ''; }

  function notificationValidationError(value, kindHint = '') {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return '通知数据格式无效';
    const kind = value.notification_kind || kindHint;
    if (!NOTIFICATION_KINDS.has(kind)) return '通知类型未知，已丢弃';
    if (value.status !== 'read' && value.status !== 'unread') return '通知已读状态无效，已丢弃';
    if (!Number.isInteger(Number(value.event_seq)) || Number(value.event_seq) <= 0) return '通知游标无效，已丢弃';
    if (typeof value.notification_id !== 'string' || !value.notification_id) return '通知 ID 无效，已丢弃';
    return '';
  }

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

  function notificationPayloadText(item) {
    const payload = item?.payload && typeof item.payload === 'object' ? item.payload : {};
    const summary = [payload.title, payload.summary, payload.message].find((value) => typeof value === 'string' && value.trim());
    const version = safePositiveInteger(payload.report_version || item?.subject_version);
    const retryAttempt = safePositiveInteger(payload.retry_attempt);
    const retryText = item?.notification_kind === 'failed' && (payload.retryable === true || retryAttempt)
      ? `研究失败，可重试${retryAttempt ? `（第 ${retryAttempt} 次）` : ''}` : '';
    return `${retryText || summary || notificationKindLabel(item?.notification_kind)}${version ? ` · 报告 v${version}` : ''}`;
  }

  function setNotificationSyncError(reason) {
    state.notificationSyncError = reason || '通知同步失败';
    setText('research-notifications-status', `通知同步失败：${state.notificationSyncError}`);
  }

  function renderNotifications() {
    const list = byId('research-notifications-list');
    const empty = byId('research-notifications-empty');
    const status = byId('research-notifications-status');
    const unread = [...state.notifications.values()].filter((item) => item.status === 'unread').length;
    const count = byId('research-notifications-unread');
    if (count) { count.textContent = String(unread); count.hidden = unread === 0; }
    if (!list) return;
    clearNode(list);
    const items = [...state.notifications.values()].sort((a, b) => b.event_seq - a.event_seq);
    items.forEach((notification) => {
      const item = state.document.createElement('li');
      item.className = 'research-notification-item';
      item.dataset.status = notification.status;
      item.dataset.notificationKind = notification.notification_kind;
      const button = state.document.createElement('button');
      button.type = 'button';
      button.className = 'research-notification-button';
      button.dataset.notificationId = notification.notification_id;
      button.setAttribute('aria-label', `${notificationKindLabel(notification.notification_kind)}：${notificationPayloadText(notification)}`);
      const title = state.document.createElement('strong');
      title.className = 'research-notification-title';
      title.textContent = notificationKindLabel(notification.notification_kind);
      const summary = state.document.createElement('span');
      summary.className = 'research-notification-summary';
      summary.textContent = notificationPayloadText(notification);
      const meta = state.document.createElement('span');
      meta.className = 'research-notification-meta';
      meta.textContent = `#${notification.event_seq}${notification.created_at ? ` · ${notification.created_at}` : ''}${notification.status === 'read' ? ' · 已读' : ' · 未读'}`;
      button.append(title, summary, meta);
      button.addEventListener('click', () => openNotification(notification));
      item.appendChild(button); list.appendChild(item);
    });
    if (empty) empty.hidden = items.length > 0;
    if (status && !state.notificationLoading && !state.notificationSyncError) status.textContent = items.length ? `共 ${items.length} 条通知` : '暂无研究通知。';
  }

  function closeNotificationStream({ keepTimer = false } = {}) {
    if (state.notificationEventSource) { state.notificationEventSource.close(); state.notificationEventSource = null; }
    if (!keepTimer && state.notificationReconnectTimer) {
      root.clearTimeout(state.notificationReconnectTimer); state.notificationReconnectTimer = null;
    }
  }

  function applyNotification(value, kindHint = '') {
    const raw = { ...(value || {}), notification_kind: value?.notification_kind || kindHint };
    const validationError = notificationValidationError(raw, kindHint);
    if (validationError) { setNotificationSyncError(validationError); return false; }
    const item = normalizeNotification(raw);
    if (!item || item.event_seq <= state.notificationLastSeq) return false;
    state.notificationLastSeq = item.event_seq;
    const existing = state.notifications.get(item.notification_id);
    if (!existing || item.event_seq >= existing.event_seq) state.notifications.set(item.notification_id, item);
    renderNotifications();
    return true;
  }

  async function markNotificationRead(notification) {
    if (!notification || notification.status === 'read') return notification;
    try {
      const updated = await requestJson(`/api/research-notifications/${encodeURIComponent(notification.notification_id)}/read`, { method: 'POST' });
      const validationError = notificationValidationError({ ...notification, ...updated, payload: updated?.payload || notification.payload });
      if (validationError) { setNotificationSyncError(validationError); return notification; }
      const normalized = normalizeNotification({ ...notification, ...updated, payload: updated?.payload || notification.payload });
      if (normalized) state.notifications.set(normalized.notification_id, normalized);
      renderNotifications();
      return normalized || notification;
    } catch (_) {
      // A concurrent read is harmless; leave the durable unread state visible on an actual failure.
      return notification;
    }
  }

  async function openNotification(notification) {
    const item = await markNotificationRead(notification);
    const payload = item?.payload && typeof item.payload === 'object' ? item.payload : {};
    let conversationId = typeof payload.conversation_id === 'string' ? payload.conversation_id : '';
    const taskId = item?.research_task_id || (typeof payload.research_task_id === 'string' ? payload.research_task_id : '');
    const sessionId = item?.research_session_id || (typeof payload.research_session_id === 'string' ? payload.research_session_id : '');
    if (!conversationId && sessionId) {
      try {
        const session = await requestJson(`/api/research-sessions/${encodeURIComponent(sessionId)}`);
        conversationId = typeof session?.conversation_id === 'string' ? session.conversation_id : '';
      } catch (_) { /* keep the notification visible if its target was removed */ }
    }
    if (conversationId && taskId) {
      openForConversation(conversationId);
      root.setTimeout(() => { if (state.selectedTaskId !== taskId) selectTask(taskId); }, 0);
      return;
    }
    if (conversationId && typeof root.openConversation === 'function') {
      root.openConversation(conversationId);
      const messageId = typeof payload.message_id === 'string' ? payload.message_id : '';
      if (messageId) root.setTimeout(() => focusConversationMessage(messageId), 500);
      return;
    }
    if (taskId) {
      showView();
      if (state.tasks.some((task) => task.research_task_id === taskId)) selectTask(taskId);
      else refreshWorkspace().then(() => selectTask(taskId));
    }
  }

  function focusConversationMessage(messageId) {
    if (!messageId || !state.document) return;
    const message = state.document.querySelector?.(`.message[data-message-id="${String(messageId).replace(/[^A-Za-z0-9._~-]/g, '')}"]`);
    if (!message) return;
    message.scrollIntoView?.({ block: 'center', behavior: 'smooth' });
    message.setAttribute('tabindex', '-1'); message.focus?.({ preventScroll: true });
  }

  async function loadNotifications({ reset = false } = {}) {
    if (state.notificationLoading) return;
    state.notificationLoading = true;
    if (reset) closeNotificationStream();
    if (reset) state.notificationSyncError = '';
    setText('research-notifications-status', '正在加载研究通知…');
    try {
      const after = reset ? 0 : state.notificationLastSeq;
      const data = await requestJson(`/api/research-notifications?after_seq=${after}&limit=100`);
      const values = Array.isArray(data?.notifications) ? data.notifications : [];
      if (reset) { state.notifications = new Map(); state.notificationLastSeq = 0; }
      values.forEach((value) => {
        const validationError = notificationValidationError(value);
        if (validationError) { setNotificationSyncError(validationError); return; }
        const item = normalizeNotification(value);
        if (!item) return;
        const existing = state.notifications.get(item.notification_id);
        if (!existing || item.event_seq >= existing.event_seq) state.notifications.set(item.notification_id, item);
        state.notificationLastSeq = Math.max(state.notificationLastSeq, item.event_seq);
      });
      renderNotifications();
    } catch (error) {
      setText('research-notifications-status', userError(error, '研究通知加载失败。'));
    } finally { state.notificationLoading = false; renderNotifications(); if (!state.notificationEventSource) connectNotificationStream(); }
  }

  function scheduleNotificationReconnect() {
    if (state.notificationReconnectTimer) return;
    state.notificationReconnectTimer = root.setTimeout(() => {
      state.notificationReconnectTimer = null; connectNotificationStream();
    }, 1500);
  }

  function connectNotificationStream() {
    if (typeof root.EventSource !== 'function') return;
    closeNotificationStream({ keepTimer: true });
    // EventSource automatically sends Last-Event-ID; after_seq is also explicit for
    // browsers/proxies that do not preserve the header across a fresh connection.
    const url = `/api/research-notifications/events?after_seq=${state.notificationLastSeq}`;
    const source = new root.EventSource(url);
    state.notificationEventSource = source;
    NOTIFICATION_EVENT_TYPES.forEach((kind) => source.addEventListener(kind, (message) => {
      let value; try { value = JSON.parse(message.data || '{}'); } catch (_) { return; }
      applyNotification(value, kind);
    }));
    source.onerror = () => {
      source.close(); if (state.notificationEventSource === source) state.notificationEventSource = null;
      setText('research-notifications-status', `通知连接中断，将从 event_seq ${state.notificationLastSeq} 之后重连。`);
      scheduleNotificationReconnect();
    };
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
      setText('research-current-conversation', '将创建新的研究会话；若当前已打开会话则自动继承其项目。');
      setText('research-create-status', '填写研究目标后，系统会通过统一 Session/Intake/Plan/Approval 流程创建并打开会话。');
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

  function sessionTaskProjection(session) {
    return sessionUI?.projectSession?.(session) || null;
  }

  function sessionDurationText(item) {
    if (sessionUI?.durationText) return sessionUI.durationText(item);
    const duration = Number(item?.duration_ms);
    if (Number.isFinite(duration) && duration >= 0) return `${(duration / 1000).toFixed(duration >= 10000 ? 0 : 1)} 秒`;
    const start = Date.parse(item?.started_at || item?.created_at || '');
    const end = Date.parse(item?.completed_at || item?.updated_at || '');
    if (Number.isFinite(start) && Number.isFinite(end) && end >= start) return `${((end - start) / 1000).toFixed((end - start) >= 10000 ? 0 : 1)} 秒`;
    return '—';
  }

  function sessionProgressText(item) {
    if (sessionUI?.progressText) return sessionUI.progressText(item);
    const raw = Number(item?.progress_percent ?? item?.progress);
    if (!Number.isFinite(raw)) return '进度：—';
    const percent = raw <= 1 ? raw * 100 : raw;
    return `进度：${Math.max(0, Math.min(100, Math.round(percent)))}%`;
  }

  function sessionApprovalText(item) {
    if (sessionUI?.approvalText) return sessionUI.approvalText(item);
    const approval = item?.approval_status;
    if (!approval) return '审批：—';
    if (typeof approval === 'object') return `审批：${text(approval.kind || approval.status, '待处理')}`;
    return `审批：${text(approval)}`;
  }

  function sessionAgentToolText(item) {
    if (sessionUI?.agentToolText) return sessionUI.agentToolText(item);
    const value = item?.agent_tool_summary;
    if (typeof value === 'string' && value.trim()) return value.length > 180 ? `${value.slice(0, 180)}…` : value;
    if (value && typeof value === 'object') {
      const agents = Number(value.agents ?? value.agent_count);
      const tools = Number(value.tools ?? value.tool_count);
      const parts = [];
      if (Number.isFinite(agents)) parts.push(`Agent ${agents}`);
      if (Number.isFinite(tools)) parts.push(`Tool ${tools}`);
      if (parts.length) return parts.join(' · ');
    }
    return 'Agent/Tool：—';
  }

  function currentProjectId() {
    const selected = state.document?.querySelector?.('.project-item .project-item-main[aria-pressed="true"]');
    // The sidebar selection reflects app.js's draftProjectId when a user has
    // switched project context without changing the open conversation.
    return selected?.closest?.('.project-item')?.dataset?.projectId || state.conversation?.project_id || null;
  }

  function createTaskCard(task) {
    const doc = state.document;
    const item = doc.createElement('div');
    item.className = 'research-task-item'; item.setAttribute('role', 'listitem');
    const button = doc.createElement('button');
    button.type = 'button';
    button.className = 'research-task-card';
    button.dataset.taskId = text(task.research_task_id, '');
    button.dataset.sessionId = text(task.research_session_id, '');
    button.classList.toggle('is-selected', task.research_task_id === state.selectedTaskId || task.research_session_id === state.selectedSessionId);
    const title = doc.createElement('span');
    title.className = 'research-task-card-title';
    title.textContent = text(task.goal_excerpt, '未命名研究任务');
    const badge = doc.createElement('span');
    badge.className = 'research-badge';
    badge.dataset.status = text(task.status, '');
    badge.textContent = statusLabel(task.status);
    const meta = doc.createElement('span'); meta.className = 'research-task-card-meta';
    meta.textContent = `${task.research_session_id ? `会话 ${task.research_session_id}` : '未绑定会话'} · 计划 v${text(task.current_plan_version, '—')}`;
    const details = doc.createElement('span'); details.className = 'research-task-card-details';
    details.textContent = [
      `阶段：${text(task.current_phase || task.phase || task.stage, '—')}`,
      sessionProgressText(task), sessionApprovalText(task), `耗时：${sessionDurationText(task)}`,
      sessionAgentToolText(task),
    ].join(' · ');
    button.append(title, badge, meta, details);
    button.addEventListener('click', () => { selectTask(task.research_task_id, task.research_session_id); });
    item.appendChild(button);
    if (task.conversation_id) {
      const open = doc.createElement('button'); open.type = 'button'; open.className = 'research-open-session'; open.textContent = '打开对应会话';
      open.dataset.conversationId = String(task.conversation_id); open.setAttribute('aria-label', '打开对应会话');
      open.addEventListener('click', (event) => { event.preventDefault(); event.stopPropagation(); openConversationFromResearch(task.conversation_id); });
      item.appendChild(open);
    }
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
    setText('research-list-status', tasks.length ? `共 ${tasks.length} 个研究会话` : '当前工作区暂无研究会话。');
  }

  async function hydrateSession(raw) {
    const base = sessionTaskProjection(raw);
    if (!base) return null;
    let detail = null;
    try { detail = await requestJson(`/api/research-sessions/${encodeURIComponent(base.research_session_id)}`); } catch (_) { /* list remains usable */ }
    let task = detail?.task || detail?.research_task || null;
    const taskId = detail?.research_task_id || base.research_task_id;
    if (!task && taskId) {
      try { task = await requestJson(`/api/research-tasks/${encodeURIComponent(taskId)}`); } catch (_) { /* session-only card remains usable */ }
    }
    let conversation = detail?.conversation || raw?.conversation || null;
    const conversationId = detail?.conversation_id || base.conversation_id;
    if (!conversation && conversationId) {
      try { conversation = await requestJson(`/api/conversations/${encodeURIComponent(conversationId)}`); } catch (_) { /* title is optional */ }
    }
    const approvals = detail?.approvals || task?.approvals || base.approvals || [];
    const latestPlan = detail?.plan || task?.plan || base.plan || null;
    return sessionTaskProjection({
      ...raw, ...base, ...(detail || {}), task: task || base,
      conversation: conversation || undefined, approvals, plan: latestPlan,
      research_task_id: detail?.research_task_id || task?.research_task_id || base.research_task_id,
    });
  }

  async function loadTasks() {
    setText('research-list-status', '正在加载研究会话…');
    try {
      const data = await requestJson('/api/research-sessions?limit=100');
      const values = data?.research_sessions || data?.sessions || data?.items;
      const listed = (Array.isArray(values) ? values : []).filter(Boolean);
      state.sessions = (await Promise.all(listed.map(hydrateSession))).filter(Boolean);
      state.tasks = state.sessions;
      renderTaskList();
      return state.tasks;
    } catch (error) {
      state.tasks = []; state.sessions = [];
      renderTaskList();
      setText('research-list-status', userError(error, '任务列表加载失败。'));
      return [];
    }
  }

  function setDetailVisibility(visible) {
    const empty = byId('research-detail-empty');
    if (empty) empty.hidden = visible;
    ['research-plan-section', 'research-session-plan-section', 'research-timeline-section', 'research-selection-section', 'research-acquisition-section'].forEach((id) => { const node = byId(id); if (node && !visible) node.hidden = true; });
  }

  function taskActionButton(action) {
    const ids = {
      pause: 'research-task-pause-button', resume: 'research-task-resume-button',
      approve: 'research-task-approve-button', cancel: 'research-cancel-button', recover: 'research-task-recover-button',
    };
    return byId(ids[action]);
  }

  function resetTaskActionConfirmation(button) {
    if (!button) return;
    if (button.__researchConfirmTimer) root.clearTimeout(button.__researchConfirmTimer);
    delete button.__researchConfirmTimer;
    delete button.dataset.confirmed;
    button.dataset.actionState = '';
    button.setAttribute('aria-busy', 'false');
  }

  function setTaskActionState(button, stateName, label = '') {
    if (!button) return;
    ['loading', 'success', 'error', 'conflict', 'confirm'].forEach((name) => button.classList.toggle(`is-${name}`, stateName === name));
    button.dataset.actionState = stateName;
    button.setAttribute('aria-busy', stateName === 'loading' ? 'true' : 'false');
    if (label) button.textContent = label;
  }

  function renderTaskActionControls(task, { preserveState = false } = {}) {
    const taskId = task?.research_task_id || state.selectedTaskId;
    const status = task?.status || '';
    Object.keys(TASK_ACTION_PATHS).forEach((action) => {
      const button = taskActionButton(action);
      if (!button) return;
      const available = Boolean(taskId) && TASK_ACTION_STATUSES[action].has(status);
      button.hidden = !available;
      button.setAttribute('aria-hidden', available ? 'false' : 'true');
      if (!preserveState || !available) {
        resetTaskActionConfirmation(button);
        setTaskActionState(button, '', TASK_ACTION_LABELS[action]);
      }
      const blocked = preserveState && ['success', 'conflict'].includes(button.dataset.actionState);
      button.disabled = !available || state.taskActionInFlight || blocked;
    });
    const recovery = byId('research-recovery-notice');
    if (recovery) {
      const visible = status === 'interrupted' || status === 'recovery_required';
      recovery.hidden = !visible;
      recovery.textContent = visible ? '任务已中断；刷新会话详情后可查看已持久化的检查点与事件。' : '';
    }
  }

  function taskActionPayload(action) {
    if (action === 'approve') return { action: 'approve' };
    return {};
  }

  function taskActionUrl(taskId, action) {
    if (action === 'pause') return `/api/research-tasks/${encodeURIComponent(taskId)}/pause`;
    if (action === 'resume') return `/api/research-tasks/${encodeURIComponent(taskId)}/resume`;
    if (action === 'cancel') return `/api/research-tasks/${encodeURIComponent(taskId)}/cancel`;
    if (action === 'recover') return `/api/research-tasks/${encodeURIComponent(taskId)}/recover`;
    // Keep the legacy task approval route behind the action allowlist; the
    // Session/Approval card remains the canonical path for Session-first work.
    return `/api/research-tasks/${encodeURIComponent(taskId)}/${TASK_ACTION_PATHS[action]}`;
  }

  async function submitTaskAction(action, button) {
    const taskId = state.selectedTaskId || state.selectedTask?.research_task_id;
    if (!taskId || !button || state.taskActionInFlight || button.disabled) return null;
    state.taskActionInFlight = true;
    setTaskActionState(button, 'loading', '提交中…');
    renderTaskActionControls(state.selectedTask, { preserveState: true });
    const payload = taskActionPayload(action);
    const options = { method: 'POST' };
    if (action === 'resume' || action === 'approve') {
      options.headers = { 'Content-Type': 'application/json' };
      options.body = JSON.stringify(payload);
    }
    try {
      const result = await requestJson(taskActionUrl(taskId, action), options);
      state.selectedTask = { ...state.selectedTask, ...result, research_task_id: result?.research_task_id || taskId };
      state.tasks = state.tasks.map((item) => item.research_task_id === taskId ? { ...item, ...result } : item);
      state.sessions = state.tasks;
      state.statusNotice = action === 'pause' ? '研究任务已暂停，已完成证据与检查点会保留。'
        : action === 'resume' ? '研究任务已继续，系统从持久化进度接着执行。'
          : action === 'approve' ? '计划已批准，研究任务正在继续。'
            : action === 'recover' ? '恢复检查完成：已清理过期租约并返回检查点摘要，未知节点不会被自动重放。'
              : '研究会话已取消，后续节点不会继续创建。';
      setTaskActionState(button, 'success', `${TASK_ACTION_LABELS[action]}已完成`);
      renderTaskHeader(state.selectedTask, { preserveActions: true });
      renderTaskList();
      if (action === 'cancel') { closeStream(); state.streamEnded = true; }
      else if (action === 'resume' || action === 'approve') { state.streamEnded = false; connectStream(); }
      return result;
    } catch (error) {
      const code = String(error?.code || '').toUpperCase();
      const conflict = ['TASK_TERMINAL_CONFLICT', 'TASK_RUNNING_CONFLICT', 'INVALID_STATE_TRANSITION', 'PLAN_VERSION_STALE'].includes(code);
      setTaskActionState(button, conflict ? 'conflict' : 'error', conflict ? '状态已变化，请刷新' : '提交失败，重试');
      button.disabled = conflict;
      state.statusNotice = userError(error, conflict ? '任务状态已变化，请刷新任务详情。' : '操作失败，请稍后重试。');
      setText('research-summary-text', state.statusNotice);
      return null;
    } finally {
      state.taskActionInFlight = false;
      renderTaskActionControls(state.selectedTask, { preserveState: true });
    }
  }

  function beginTaskAction(action) {
    const button = taskActionButton(action);
    if (!button || button.hidden || state.taskActionInFlight) return;
    if (button.dataset.confirmed !== 'true') {
      button.dataset.confirmed = 'true';
      setTaskActionState(button, 'confirm', TASK_ACTION_CONFIRM_LABELS[action]);
      button.disabled = false;
      button.setAttribute('aria-label', `${TASK_ACTION_CONFIRM_LABELS[action]}，${TASK_ACTION_LABELS[action]}`);
      button.__researchConfirmTimer = root.setTimeout(() => {
        resetTaskActionConfirmation(button);
        setTaskActionState(button, '', TASK_ACTION_LABELS[action]);
        button.disabled = false;
      }, 4000);
      return;
    }
    resetTaskActionConfirmation(button);
    submitTaskAction(action, button);
  }

  function renderTaskHeader(task, { preserveActions = false } = {}) {
    const status = byId('research-detail-status');
    if (status) { status.dataset.status = text(task?.status, ''); status.textContent = statusLabel(task?.status); }
    setText('research-detail-title', task?.goal_excerpt || task?.topic || '选择一个研究会话');
    setText('research-detail-meta', task ? `${task.research_session_id ? `会话 ${task.research_session_id}` : `任务 ${text(task.research_task_id)}`} · ${task.conversation_id ? `对话 ${task.conversation_id} · ` : ''}阶段 ${text(task.current_phase || task.phase || task.stage, '—')} · ${sessionProgressText(task)} · ${sessionApprovalText(task)} · 耗时 ${sessionDurationText(task)}` : '刷新后会先恢复会话详情，再连接实时事件。');
    renderTaskActionControls(task, { preserveState: preserveActions });
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

  function parseSessionJson(value) {
    if (value && typeof value === 'object' && !Array.isArray(value)) return value;
    if (typeof value !== 'string' || value.length > 20000) return {};
    try { const parsed = JSON.parse(value); return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}; } catch (_) { return {}; }
  }

  function safeSessionValue(value, fallback = '未提供') {
    if (value === null || value === undefined || value === '') return fallback;
    if (typeof value === 'string') {
      if (/(?:https?|ftp):\/\//i.test(value.trim())) return fallback;
      return value.length > 2400 ? `${value.slice(0, 2400)}…` : value;
    }
    if (typeof value === 'number' || typeof value === 'boolean') return String(value);
    return fallback;
  }

  function safeSessionList(value, limit = 12) {
    const values = Array.isArray(value) ? value : value === undefined || value === null ? [] : [value];
    return values.map((item) => {
      if (typeof item === 'string' || typeof item === 'number' || typeof item === 'boolean') return safeSessionValue(item, '');
      if (!item || typeof item !== 'object' || Array.isArray(item)) return '';
      return ['id', 'name', 'role', 'capability', 'source', 'research_question', 'task_type', 'depends_on', 'query', 'limit']
        .filter((key) => Object.prototype.hasOwnProperty.call(item, key))
        .map((key) => `${key}: ${safeSessionValue(item[key], '')}`).filter((part) => !part.endsWith(': ')).join(' · ');
    }).filter((item) => item && !/^https?:\/\//i.test(item)).slice(0, limit);
  }

  function sessionPlanField(plan, key) {
    if (!plan || typeof plan !== 'object') return null;
    const shared = sessionUI?.planField?.(plan, key);
    if (shared !== null && shared !== undefined) return shared;
    if (key === 'safety_summary' && plan.safe_summary !== undefined) return plan.safe_summary;
    return plan[key] !== undefined ? plan[key] : parseSessionJson(plan[`${key}_json`]);
  }

  function sessionPlanFieldText(plan, key) {
    const value = sessionPlanField(plan, key);
    if (key === 'objective') return safeSessionValue(value);
    if (key === 'scope') {
      const scope = parseSessionJson(value); const parts = [];
      safeSessionList(scope.in_scope || scope.include || scope.facets).forEach((item) => parts.push(`包含：${item}`));
      safeSessionList(scope.exclusions || scope.exclude).forEach((item) => parts.push(`排除：${item}`));
      safeSessionList(scope.research_directions || scope.questions).forEach((item) => parts.push(`方向：${item}`));
      return parts.join(' · ') || safeSessionValue(value);
    }
    if (key === 'work_items' || key === 'capabilities' || key === 'report_structure') return safeSessionList(value).join('；') || safeSessionValue(value);
    if (key === 'budget') {
      const budget = parseSessionJson(value);
      return ['model_loops', 'tool_calls', 'seconds', 'worker_count', 'max_results']
        .filter((name) => budget[name] !== undefined).map((name) => `${name}: ${safeSessionValue(budget[name], '')}`).join(' · ') || safeSessionValue(value);
    }
    if (key === 'safety_summary') {
      const safety = parseSessionJson(value);
      return ['degraded_sources', 'fallback', 'fallback_strategy', 'stop_reason', 'limitations']
        .filter((name) => safety[name] !== undefined).map((name) => `${name}: ${safeSessionValue(safety[name], '')}`).join(' · ') || safeSessionValue(value);
    }
    return safeSessionValue(value);
  }

  function sessionCommandScope(command, approval, plan) {
    const requested = parseSessionJson(approval?.scope ?? approval?.requested_scope_json);
    if (command === 'approve_plan') return { plan_version: Number(plan?.version || plan?.plan_version || 0), output_hash: safeSessionValue(plan?.output_hash, '') };
    if (command === 'approve_capability') return { approval_request_id: safeSessionValue(approval?.approval_request_id, ''), skill: safeSessionValue(requested.skill, ''), skill_name: safeSessionValue(requested.skill_name, ''), tools: safeSessionList(requested.tools) };
    if (command === 'approve_resource_extension') return { approval_request_id: safeSessionValue(approval?.approval_request_id, ''), model_loops: Number(requested.model_loops) || 0, tool_calls: Number(requested.tool_calls) || 0, seconds: Number(requested.seconds) || 0 };
    if (command === 'revise_plan') return Object.fromEntries(['objective', 'scope', 'work_items', 'capabilities', 'budget', 'report_structure'].map((key) => [key, sessionPlanField(plan, key)]));
    if (command === 'decline_request') return { approval_request_id: safeSessionValue(approval?.approval_request_id, '') };
    return {};
  }

  function setSessionCommandState(button, status, label = '') {
    if (!button) return;
    ['loading', 'success', 'error', 'stale', 'conflict'].forEach((name) => button.classList.toggle(`is-${name}`, status === name));
    button.dataset.state = status; button.setAttribute('aria-busy', status === 'loading' ? 'true' : 'false');
    if (label) button.textContent = label;
  }

  function addSessionRefreshAction(sessionId, button) {
    const section = button?.closest('.research-session-plan');
    const actions = byId('research-session-plan-actions');
    if (!section || !actions || actions.querySelector('.research-session-refresh')) return;
    const refresh = state.document.createElement('button'); refresh.type = 'button'; refresh.className = 'secondary-button research-session-refresh'; refresh.textContent = '刷新计划/重新加载会话';
    refresh.addEventListener('click', async () => {
      refresh.disabled = true; refresh.setAttribute('aria-busy', 'true'); refresh.textContent = '正在刷新…';
      try {
        const session = await requestJson(`/api/research-sessions/${encodeURIComponent(sessionId)}`);
        if (!state.selectedTask) return;
        state.selectedTask = { ...state.selectedTask, research_session_id: sessionId, research_session: session, session_plan: session.plan, session_approvals: session.approvals || [] };
        renderSessionPlan(session.plan, session.approvals || [], session);
      } catch (_) {
        refresh.disabled = false; refresh.setAttribute('aria-busy', 'false'); refresh.textContent = '刷新失败，重试';
      }
    });
    actions.appendChild(refresh);
  }

  async function submitSessionCommand(sessionId, command, subjectVersion, scopeJson, button, onSuccess = null) {
    if (!sessionId || !button || button.dataset.state === 'loading' || button.dataset.state === 'success') return null;
    setSessionCommandState(button, 'loading', '提交中…'); button.disabled = true;
    if (!button.dataset.idempotencyKey) button.dataset.idempotencyKey = root.crypto?.randomUUID?.() || `research-command-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const payload = { command, subject_version: Number(subjectVersion) || 0, scope_json: scopeJson && typeof scopeJson === 'object' ? scopeJson : {}, idempotency_key: button.dataset.idempotencyKey };
    try {
      const result = await requestJson(`/api/research-sessions/${encodeURIComponent(sessionId)}/commands`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      setSessionCommandState(button, 'success', `${SESSION_COMMAND_LABELS[command] || '命令'}已完成`); button.disabled = true; onSuccess?.(result); return result;
    } catch (error) {
      const code = String(error?.code || '').toUpperCase();
      const status = code === 'APPROVAL_STALE' || code === 'PLAN_VERSION_STALE' ? 'stale' : code === 'APPROVAL_CONFLICT' ? 'conflict' : 'error';
      setSessionCommandState(button, status, status === 'stale' ? '版本已过期' : status === 'conflict' ? '已有窗口处理' : '提交失败，重试');
      button.disabled = status === 'stale' || status === 'conflict';
      if (status === 'stale' || status === 'conflict') addSessionRefreshAction(sessionId, button);
      else button.disabled = false;
      return null;
    }
  }

  async function mergeSessionCommandResult(result, sessionId) {
    const returnedTask = result?.task || result?.research_task || null;
    const returnedSession = result?.session || result?.research_session || {};
    const taskId = result?.research_task_id || returnedTask?.research_task_id || state.selectedTask?.research_task_id || null;
    const merged = sessionTaskProjection({
      ...(state.selectedTask?.research_session || {}),
      ...returnedSession,
      research_session_id: sessionId,
      research_task_id: taskId,
      task: returnedTask || state.selectedTask || undefined,
      status: returnedSession.status || result?.status || (taskId ? 'queued' : state.selectedTask?.status),
      current_plan_version: result?.subject_version || returnedSession.current_plan_version || state.selectedTask?.current_plan_version,
    });
    if (merged) {
      state.selectedSessionId = sessionId;
      state.tasks = state.tasks.map((item) => item.research_session_id === sessionId ? { ...item, ...merged } : item);
      state.sessions = state.tasks;
      state.selectedTask = { ...state.selectedTask, ...merged, research_session_id: sessionId };
      renderTaskHeader(state.selectedTask); renderTaskList(); renderSessionPlan(merged.session_plan || merged.plan, merged.session_approvals || merged.approvals, merged.research_session);
    }
    // approve_plan materializes the Task/Activity message in the backend Saga;
    // reselecting through the same loader hydrates the canonical Task and starts
    // the existing Task07 SSE/Task08 report pipeline exactly once.
    if (taskId && state.selectedTaskId !== taskId) await selectTask(taskId, sessionId);
    else if (taskId && !state.eventSource) { await loadReport(taskId); connectStream(); }
    return merged;
  }

  function renderSessionApprovals(approvals, sessionId, subjectVersion, plan) {
    const container = byId('research-session-approvals'); if (!container) return;
    container.replaceChildren();
    (Array.isArray(approvals) ? approvals : []).filter((approval) => approval && Object.prototype.hasOwnProperty.call(SESSION_APPROVAL_LABELS, approval.kind)).forEach((approval) => {
      const card = state.document.createElement('article'); card.className = 'research-session-approval'; card.dataset.kind = approval.kind; card.dataset.status = approval.status || 'pending';
      const title = state.document.createElement('strong'); title.className = 'research-session-approval-title'; title.textContent = SESSION_APPROVAL_LABELS[approval.kind];
      const status = state.document.createElement('span'); status.className = 'research-session-approval-status'; status.textContent = approval.status === 'pending' ? '待处理' : `已${approval.status}`;
      const meta = state.document.createElement('span'); meta.className = 'research-session-approval-meta'; meta.textContent = `版本 v${text(approval.subject_version, '—')} · ${safeSessionValue(approval.approval_request_id, '无 ID')}`;
      const actions = state.document.createElement('div'); actions.className = 'research-session-approval-actions';
      const command = approval.kind === 'plan' ? 'approve_plan' : approval.kind === 'capability_override' ? 'approve_capability' : 'approve_resource_extension';
      const approve = state.document.createElement('button'); approve.type = 'button'; approve.className = 'send-button research-session-command'; approve.textContent = SESSION_COMMAND_LABELS[command];
      const decline = state.document.createElement('button'); decline.type = 'button'; decline.className = 'secondary-button research-session-command'; decline.textContent = '拒绝';
      const pending = approval.status === 'pending'; approve.disabled = !pending; decline.disabled = !pending;
      if (pending) {
        approve.addEventListener('click', () => submitSessionCommand(sessionId, command, approval.subject_version || subjectVersion, sessionCommandScope(command, approval, plan), approve, async (result) => { status.textContent = '已完成'; card.dataset.status = 'approved'; await mergeSessionCommandResult(result, sessionId); }));
        decline.addEventListener('click', () => submitSessionCommand(sessionId, 'decline_request', approval.subject_version || subjectVersion, sessionCommandScope('decline_request', approval, plan), decline, () => { status.textContent = '已拒绝'; card.dataset.status = 'rejected'; }));
      }
      actions.append(approve, decline); card.append(title, status, meta, actions); container.appendChild(card);
    });
  }

  function renderSessionPlan(plan, approvals = [], session = null) {
    const section = byId('research-session-plan-section'); if (!section) return;
    const sessionId = session?.research_session_id || state.selectedTask?.research_session_id || state.selectedTask?.session_id;
    const version = Number(plan?.version || plan?.plan_version || session?.current_plan_version || state.selectedTask?.current_plan_version || 0);
    section.hidden = !plan && !approvals.length;
    if (!plan && !approvals.length) return;
    setText('research-session-plan-meta', `会话计划 v${version || '—'} · ${plan?.status === 'proposed' ? '待审批' : (plan?.status || '已记录')}`);
    const fields = byId('research-session-plan-fields'); clearNode(fields);
    SESSION_PLAN_FIELDS.forEach(([key, label]) => { const dt = state.document.createElement('dt'); dt.className = 'research-session-plan-field-name'; dt.textContent = label; const dd = state.document.createElement('dd'); dd.className = 'research-session-plan-field-value'; dd.textContent = sessionPlanFieldText(plan || {}, key); fields.append(dt, dd); });
    renderSessionApprovals(approvals, sessionId, version, plan || {});
    const actions = byId('research-session-plan-actions'); clearNode(actions);
    if (sessionId && plan && version > 0) {
      const revise = state.document.createElement('button'); revise.type = 'button'; revise.className = 'secondary-button research-session-command'; revise.textContent = SESSION_COMMAND_LABELS.revise_plan;
      revise.addEventListener('click', () => submitSessionCommand(sessionId, 'revise_plan', version, sessionCommandScope('revise_plan', null, plan), revise));
      const cancel = state.document.createElement('button'); cancel.type = 'button'; cancel.className = 'secondary-button danger-button research-session-command'; cancel.textContent = SESSION_COMMAND_LABELS.cancel_research;
      cancel.addEventListener('click', () => submitSessionCommand(sessionId, 'cancel_research', version, {}, cancel));
      actions.append(revise, cancel);
    }
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
    const treeHost = byId('research-processing-tree');
    if (treeHost && root.ProcessingTree?.createProcessingTree) {
      if (!state.processingTree || state.processingTreeTaskId !== state.selectedTaskId) {
        treeHost.replaceChildren();
        state.processingTree = root.ProcessingTree.createProcessingTree({ document: state.document, container: treeHost, storageKey: `research:${state.selectedTaskId || 'task'}` });
        state.processingTreeTaskId = state.selectedTaskId;
      }
      const treeHasNodes = state.processingTree.snapshot().length > 0;
      treeHost.hidden = !treeHasNodes;
      if (treeHasNodes) section.hidden = false;
      if (state.terminal && TERMINAL_STATUSES.has(state.terminal.payload?.status)) state.processingTree.finalize(state.terminal.payload.status, eventStopReason(state.terminal.payload));
    }
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

  function applyProcessingStepFrame(payload) {
    const section = byId('research-timeline-section');
    const treeHost = byId('research-processing-tree');
    if (!treeHost || !root.ProcessingTree?.createProcessingTree) return;
    if (!state.processingTree || state.processingTreeTaskId !== state.selectedTaskId) {
      treeHost.replaceChildren();
      state.processingTree = root.ProcessingTree.createProcessingTree({ document: state.document, container: treeHost, storageKey: `research:${state.selectedTaskId || 'task'}` });
      state.processingTreeTaskId = state.selectedTaskId;
    }
    if (payload?.operation === 'syncing' || payload?.status === 'trace_syncing' || payload?.code === 'TRACE_PROJECTION_FAILED') state.processingTree.setSyncing(true);
    else state.processingTree.upsert(payload?.step || payload);
    treeHost.hidden = state.processingTree.snapshot().length === 0 && !payload?.code;
    if (section && !treeHost.hidden) section.hidden = false;
  }

  function acquisitionStatusLabel(status) { return ACQUISITION_STATUS_TEXT[status] || '处理中'; }

  function acquisitionErrorText(code) {
    const value = typeof code === 'string' ? code : '';
    return ACQUISITION_ERROR_TEXT[value] || (value ? `错误码：${value}` : '导入失败，可重试。');
  }

  function resolveAcquisitionSearchId(task = state.selectedTask, report = state.report) {
    const candidates = [
      task?.search_id, task?.catalog_search_id, task?.research_search_id,
      task?.plan?.search_id, task?.research_session?.search_id,
      report?.search_id, report?.catalog_search_id,
    ];
    return candidates.find((value) => typeof value === 'string' && /^[A-Za-z0-9._~-]{1,200}$/.test(value)) || null;
  }

  function acquisitionCandidates() {
    const reportValues = Array.isArray(state.reportSelections) ? state.reportSelections : [];
    return reportValues.filter((value) => value && typeof value === 'object' && typeof value.catalog_paper_id === 'string' && value.catalog_paper_id.trim()).map((value) => ({
      ...value, catalog_paper_id: value.catalog_paper_id.trim(),
    })).slice(0, 20);
  }

  function acquisitionPreviewMap() {
    return new Map((Array.isArray(state.acquisition.preview) ? state.acquisition.preview : []).map((item) => [String(item?.catalog_paper_id || ''), item]));
  }

  function acquisitionProjectedItems() {
    const links = Array.isArray(state.acquisition.links) ? state.acquisition.links : [];
    const items = Array.isArray(state.acquisition.items) ? state.acquisition.items : [];
    const byId = new Map();
    [...links, ...items].forEach((item) => {
      const id = String(item?.catalog_paper_id || item?.candidate_id || item?.paper_id || '');
      if (!id) return;
      byId.set(id, { ...(byId.get(id) || {}), ...item, catalog_paper_id: id });
    });
    return [...byId.values()];
  }

  function acquisitionIsTerminal(status) {
    return ['completed', 'partial_success', 'failed', 'cancelled'].includes(String(status || ''));
  }

  function setAcquisitionStatus(message, status = '') {
    const node = byId('research-acquisition-status');
    if (!node) return;
    node.textContent = message || (status ? acquisitionStatusLabel(status) : '');
    node.dataset.status = status;
  }

  function renderAcquisitionEvidence(values) {
    const section = byId('research-evidence-upgrades');
    const list = byId('research-evidence-list');
    if (!section || !list) return;
    clearNode(list); section.hidden = true;
    const upgrades = (Array.isArray(values) ? values : []).filter((item) => item && typeof item === 'object').slice(0, 128);
    upgrades.forEach((upgrade) => {
      const item = state.document.createElement('li'); item.className = 'research-evidence-item'; item.dataset.status = String(upgrade.status || '');
      const head = state.document.createElement('div'); head.className = 'research-evidence-item-head';
      const title = state.document.createElement('strong'); title.className = 'research-evidence-title'; title.textContent = `Claim ${text(upgrade.claim_id, '未知')} · ${EVIDENCE_TEXT[upgrade.to_level] || text(upgrade.to_level, '证据')}`;
      const status = state.document.createElement('span'); status.className = 'research-acquisition-badge'; status.dataset.status = String(upgrade.status || ''); status.textContent = text(upgrade.status, '已记录');
      head.append(title, status);
      const meta = state.document.createElement('p'); meta.className = 'research-evidence-meta';
      const page = Number(upgrade.page); const pageEnd = Number(upgrade.page_end);
      const pageText = Number.isInteger(page) && page > 0 ? ` · 原文第 ${pageEnd > page ? `${page}–${pageEnd}` : page} 页` : '';
      meta.textContent = `文档：${text(upgrade.document_id, '未知')}${pageText}${Array.isArray(upgrade.chunk_ids) && upgrade.chunk_ids.length ? ` · ${upgrade.chunk_ids.length} 个切片` : ''}`;
      const actions = state.document.createElement('div'); actions.className = 'research-acquisition-item-actions';
      if (upgrade.document_id && (upgrade.status === 'upgraded' || upgrade.status === 'revalidation_required')) {
        const locator = state.document.createElement('button'); locator.type = 'button'; locator.className = 'secondary-button research-evidence-locator'; locator.textContent = '打开原文切片';
        locator.dataset.documentId = String(upgrade.document_id); locator.dataset.chunkIds = Array.isArray(upgrade.chunk_ids) ? upgrade.chunk_ids.map(String).join(' ') : '';
        locator.addEventListener('click', () => {
          if (typeof root.jumpToKnowledgeBase === 'function') root.jumpToKnowledgeBase(String(upgrade.document_id));
          else if (root.location) root.location.hash = '#kb-view';
        });
        actions.appendChild(locator);
      }
      item.append(head, meta, actions); list.appendChild(item);
    });
    section.hidden = list.childNodes.length === 0;
  }

  function renderAcquisition() {
    const section = byId('research-acquisition-section');
    const list = byId('research-acquisition-candidates');
    if (!section || !list) return;
    const candidates = acquisitionCandidates();
    const projected = acquisitionProjectedItems();
    const preview = acquisitionPreviewMap();
    const hasAcquisition = candidates.length > 0 || projected.length > 0 || state.acquisition.status;
    section.hidden = !hasAcquisition;
    clearNode(list);
    candidates.forEach((candidate) => {
      const id = candidate.catalog_paper_id;
      const classified = preview.get(id) || {};
      const projectedItem = projected.find((item) => item.catalog_paper_id === id) || {};
      const status = String(projectedItem.status || classified.status || 'pending');
      const row = state.document.createElement('li'); row.className = 'research-acquisition-candidate'; row.dataset.paperId = id; row.dataset.status = status;
      const head = state.document.createElement('div'); head.className = 'research-acquisition-candidate-head';
      const label = state.document.createElement('label');
      const checkbox = state.document.createElement('input'); checkbox.type = 'checkbox'; checkbox.checked = state.acquisition.selectedIds.has(id); checkbox.dataset.paperId = id;
      checkbox.setAttribute('aria-label', `选择全文候选 ${id}`);
      checkbox.addEventListener('change', () => { if (checkbox.checked) state.acquisition.selectedIds.add(id); else state.acquisition.selectedIds.delete(id); renderAcquisition(); });
      const title = state.document.createElement('span'); title.className = 'research-acquisition-candidate-title'; title.textContent = `目录论文：${id}`;
      label.append(checkbox, title);
      const badge = state.document.createElement('span'); badge.className = 'research-acquisition-badge'; badge.dataset.status = status; badge.textContent = acquisitionStatusLabel(status);
      head.append(label, badge);
      const meta = state.document.createElement('p'); meta.className = 'research-acquisition-item-meta'; meta.textContent = `相关性：${text(candidate.relevance)} · ${evidenceLabel(candidate.evidence_level)}`;
      row.append(head, meta); list.appendChild(row);
    });
    const count = state.acquisition.selectedIds.size;
    setText('research-acquisition-selection-count', `已选 ${count} 篇 · 选集 v${text(state.acquisition.selectionVersion, '—')}`);
    const confirm = byId('research-acquisition-confirm');
    if (confirm) {
      confirm.disabled = count === 0 || state.acquisition.confirming || state.acquisition.loading || Boolean(state.acquisition.status && state.acquisition.status !== 'failed' && state.acquisition.status !== 'cancelled');
      confirm.textContent = state.acquisition.confirming ? '正在确认…' : state.acquisition.status && state.acquisition.status !== 'failed' ? '已确认导入' : '确认并开始导入';
      confirm.setAttribute('aria-busy', state.acquisition.confirming ? 'true' : 'false');
    }
    const refresh = byId('research-acquisition-refresh');
    if (refresh) refresh.disabled = state.acquisition.loading || projected.length === 0;
    const progress = byId('research-acquisition-progress');
    const progressSummary = byId('research-acquisition-progress-summary');
    const itemsHost = byId('research-acquisition-items');
    if (progress && progressSummary && itemsHost) {
      clearNode(itemsHost);
      progress.hidden = projected.length === 0;
      const completed = projected.filter((item) => ['completed', 'existing'].includes(String(item.status))).length;
      const waiting = projected.filter((item) => String(item.status) === 'waiting_login').length;
      const failed = projected.filter((item) => String(item.status) === 'failed').length;
      progressSummary.textContent = `${completed}/${projected.length} 篇已完成${waiting ? ` · ${waiting} 篇等待登录` : ''}${failed ? ` · ${failed} 篇失败可重试` : ''}`;
      projected.forEach((item) => {
        const row = state.document.createElement('li'); row.className = 'research-acquisition-item'; row.dataset.status = String(item.status || '');
        const head = state.document.createElement('div'); head.className = 'research-acquisition-item-head';
        const title = state.document.createElement('strong'); title.className = 'research-acquisition-item-title'; title.textContent = `目录论文：${text(item.catalog_paper_id, '未知')}`;
        const badge = state.document.createElement('span'); badge.className = 'research-acquisition-badge'; badge.dataset.status = String(item.status || ''); badge.textContent = acquisitionStatusLabel(item.status);
        head.append(title, badge);
        const meta = state.document.createElement('p'); meta.className = 'research-acquisition-item-meta'; meta.textContent = item.document_id ? `知识库文档：${item.document_id}` : `导入条目：${text(item.import_item_id || item.item_id, '等待创建')}`;
        const actions = state.document.createElement('div'); actions.className = 'research-acquisition-item-actions';
        if (item.status === 'waiting_login') {
          const wait = state.document.createElement('span'); wait.className = 'research-acquisition-item-meta'; wait.textContent = '请在既有浏览器会话完成登录，页面不会自动登录。'; actions.appendChild(wait);
        }
        if (item.status === 'failed' && (item.import_item_id || item.item_id)) {
          const retry = state.document.createElement('button'); retry.type = 'button'; retry.className = 'secondary-button'; retry.textContent = state.acquisition.retrying.has(String(item.import_item_id || item.item_id)) ? '重试中…' : '重试';
          retry.disabled = state.acquisition.retrying.has(String(item.import_item_id || item.item_id));
          retry.addEventListener('click', () => retryAcquisitionItem(item, retry)); actions.appendChild(retry);
        }
        if (item.error_code) { const error = state.document.createElement('p'); error.className = 'research-acquisition-item-error'; error.textContent = acquisitionErrorText(item.error_code); row.append(error); }
        row.append(head, meta, actions); itemsHost.appendChild(row);
      });
    }
    renderAcquisitionEvidence(state.acquisition.evidence);
  }

  async function loadAcquisitionStatus(taskId = state.selectedTaskId) {
    if (!taskId || state.acquisition.loading) return null;
    state.acquisition.loading = true; renderAcquisition();
    try {
      const result = await requestJson(`/api/research-tasks/${encodeURIComponent(taskId)}/acquisitions`);
      if (state.selectedTaskId !== taskId) return null;
      state.acquisition.status = result?.status || result?.approval_status || null;
      state.acquisition.selectionVersion = result?.selection_version || state.acquisition.selectionVersion;
      state.acquisition.links = Array.isArray(result?.links) ? result.links : [];
      state.acquisition.items = Array.isArray(result?.items) ? result.items : [];
      state.acquisition.events = Array.isArray(result?.events) ? result.events : [];
      if (Array.isArray(result?.evidence_upgrades)) state.acquisition.evidence = result.evidence_upgrades;
      if (result?.batch_id) state.acquisition.batchId = String(result.batch_id);
      setAcquisitionStatus(state.acquisition.status ? `导入状态：${acquisitionStatusLabel(state.acquisition.status)}` : '已确认，等待导入状态。', state.acquisition.status || 'queued');
      renderAcquisition();
      scheduleAcquisitionPoll();
      return result;
    } catch (error) {
      if (error.status !== 404 && error.code !== 'BATCH_NOT_FOUND') setAcquisitionStatus(userError(error, '导入状态暂时不可用。'), 'failed');
      renderAcquisition();
      return null;
    } finally { state.acquisition.loading = false; renderAcquisition(); }
  }

  function scheduleAcquisitionPoll() {
    if (state.acquisition.pollTimer || !state.selectedTaskId || !state.acquisition.status || acquisitionIsTerminal(state.acquisition.status)) return;
    const generation = state.acquisition.generation;
    state.acquisition.pollTimer = root.setTimeout(async () => {
      state.acquisition.pollTimer = null;
      if (generation !== state.acquisition.generation) return;
      await loadAcquisitionStatus(state.selectedTaskId);
    }, 2500);
  }

  function stopAcquisitionPoll() {
    if (state.acquisition.pollTimer) root.clearTimeout(state.acquisition.pollTimer);
    state.acquisition.pollTimer = null; state.acquisition.generation += 1;
  }

  async function loadAcquisitionPreview(taskId = state.selectedTaskId) {
    const candidates = acquisitionCandidates();
    if (!taskId || !candidates.length) { renderAcquisition(); return null; }
    const planVersion = safePositiveInteger(state.selectedTask?.current_plan_version || state.report?.plan_version) || 1;
    const searchId = resolveAcquisitionSearchId(); state.acquisition.searchId = searchId;
    state.acquisition.loading = true; setAcquisitionStatus('正在读取候选分类（不会下载）…'); renderAcquisition();
    try {
      const result = await requestJson(`/api/research-tasks/${encodeURIComponent(taskId)}/acquisition-preview`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ plan_version: planVersion, ...(searchId ? { search_id: searchId } : {}) }) });
      if (state.selectedTaskId !== taskId) return null;
      state.acquisition.selectionVersion = result?.selection_version || null;
      state.acquisition.preview = Array.isArray(result?.items) ? result.items : [];
      if (!state.acquisition.selectedIds.size) candidates.forEach((item) => state.acquisition.selectedIds.add(item.catalog_paper_id));
      setAcquisitionStatus('候选已分类；确认前不会下载。'); renderAcquisition();
      state.acquisition.loading = false;
      await loadAcquisitionStatus(taskId);
      return result;
    } catch (error) {
      setAcquisitionStatus(userError(error, '候选预览暂时不可用。'), 'failed'); renderAcquisition(); return null;
    } finally { state.acquisition.loading = false; renderAcquisition(); }
  }

  async function confirmAcquisition() {
    const taskId = state.selectedTaskId; const ids = [...state.acquisition.selectedIds];
    if (!taskId || !ids.length || state.acquisition.confirming) return null;
    if (!state.acquisition.selectionVersion) { setAcquisitionStatus('选集版本尚未就绪，请刷新任务详情。', 'failed'); return null; }
    if (!state.acquisition.searchId) { setAcquisitionStatus('服务器搜索快照不可用，暂不能确认；请刷新任务详情后重试。', 'failed'); return null; }
    state.acquisition.confirming = true; renderAcquisition(); setAcquisitionStatus('正在提交确认…');
    if (!state.acquisition.idempotencyKey) state.acquisition.idempotencyKey = root.crypto?.randomUUID?.() || `research-acquisition-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    try {
      const result = await requestJson(`/api/research-tasks/${encodeURIComponent(taskId)}/acquisitions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ selection_version: state.acquisition.selectionVersion, paper_ids: ids, idempotency_key: state.acquisition.idempotencyKey, search_id: state.acquisition.searchId }) });
      state.acquisition.status = result?.status || result?.approval_status || 'queued';
      state.acquisition.batchId = result?.batch_id || null; state.acquisition.links = Array.isArray(result?.links) ? result.links : [];
      state.acquisition.items = Array.isArray(result?.items) ? result.items : []; state.acquisition.events = Array.isArray(result?.events) ? result.events : [];
      setAcquisitionStatus(`已确认，导入状态：${acquisitionStatusLabel(state.acquisition.status)}`, state.acquisition.status); renderAcquisition(); scheduleAcquisitionPoll();
      return result;
    } catch (error) { setAcquisitionStatus(userError(error, '确认失败；候选仍未被下载。'), 'failed'); renderAcquisition(); return null; }
    finally { state.acquisition.confirming = false; renderAcquisition(); }
  }

  async function retryAcquisitionItem(item, button) {
    const itemId = String(item?.import_item_id || item?.item_id || '');
    if (!itemId || state.acquisition.retrying.has(itemId)) return null;
    state.acquisition.retrying.add(itemId); if (button) { button.disabled = true; button.textContent = '重试中…'; }
    renderAcquisition();
    try {
      const result = await requestJson(`/api/papers/import-items/${encodeURIComponent(itemId)}/retry`, { method: 'POST' });
      setAcquisitionStatus('已提交失败条目重试，正在同步既有导入状态。', 'queued');
      state.acquisition.status = result?.status || 'queued'; await loadAcquisitionStatus(state.selectedTaskId); return result;
    } catch (error) { setAcquisitionStatus(userError(error, '重试失败，请稍后再试。'), 'failed'); return null; }
    finally { state.acquisition.retrying.delete(itemId); renderAcquisition(); }
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

  function reportCitationValue(value) {
    if (value === null || value === undefined || value === '') return '';
    if (typeof value !== 'object') return String(value).slice(0, 2400);
    return Object.entries(value).slice(0, 12).map(([key, item]) => {
      const scalar = typeof item === 'string' || typeof item === 'number' || typeof item === 'boolean' ? String(item) : '';
      return scalar ? `${key}: ${scalar.slice(0, 600)}` : '';
    }).filter(Boolean).join(' · ');
  }

  function renderReportArtifacts(artifacts) {
    const host = byId('research-report-artifacts');
    if (!host) return;
    clearNode(host); host.hidden = true;
    const labels = { markdown: '下载 Markdown', html: '打开 HTML', citation_manifest: '下载引用 manifest' };
    ['markdown', 'html', 'citation_manifest'].forEach((kind) => {
      const artifact = (Array.isArray(artifacts) ? artifacts : []).map(normalizeArtifact).find((item) => item?.artifact_type === kind);
      const url = artifact?.download_url || '';
      const actionUrl = artifactActionUrl(kind, url);
      if (!actionUrl) return;
      const link = state.document.createElement('a'); link.className = 'research-report-artifact'; link.href = actionUrl; link.textContent = labels[kind];
      link.setAttribute('aria-label', labels[kind]); link.setAttribute('rel', 'noopener noreferrer');
      if (kind === 'html') link.target = '_blank'; else link.download = '';
      host.appendChild(link);
    });
    host.hidden = host.childNodes.length === 0;
  }

  function renderReportCitations(citations) {
    const details = byId('research-report-citations');
    const list = byId('research-report-citation-list');
    if (!details || !list) return;
    clearNode(list); details.hidden = true;
    const values = Array.isArray(citations) ? citations.slice(0, 256) : citations && typeof citations === 'object' ? [citations] : [];
    values.forEach((citation) => { const item = state.document.createElement('li'); item.textContent = reportCitationValue(citation); if (item.textContent) list.appendChild(item); });
    details.hidden = list.childNodes.length === 0;
  }

  async function loadReport(taskId) {
    const stateNode = byId('research-report-state');
    const reportNode = byId('research-report-markdown');
    if (stateNode) stateNode.textContent = '正在读取报告…';
    if (reportNode) { reportNode.hidden = true; reportNode.replaceChildren(); }
    renderReportArtifacts([]); renderReportCitations([]);
    state.reportSelections = [];
    state.report = null;
    renderSelection();
    try {
      const report = await requestJson(`/api/research-tasks/${encodeURIComponent(taskId)}/report`);
      let artifacts = Array.isArray(report.artifacts) ? report.artifacts : [];
      const sessionId = state.selectedTask?.research_session_id || state.selectedTask?.research_session?.research_session_id;
      if (sessionId) {
        try {
          const artifactData = await requestJson(`/api/research-sessions/${encodeURIComponent(sessionId)}/artifacts?report_version=${encodeURIComponent(report.plan_version || report.report_version || 1)}`);
          artifacts = Array.isArray(artifactData?.artifacts) ? artifactData.artifacts : artifacts;
        } catch (_) { /* legacy report remains readable when artifact metadata is unavailable */ }
      }
      state.report = { ...report, artifacts, report_version: report.report_version || report.plan_version };
      state.reportSelections = Array.isArray(report.selections) ? report.selections : [];
      state.acquisition.evidence = Array.isArray(report.evidence_upgrades) ? report.evidence_upgrades : (Array.isArray(report.evidence) ? report.evidence : []);
      renderSelection();
      await loadAcquisitionPreview(taskId);
      renderSummary();
      renderSafeMarkdown(reportNode, report.markdown);
      renderReportArtifacts(artifacts); renderReportCitations(report.citation_manifest);
      if (stateNode) stateNode.textContent = `报告 v${text(report.plan_version)} · ${statusLabel(report.status)}`;
      const limitations = limitationText(report.limitations);
      setText('research-report-limitations', limitations ? `限制：${limitations}` : '');
      return report;
    } catch (error) {
      state.reportSelections = [];
      state.report = null;
      stopAcquisitionPoll();
      state.acquisition.preview = []; state.acquisition.status = null; state.acquisition.links = []; state.acquisition.items = [];
      state.acquisition.events = []; state.acquisition.evidence = []; state.acquisition.selectionVersion = null; state.acquisition.selectedIds = new Set();
      state.acquisition.searchId = null; state.acquisition.idempotencyKey = null;
      renderSelection();
      renderAcquisition();
      renderSummary();
      if (stateNode) stateNode.textContent = error.code === 'REPORT_NOT_READY' ? ERROR_TEXT.REPORT_NOT_READY : userError(error, '报告暂时不可用。');
      setText('research-report-limitations', '');
      renderReportArtifacts([]); renderReportCitations([]);
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
    if (type === 'processing_step') {
      applyProcessingStepFrame(data.payload && typeof data.payload === 'object' ? data.payload : data);
      return;
    }
    const seq = Number(data.event_seq);
    if (type !== 'terminal' && (!Number.isInteger(seq) || seq <= 0)) return;
    if (Number.isInteger(seq) && seq > 0) {
      if (seq <= state.lastSeq) return;
      state.lastSeq = seq;
      state.events.set(seq, { seq, type, timestamp: data.timestamp, payload: data.payload || {} });
    }
    // Synthetic terminal frames deliberately have event_seq=null and no id; they never move lastSeq.
    applyEvent({ type, seq: Number.isInteger(seq) && seq > 0 ? seq : null, timestamp: data.timestamp, payload: data.payload || {} });
    // The projector appends the terminal processing_step/upsert after the raw
    // terminal ResearchEvent. Keep the source open until that envelope can be
    // delivered; the generator then emits its synthetic terminal and closes.
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

  async function selectTask(taskId, sessionId = null) {
    if (!taskId && !sessionId) return;
    closeStream();
    state.selectedTaskId = taskId || null;
    state.selectedSessionId = sessionId || state.tasks.find((item) => item.research_task_id === taskId)?.research_session_id || null;
    stopAcquisitionPoll();
    state.acquisition.preview = []; state.acquisition.status = null; state.acquisition.links = []; state.acquisition.items = [];
    state.acquisition.events = []; state.acquisition.evidence = []; state.acquisition.selectionVersion = null; state.acquisition.selectedIds = new Set();
    state.acquisition.searchId = null; state.acquisition.idempotencyKey = null; state.acquisition.confirming = false; state.acquisition.retrying = new Set();
    state.selectedTask = null;
    state.events = new Map();
    state.selectedPapers = new Set();
    state.selectedPaperCount = null;
    state.reportSelections = [];
    state.report = null;
    state.terminal = null;
    state.processingTree = null;
    state.processingTreeTaskId = null;
    state.lastSeq = 0;
    state.streamEnded = false;
    state.approvalInFlight = false;
    state.statusNotice = '';
    renderTaskList();
    setDetailVisibility(false);
    renderTaskHeader(null);
    setText('research-summary-text', '正在恢复研究会话详情…');
    try {
      let task;
      if (taskId) task = await requestJson(`/api/research-tasks/${encodeURIComponent(taskId)}`);
      else task = sessionTaskProjection(await requestJson(`/api/research-sessions/${encodeURIComponent(sessionId)}`));
      if (state.selectedTaskId !== taskId && state.selectedSessionId !== sessionId) return;
      if (!task) throw new Error('研究会话不存在');
      const listed = state.tasks.find((item) => item.research_task_id === taskId || item.research_session_id === sessionId) || {};
      state.selectedTask = { ...listed, ...task };
      renderTaskHeader(task);
      renderPlan(task.plan);
      renderSessionPlan(task.session_plan || task.research_plan || task.plan || null, task.session_approvals || task.approvals || task.approval || [], task.research_session || (task.research_session_id ? { research_session_id: task.research_session_id, current_plan_version: task.current_plan_version } : null));
      const resolvedSessionId = task.research_session_id || task.session_id || task.research_session?.research_session_id || sessionId;
      if (resolvedSessionId) {
        try {
          const session = task.research_session?.research_session_id === resolvedSessionId ? task.research_session : await requestJson(`/api/research-sessions/${encodeURIComponent(resolvedSessionId)}`);
          if (state.selectedTaskId !== taskId && state.selectedSessionId !== resolvedSessionId) return;
          state.selectedSessionId = resolvedSessionId;
          const canonical = sessionTaskProjection({ ...session, task: state.selectedTask });
          state.selectedTask = { ...state.selectedTask, ...(canonical || {}), research_session_id: resolvedSessionId, research_session: session, session_plan: session.plan, session_approvals: session.approvals || [], status: session.status || state.selectedTask.status, conversation_id: session.conversation_id || state.selectedTask.conversation_id };
          renderTaskHeader(state.selectedTask);
          renderSessionPlan(session.plan, session.approvals || [], session);
        } catch (_) {
          // The legacy task detail remains usable when the optional session projection is unavailable.
          renderSessionPlan(task.session_plan || task.research_plan || task.plan || null, task.session_approvals || task.approvals || task.approval || [], task.research_session || (sessionId ? { research_session_id: sessionId, current_plan_version: task.current_plan_version } : null));
        }
      }
      setDetailVisibility(true);
      if (taskId) {
        await loadReport(taskId);
        if (state.selectedTaskId !== taskId) return;
        connectStream();
      } else {
        setText('research-report-state', '任务批准并完成后显示报告。');
      }
    } catch (error) {
      setText('research-detail-empty', userError(error, '任务详情加载失败。'));
      setDetailVisibility(false);
      setText('research-summary-text', userError(error));
    }
  }

  async function refreshWorkspace() {
    await conversationFromUrl();
    const tasks = await loadTasks();
    const selected = state.selectedTaskId && tasks.find((task) => task.research_task_id === state.selectedTaskId)
      || state.selectedSessionId && tasks.find((task) => task.research_session_id === state.selectedSessionId)
      || tasks.find((task) => task.conversation_id === state.conversationId);
    if (selected) await selectTask(selected.research_task_id, selected.research_session_id);
    else {
      closeStream(); stopAcquisitionPoll(); state.selectedTaskId = null; state.selectedSessionId = null; state.selectedTask = null; state.events = new Map(); state.selectedPapers = new Set(); state.selectedPaperCount = null; state.reportSelections = []; state.lastSeq = 0; state.approvalInFlight = false; state.statusNotice = '';
      state.acquisition.preview = []; state.acquisition.status = null; state.acquisition.links = []; state.acquisition.items = []; state.acquisition.events = []; state.acquisition.evidence = []; state.acquisition.selectionVersion = null; state.acquisition.selectedIds = new Set(); state.acquisition.searchId = null; state.acquisition.idempotencyKey = null;
      renderTaskHeader(null); setDetailVisibility(false); renderSummary();
      state.report = null; state.terminal = null;
      const report = byId('research-report-markdown'); if (report) { report.hidden = true; report.replaceChildren(); }
      setText('research-report-state', '任务完成后显示报告。');
      setText('research-report-limitations', '');
      renderReportArtifacts([]); renderReportCitations([]);
      renderAcquisition();
    }
  }

  async function createTask(event) {
    event.preventDefault();
    const goal = (byId('research-goal')?.value || '').trim();
    if (!goal) { setText('research-create-status', '请填写研究目标。'); byId('research-goal')?.focus(); return; }
    const button = byId('research-create-button'); if (button) button.disabled = true;
    setText('research-create-status', '正在创建研究会话…');
    const quality = byId('research-quality')?.value || 'balanced';
    const targetPaperCount = Number(byId('research-target-count')?.value || 12);
    const language = byId('research-language')?.value || 'zh';
    const reviewPlanFirst = Boolean(byId('research-review-plan')?.checked);
    if (!state.createIdempotencyKey) state.createIdempotencyKey = root.crypto?.randomUUID?.() || `research-session-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    state.triggerMessageId = state.triggerMessageId || state.conversation?.last_message_id || state.conversation?.trigger_message_id || null;
    const payload = {
      idempotency_key: state.createIdempotencyKey,
      trigger_message_id: state.triggerMessageId,
      ...(state.conversationId ? { conversation_id: state.conversationId } : {}),
      ...(currentProjectId() ? { project_id: currentProjectId() } : {}),
      intake: {
        topic: goal, objective: goal, language, depth: quality,
        sources: ['usenix'], citations: 'true', output: 'markdown',
        constraints: `目标论文数：${Number.isInteger(targetPaperCount) ? Math.max(1, Math.min(20, targetPaperCount)) : 12}；先审核计划：${reviewPlanFirst ? '是' : '否'}`,
      },
    };
    try {
      const response = await requestJson('/api/research-sessions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const returnedSession = response?.session || response?.research_session || response?.intake?.session || response;
      const conversation = response?.conversation || {};
      const session = {
        ...(returnedSession && typeof returnedSession === 'object' ? returnedSession : {}),
        conversation_id: returnedSession?.conversation_id || conversation.conversation_id || null,
        project_id: returnedSession?.project_id ?? conversation.project_id ?? null,
        title: returnedSession?.title || conversation.title || '',
      };
      const projected = sessionTaskProjection(session);
      if (!projected) throw new Error('研究会话响应缺少会话 ID');
      state.sessions = [projected, ...state.sessions.filter((item) => item.research_session_id !== projected.research_session_id)];
      state.tasks = state.sessions;
      renderTaskList();
      setText('research-create-status', `研究会话已创建：深度研究：${goal}，正在打开对应会话。`);
      const conversationId = session.conversation_id || response?.conversation_id;
      if (conversationId) openConversationFromResearch(conversationId);
      await selectTask(projected.research_task_id, projected.research_session_id);
      state.createIdempotencyKey = null;
      state.triggerMessageId = null;
    } catch (error) {
      setText('research-create-status', userError(error, '研究会话创建失败。'));
    } finally { if (button) button.disabled = false; }
  }

  function cancelTask() { beginTaskAction('cancel'); }

  function openForConversation(conversationId) {
    if (!conversationId) return;
    root.history.replaceState({}, '', `/c/${encodeURIComponent(conversationId)}#research-view`);
    state.conversationId = conversationId;
    showView();
    conversationFromUrl().catch(() => {});
    refreshWorkspace();
  }

  function openConversationFromResearch(conversationId) {
    if (!conversationId) return;
    const path = `/c/${encodeURIComponent(conversationId)}`;
    if (typeof root.openConversation === 'function') { root.openConversation(conversationId); return; }
    root.history.pushState({}, '', path);
    const event = typeof root.PopStateEvent === 'function' ? new root.PopStateEvent('popstate') : (typeof root.Event === 'function' ? new root.Event('popstate') : null);
    if (event) root.dispatchEvent?.(event);
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
    byId('research-cancel-button')?.addEventListener('click', cancelTask);
    byId('research-task-pause-button')?.addEventListener('click', () => beginTaskAction('pause'));
    byId('research-task-resume-button')?.addEventListener('click', () => beginTaskAction('resume'));
    byId('research-task-approve-button')?.addEventListener('click', () => beginTaskAction('approve'));
    byId('research-task-recover-button')?.addEventListener('click', () => beginTaskAction('recover'));
    byId('research-acquisition-confirm')?.addEventListener('click', confirmAcquisition);
    byId('research-acquisition-refresh')?.addEventListener('click', () => loadAcquisitionStatus(state.selectedTaskId));

    // Chat approval commands publish the same backend result.  Reconcile it
    // through this Tab's canonical Session/Task state instead of maintaining a
    // second task/report/SSE state machine in app.js.
    if (!root.__researchSessionCommandBridge) {
      root.__researchSessionCommandBridge = true;
      root.addEventListener('research-session-command-success', (event) => {
        const detail = event?.detail || {};
        if (!detail.sessionId || !detail.result) return;
        mergeSessionCommandResult(detail.result, detail.sessionId).catch(() => {
          setText('research-summary-text', '会话状态已更新，请刷新研究工作台。');
        });
      });
    }

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

  function bindNotifications() {
    byId('research-notifications-refresh')?.addEventListener('click', () => loadNotifications({ reset: true }));
    loadNotifications({ reset: true });
  }

  function boot(documentRef) {
    if (state.booted) return;
    state.document = documentRef; state.booted = true; state.conversationId = parseConversationId();
    if (!byId('research-view')) return;
    bindModeGuard(); bindNavigation(); bindNotifications();
    conversationFromUrl();
    loadTasks();
    if (root.location.hash === '#research-view') root.setTimeout(() => { showView(); refreshWorkspace(); }, 0);
  }

  return {
    boot, parseConversationId, statusLabel, userError, renderSafeMarkdown,
    safeArtifactUrl, artifactActionUrl, normalizeArtifact, normalizeNotification, mergeNotifications,
    notificationKindLabel, notificationPayloadText, applyNotification, loadNotifications, markNotificationRead,
    sessionTaskProjection, sessionDurationText, sessionProgressText, sessionApprovalText, sessionAgentToolText,
    acquisitionStatusLabel, acquisitionErrorText, acquisitionIsTerminal,
  };
}));
