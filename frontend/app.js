const form = document.querySelector('#chat-form');
const input = document.querySelector('#question');
const messages = document.querySelector('#messages');
const sendButton = document.querySelector('#send-button');
const modelLabel = document.querySelector('#model-label');
const statusDot = document.querySelector('.status-dot');
const modeSelect = document.querySelector('#mode-select');
const modelSelect = document.querySelector('#model-select');
const reasoningEffortSelect = document.querySelector('#reasoning-effort-select');
const modeHint = document.querySelector('#mode-hint');
const sendLabel = sendButton.innerHTML;
const workspace = document.querySelector('.workspace');
const newChatButton = document.querySelector('.new-chat');
const mobileNavToggle = document.querySelector('#mobile-nav-toggle');
const mobileNavClose = document.querySelector('#mobile-nav-close');
const mobileNavBackdrop = document.querySelector('#mobile-nav-backdrop');
const mobileSidebar = document.querySelector('#mobile-sidebar');
const settingsButton = document.querySelector('#settings-button');
const settingsDialog = document.querySelector('#settings-dialog');
const settingsForm = document.querySelector('#settings-form');
const searchUrls = document.querySelector('#search-urls');
const downloadUrls = document.querySelector('#download-urls');
const downloadDir = document.querySelector('#download-dir');
const settingsStatus = document.querySelector('#settings-status');
let activeModel = 'Ollama';
let currentModels = [];
const REASONING_EFFORTS = ['off', 'low', 'medium', 'high', 'xhigh'];
const reasoningOptionsState = { model: null, supported: null, defaultEffort: 'off', loadState: 'loading', staleCachedAt: null, correctedKeys: new Set(), loadToken: 0, lastEffort: 'off', patchSerial: 0 };

// ===== 项目会话记忆 MVP（spec-022 Task02） =====
const newProjectButton = document.querySelector('#new-project-button');
const conversationList = document.querySelector('#conversation-list');
const conversationStatus = document.querySelector('#conversation-status');
const conversationMemoryStatus = document.querySelector('#conversation-memory-status');
const conversationArchivedButton = document.querySelector('#conversation-archived-button');
const loadOlderMessagesButton = document.querySelector('#load-older-messages');
const memoryView = document.querySelector('#memory-view');
const memoryScopeSelect = document.querySelector('#memory-scope-select');
const memoryProjectSelect = document.querySelector('#memory-project-select');
const memoryProjectLabel = document.querySelector('#memory-project-label');
const memoryStatusSelect = document.querySelector('#memory-status-select');
const memoryCreateButton = document.querySelector('#memory-create-button');
const memoryRefreshButton = document.querySelector('#memory-refresh-button');
const memoryList = document.querySelector('#memory-list');
const memoryEmpty = document.querySelector('#memory-empty');
const memoryStatus = document.querySelector('#memory-status');
const systemRuleCard = document.querySelector('#system-rule-card');
const systemRuleContent = document.querySelector('#system-rule-content');
const systemRuleUpdated = document.querySelector('#system-rule-updated');
const systemRuleStatusBadge = document.querySelector('#system-rule-status-badge');
const systemRuleStatus = document.querySelector('#system-rule-status');
const systemRuleEditButton = document.querySelector('#system-rule-edit-button');
const systemRuleToggleButton = document.querySelector('#system-rule-toggle-button');
const systemRuleClearButton = document.querySelector('#system-rule-clear-button');
const systemRuleDialog = document.querySelector('#system-rule-dialog');
const systemRuleForm = document.querySelector('#system-rule-form');
const systemRuleInput = document.querySelector('#system-rule-input');
const systemRuleCount = document.querySelector('#system-rule-count');
const systemRuleEnabledInput = document.querySelector('#system-rule-enabled-input');
const systemRuleDialogStatus = document.querySelector('#system-rule-dialog-status');
const systemRuleClearDialog = document.querySelector('#system-rule-clear-dialog');
const systemRuleClearForm = document.querySelector('#system-rule-clear-form');
const systemRuleClearSubmit = document.querySelector('#system-rule-clear-submit');
const systemRuleClearStatus = document.querySelector('#system-rule-clear-status');
const projectList = document.querySelector('#project-list');
const projectTreeToggle = document.querySelector('#project-tree-toggle');
const projectTreeMenuButton = document.querySelector('#project-tree-menu-button');
const projectDialog = document.querySelector('#project-dialog');
const projectDialogForm = document.querySelector('#project-dialog-form');
const projectDialogName = document.querySelector('#project-dialog-name');
const conversationActionDialog = document.querySelector('#conversation-action-dialog');
const conversationActionForm = document.querySelector('#conversation-action-form');
const conversationActionTitle = document.querySelector('#conversation-action-dialog-title');
const conversationActionName = document.querySelector('#conversation-action-name');
const conversationActionNameField = document.querySelector('#conversation-action-name-field');
const conversationActionProjectSearchField = document.querySelector('#conversation-action-project-search-field');
const conversationActionProjectSearch = document.querySelector('#conversation-action-project-search');
const conversationActionProjectField = document.querySelector('#conversation-action-project-field');
const conversationActionProject = document.querySelector('#conversation-action-project');
const conversationActionHistoryField = document.querySelector('#conversation-action-history-field');
const conversationActionHistory = document.querySelector('#conversation-action-history');
const conversationActionStatus = document.querySelector('#conversation-action-status');
const conversationConfirmDialog = document.querySelector('#conversation-confirm-dialog');
const conversationConfirmForm = document.querySelector('#conversation-confirm-form');
const conversationConfirmTitle = document.querySelector('#conversation-confirm-title');
const conversationConfirmMessage = document.querySelector('#conversation-confirm-message');
const conversationConfirmSubmit = document.querySelector('#conversation-confirm-submit');
const conversationListMenuTrigger = document.querySelector('#conversation-archived-button');
const PROJECT_SORT_KEY = 'conversation_project_sort';
const projectState = { items: [], showArchived: false, sort: 'recent', collapsed: false, expandedProjectId: null, conversations: new Map() };
const conversationListState = { showArchived: false, cursor: null, loading: false };
const menuState = { panel: null, trigger: null, restoreFocus: null };
const dialogState = { action: null, target: null, restoreFocus: null };
try {
  const savedProjectSort = localStorage.getItem(PROJECT_SORT_KEY);
  if (savedProjectSort === 'name' || savedProjectSort === 'recent') projectState.sort = savedProjectSort;
} catch (_) { /* localStorage may be unavailable in privacy mode. */ }
const memoryState = { items: [], evidence: new Map(), loading: false };
const systemRuleState = { content: '', enabled: false, updatedAt: null, loaded: false, loading: false };
const memoryNavigationSnapshot = { scope: null, status: null, projectId: null, scrollTop: 0, projectCollapsed: false, expandedProjectId: null };
const conversationState = {
  projectId: null,
  draftProjectId: null,
  conversationId: null,
  conversation: null,
  conversationCursor: null,
  messageCursor: null,
  streamController: null,
  streamGeneration: 0,
  loadingMessages: false,
  loadingConversationId: null,
  messageLoadToken: null,
  processingHydrationQueue: Promise.resolve(),
  openToken: null,
  memoryAnalysis: new Map(),
};
const mobileDrawerState = { open: false, restoreFocus: null };

function mobileTriggerIsVisible() {
  if (!mobileNavToggle?.isConnected || mobileNavToggle.hidden) return false;
  return window.getComputedStyle(mobileNavToggle).display !== 'none';
}

function openMobileDrawer() {
  if (!mobileSidebar) return;
  mobileDrawerState.restoreFocus = document.activeElement;
  mobileDrawerState.open = true;
  mobileSidebar.classList.add('mobile-nav-open');
  if (mobileNavBackdrop) mobileNavBackdrop.hidden = false;
  if (mobileNavToggle) mobileNavToggle.setAttribute('aria-expanded', 'true');
  document.body.classList.add('mobile-nav-is-open');
  mobileNavClose?.focus();
}

function closeMobileDrawer(restoreFocus = false) {
  if (!mobileSidebar) return;
  if (!mobileDrawerState.open) return;
  mobileSidebar.classList.remove('mobile-nav-open');
  if (mobileNavBackdrop) mobileNavBackdrop.hidden = true;
  if (mobileNavToggle) mobileNavToggle.setAttribute('aria-expanded', 'false');
  document.body.classList.remove('mobile-nav-is-open');
  const target = mobileTriggerIsVisible() ? (mobileDrawerState.restoreFocus || mobileNavToggle) : null;
  mobileDrawerState.restoreFocus = null;
  mobileDrawerState.open = false;
  if (restoreFocus && target?.isConnected) target.focus();
}

function setConversationRetryStatus(text, retry) {
  if (!conversationStatus) return;
  conversationStatus.replaceChildren(document.createTextNode(text || ''));
  if (typeof retry !== 'function') return;
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'conversation-retry-button conversation-status-retry';
  button.textContent = '重试';
  button.addEventListener('click', () => {
    button.disabled = true;
    setConversationStatus('正在重试…', 'loading');
    retry();
  });
  conversationStatus.append(document.createTextNode(' '), button);
}

// ===== 模型别名（spec-008）：前端 localStorage 偏好 =====
const ALIAS_KEY = 'model_aliases';
// 隐私模式/存储禁用时的降级存储（仅本次会话有效）
const memoryAliases = new Map();

function loadAliases() {
  try {
    const parsed = JSON.parse(localStorage.getItem(ALIAS_KEY));
    if (parsed && typeof parsed === 'object') return parsed;
  } catch (e) {
    try { localStorage.removeItem(ALIAS_KEY); } catch (_) {}
  }
  const fallback = {};
  memoryAliases.forEach((value, key) => { fallback[key] = value; });
  return fallback;
}

function saveAliases(map) {
  const data = map || {};
  try {
    localStorage.setItem(ALIAS_KEY, JSON.stringify(data));
    memoryAliases.clear();
  } catch (e) {
    // localStorage 不可用时降级为内存 Map，保证本次会话内可用
    memoryAliases.clear();
    Object.keys(data).forEach((key) => memoryAliases.set(key, data[key]));
  }
}
function displayName(model) {
  const aliases = loadAliases();
  return (aliases && aliases[model]) || model;
}
let recommendedCount = 0;

settingsButton.addEventListener('click', async () => {
  settingsStatus.textContent = '正在读取设置...';
  settingsDialog.showModal();
  try {
    const response = await fetch('/api/agent/settings');
    const data = await response.json();
    searchUrls.value = (data.article_search_urls || []).join('\n');
    downloadUrls.value = (data.article_download_urls || []).join('\n');
    downloadDir.value = data.article_download_dir || '';
    settingsStatus.textContent = '';
  } catch (error) {
    settingsStatus.textContent = `读取失败：${error.message}`;
  }
});

settingsForm.addEventListener('submit', async (event) => {
  if (event.submitter?.value !== 'default') return;
  event.preventDefault();
  settingsStatus.textContent = '正在保存...';
  try {
    const response = await fetch('/api/agent/settings', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        article_search_urls: searchUrls.value.split('\n').map((value) => value.trim()).filter(Boolean),
        article_download_urls: downloadUrls.value.split('\n').map((value) => value.trim()).filter(Boolean),
        article_download_dir: downloadDir.value.trim(),
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || '保存失败');
    settingsDialog.close();
  } catch (error) {
    settingsStatus.textContent = `保存失败：${error.message}`;
  }
});

const modelEmpty = document.querySelector('#model-empty');
if (modelEmpty) { modelEmpty.hidden = false; modelEmpty.textContent = '加载中…'; }

fetch('/api/health')
  .then((response) => response.json())
  .then((data) => {
    const models = data.models || [];
    currentModels = models;
    activeModel = models.includes(data.model) ? data.model : models[0] || data.model;
    refreshModelOptions();
    modelSelect.value = activeModel;
    document.querySelector('#model-count').textContent = models.length;
    modelLabel.textContent = displayName(activeModel);
    loadReasoningOptions(activeModel, { source: 'initial' });
    statusDot.classList.add('ready');
    if (typeof renderModelList === 'function') renderModelList(models, activeModel);
    if (typeof refreshKbModelOptions === 'function') refreshKbModelOptions();
    if (typeof data.paper_discovery_enabled === 'boolean' && typeof setPaperEnabled === 'function') {
      setPaperEnabled(data.paper_discovery_enabled);
    }
  })
  .catch(() => { modelLabel.textContent = '服务未连接'; });

function addMessage(text, type) {
  const message = document.createElement('div');
  message.className = `message ${type}`;
  message.innerHTML = type === 'assistant'
    ? `<div class="avatar">O</div><div class="bubble"></div>`
    : '<div class="bubble"></div>';
  message.querySelector('.bubble').textContent = text;
  if (type === 'user') attachSystemRuleSuggestion(message, text);
  messages.appendChild(message);
  messages.scrollTop = messages.scrollHeight;
  return message;
}

// ===== spec-026 Task04：乐观建卡 + 失败终态 + 错误文案按 code 分流 =====
const REASONING_EFFORT_LABELS = { off: '关闭', low: '低', medium: '中', high: '高', xhigh: '极高' };

function reasoningEffortLabel(effort) {
  return REASONING_EFFORT_LABELS[normalizeReasoningEffort(effort)] || String(effort || '');
}

// 支持档位按 REASONING_EFFORTS 的固定序位过滤，不信任接口返回顺序，
// 保证「最高支持档」恒为序位最高者（off < low < medium < high < xhigh）。
function supportedReasoningEfforts() {
  const supported = Array.isArray(reasoningOptionsState.supported) ? reasoningOptionsState.supported : [];
  return REASONING_EFFORTS.filter((effort) => supported.includes(effort));
}

function highestSupportedReasoningEffort() {
  return supportedReasoningEfforts().at(-1) || null;
}

// 文案只由 error.code 决定；retryable 仅用于状态条颜色，不参与文案。
// 返回 { text, actions }，actions 项形如 { kind, label, effort? }。
function errorTextFor(code, message, effort = null) {
  const requested = normalizeReasoningEffort(effort || reasoningOptionsState.lastEffort || 'off');
  if (code === 'REASONING_EFFORT_UNSUPPORTED') {
    const labels = supportedReasoningEfforts().map(reasoningEffortLabel).join('、');
    const highest = highestSupportedReasoningEffort();
    return {
      text: `该模型不支持『${reasoningEffortLabel(requested)}』推理档位${labels ? `，可选：${labels}` : ''}`,
      actions: highest
        ? [
            { kind: 'switch', effort: highest, label: `用『${reasoningEffortLabel(highest)}』重发` },
            { kind: 'switchOnly', effort: highest, label: '仅切换不重发' },
          ]
        : [],
    };
  }
  if (code === 'MODEL_CAPABILITIES_UNAVAILABLE') {
    return { text: '无法确认模型能力', actions: [{ kind: 'recheck', label: '重新检测能力' }] };
  }
  if (code === 'INVALID_REASONING_EFFORT') {
    return { text: '推理档位无效', actions: [] };
  }
  if (code === 'MODEL_UNAVAILABLE') {
    return { text: '无法连接 Ollama 服务', actions: [{ kind: 'retry', label: '重新发送' }] };
  }
  // 内部错误（非网络）：主动中止 / 事件流中断等，一律用中性文案，不套用网络类措辞
  // （spec §前端错误文案映射：仅真网络错误允许出现网络类字样）。
  if (code === 'ABORTED') {
    return { text: '本轮已中止', actions: [] };
  }
  if (code === 'STREAM_INTERRUPTED') {
    return { text: '事件流中断，请重新发送', actions: [{ kind: 'retry', label: '重新发送' }] };
  }
  // 兜底：仅真网络错误（fetch 抛出 / 无响应 / 流中途连接中断）落到此处，使用网络类措辞。
  return { text: `连接失败：${message || '请求失败'}`, actions: [{ kind: 'retry', label: '重新发送' }] };
}

// 乐观建卡的占位态：卡片先出现「模型正在准备…」，meta 到达时由 clearConversationPending 清掉。
function setConversationPending(message, text = '模型正在准备…') {
  if (!message) return null;
  let pending = message.querySelector('.conversation-pending');
  if (!pending) {
    pending = document.createElement('p');
    pending.className = 'conversation-pending';
    pending.setAttribute('role', 'status');
    const bubble = message.querySelector('.bubble');
    const answer = bubble?.querySelector('.answer');
    if (answer) bubble.insertBefore(pending, answer);
    else if (bubble) bubble.appendChild(pending);
    else message.appendChild(pending);
  }
  pending.textContent = text;
  message.dataset.phase = 'pending';
  return pending;
}

function clearConversationPending(message) {
  if (!message) return;
  message.querySelector('.conversation-pending')?.remove();
  if (message.dataset.phase === 'pending') message.dataset.phase = 'streaming';
}

// 失败终态：卡片保留不消失，就地清掉占位并渲染按 code 分流的文案 + 操作按钮。
function renderConversationFailure(message, error, context = null) {
  if (!message) return null;
  clearConversationPending(message);
  message.classList.add('is-failed');
  message.dataset.phase = 'error';
  message.dataset.streamActive = 'false';
  const bubble = message.querySelector('.bubble') || message;
  let card = bubble.querySelector('.conversation-error-card');
  if (!card) {
    card = document.createElement('div');
    card.className = 'conversation-error-card';
    bubble.appendChild(card);
  }
  let notice = card.querySelector('.conversation-error-notice');
  if (!notice) {
    notice = document.createElement('p');
    notice.className = 'conversation-error-notice';
    card.appendChild(notice);
  }
  const { text, actions } = errorTextFor(error?.code, error?.message, error?.effort);
  notice.textContent = text;
  // 只有带重发上下文（发消息失败路径）才渲染操作按钮；事件流中断 / 主动中止
  // 这类没有上下文的失败只显示文案，避免出现点了没反应的按钮。
  const usableActions = context && typeof context.question === 'string' && context.question ? actions : [];
  if (!usableActions.length || card.querySelector('.conversation-error-actions')) return message;
  const group = document.createElement('div');
  group.className = 'conversation-error-actions';
  usableActions.forEach((action) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'secondary-button conversation-error-action';
    button.dataset.errorAction = action.kind;
    button.textContent = action.label;
    attachConversationErrorAction(button, action, context);
    group.appendChild(button);
  });
  card.appendChild(group);
  return message;
}

function addConversationErrorNotice(message, error, context = null) {
  if (!message) return null;
  if (message.querySelector('.conversation-error-notice')) return null;
  renderConversationFailure(message, error, context);
  return message.querySelector('.conversation-error-notice');
}

function addConversationError(error, context = null) {
  const message = addMessage('', 'assistant');
  renderConversationFailure(message, error, context);
  return message;
}

function attachConversationErrorAction(button, action, context) {
  button.addEventListener('click', () => { handleConversationErrorAction(button, action, context); });
}

async function handleConversationErrorAction(button, action, context) {
  if (!context || typeof context.question !== 'string' || !context.question) return;
  if (action.kind === 'recheck') {
    // 边界 B15：只带 refresh=1 重探能力，绝不重发用户消息。
    if (button.disabled) return;
    button.disabled = true;
    try { await loadReasoningOptions(activeModel, { refresh: true }); }
    finally { button.disabled = false; }
    return;
  }
  if (action.kind === 'switch' || action.kind === 'switchOnly') {
    const previous = reasoningOptionsState.lastEffort;
    const previousDefault = reasoningOptionsState.defaultEffort;
    const effort = setReasoningEffort(action.effort);
    persistConversationReasoningEffort(effort, previous, previousDefault);
    if (action.kind === 'switchOnly') return;
  }
  if (button.disabled) return;
  button.disabled = true;
  await sendConversationMessage(context.question, { appendUser: false, userBubble: context.userMessage });
}

function createAssistantMessage(model) {
  const message = document.createElement('div');
  message.className = 'message assistant';
  const avatar = document.createElement('div'); avatar.className = 'avatar'; avatar.textContent = 'O';
  const bubble = document.createElement('div'); bubble.className = 'bubble';
  const modelTag = document.createElement('span'); modelTag.className = 'model-tag';
  modelTag.textContent = `${model || activeModel}${modeSelect.value === 'developer' ? ' · Developer' : ''}`;
  const answer = document.createElement('div'); answer.className = 'answer md-body';
  const memoryResults = document.createElement('section'); memoryResults.className = 'conversation-memory-results'; memoryResults.hidden = true; memoryResults.setAttribute('aria-live', 'polite');
  const sources = document.createElement('section'); sources.className = 'conversation-sources'; sources.hidden = true; sources.setAttribute('aria-label', '参考来源');
  bubble.append(modelTag, answer, memoryResults, sources);
  message.append(avatar, bubble);
  message.dataset.lastEventSeq = '0';
  message.dataset.reasoningEffort = normalizeReasoningEffort(reasoningOptionsState.lastEffort || 'off');
  messages.appendChild(message);
  messages.scrollTop = messages.scrollHeight;
  return message;
}

function addCandidate(candidate, taskId) {
  const message = document.createElement('div');
  message.className = 'message assistant candidate-message';
  message.innerHTML = '<div class="avatar">↗</div><div class="bubble candidate-bubble"><strong class="candidate-title"></strong><span class="candidate-meta"></span><a class="candidate-link" target="_blank" rel="noreferrer">打开文章页面</a><button class="candidate-action" type="button">选择下载</button></div>';
  message.querySelector('.candidate-title').textContent = candidate.title || '未命名文章';
  message.querySelector('.candidate-meta').textContent = [candidate.source_name, candidate.year, candidate.doi].filter(Boolean).join(' · ');
  if (candidate.article_url) message.querySelector('.candidate-link').href = candidate.article_url;
  else message.querySelector('.candidate-link').remove();
  const action = message.querySelector('.candidate-action');
  action.dataset.taskId = taskId;
  action.dataset.candidateId = candidate.candidate_id;
  action.textContent = candidate.requires_login ? '登录后下载' : '选择下载';
  messages.appendChild(message);
  messages.scrollTop = messages.scrollHeight;
}

function showSkillHint(skill) {
  const hint = document.querySelector('#skill-hint');
  if (!hint) return;
  hint.textContent = `已选取 ${skill} 技能，负责本次论文下载`;
  hint.hidden = false;
}

function clearSkillHint() {
  const hint = document.querySelector('#skill-hint');
  if (!hint) return;
  hint.textContent = '';
  hint.hidden = true;
}

modeSelect.addEventListener('change', () => {
  modeHint.textContent = modeSelect.value === 'developer'
    ? 'Developer 模式 · 单次最多 20,000 字 · 显示调试信息'
    : 'Normal 模式 · 单次最多 2,000 字';
});

modelSelect.addEventListener('change', () => {
  activeModel = modelSelect.value;
  modelLabel.textContent = displayName(activeModel);
  loadReasoningOptions(activeModel, { source: 'model-switch' });
});

function normalizeReasoningEffort(value, fallback = 'off') {
  const effort = String(value || '').trim().toLowerCase();
  return REASONING_EFFORTS.includes(effort) ? effort : fallback;
}

// P1-1：发出消息时选择 reasoning_effort。能力探测（loading）期间 select 的选中值尚未经
// 后端确认，绝不能直接发出——否则模型不支持该档位会触发后端 409（即 spec 缺陷 C）。
// loading 期间回落到所有模型都支持的 'off'；非 loading 用已确认的 select 值，空则回落 lastEffort。
// 注意：loading 期间选择器被禁用，用户无法显式选档，回落 'off' 不构成对 B11（用户显式选择）的静默改写。
function pickSendReasoningEffort(loadState, selectValue, lastEffort) {
  if (loadState === 'loading') return 'off';
  return normalizeReasoningEffort(selectValue || normalizeReasoningEffort(lastEffort || 'off'));
}

function setReasoningEffort(value, { remember = true } = {}) {
  const effort = normalizeReasoningEffort(value, reasoningOptionsState.defaultEffort || 'off');
  reasoningOptionsState.lastEffort = effort;
  if (reasoningEffortSelect) reasoningEffortSelect.value = effort;
  if (remember) reasoningOptionsState.defaultEffort = effort;
  return effort;
}

function syncReasoningEffortOptions(loadState, supported, staleCachedAt) {
  if (!reasoningEffortSelect) return;
  // B14：能力加载中（loading）选择器整体禁用，避免「全灰只剩 off」的闪烁。
  if (loadState === 'loading') {
    reasoningEffortSelect.disabled = true;
    [...reasoningEffortSelect.options].forEach((option) => {
      option.disabled = true;
      option.setAttribute('aria-disabled', 'true');
      option.title = '';
    });
    renderReasoningEffortState(loadState, staleCachedAt);
    return;
  }
  // 非 loading 态：整体恢复可交互（个别不支持的档位在下面按 supported 禁用）。
  reasoningEffortSelect.disabled = false;
  const known = loadState === 'known' || loadState === 'stale';
  const supportedSet = new Set(known && Array.isArray(supported) && supported.length ? supported : ['off']);
  supportedSet.add('off');
  const disabledTitle = loadState === 'unknown' ? '能力未确认，暂不可选此档位' : '该模型不支持此档位';
  [...reasoningEffortSelect.options].forEach((option) => {
    const enabled = supportedSet.has(option.value);
    option.disabled = !enabled;
    option.setAttribute('aria-disabled', enabled ? 'false' : 'true');
    option.title = enabled ? '' : disabledTitle;
  });
  renderReasoningEffortState(loadState, staleCachedAt);
}

// 选中值校正（B9/B10）：能力已知（known/stale）且当前选中档不在 supported_efforts 内时，
// 改到该模型支持的最高档，并在档位选择器旁弹一次性提示。
// B11 红线：reason==='user'（用户显式 change）一律不改档；unknown 也不静默降级。
function reconcileEffortWithCapabilities(reason, desired) {
  const desiredNorm = normalizeReasoningEffort(desired || 'off');
  if (reason === 'user') return desiredNorm;
  if (reasoningOptionsState.loadState === 'unknown') return desiredNorm;
  const supported = supportedReasoningEfforts();
  if (supported.includes(desiredNorm)) return desiredNorm;
  const highest = highestSupportedReasoningEffort();
  if (!highest || highest === desiredNorm) return desiredNorm;
  const key = `${reasoningOptionsState.model}|${conversationState.conversationId || ''}`;
  if (!reasoningOptionsState.correctedKeys.has(key)) {
    reasoningOptionsState.correctedKeys.add(key);
    showEffortCorrectionNotice(reasoningEffortLabel(desiredNorm), reasoningEffortLabel(highest));
  }
  return highest;
}

// 档位选择器旁的状态条（四态）。loading 整体禁用 + 检测中；unknown 能力未确认 + 重新检测；
// stale 沿用旧结果 + 重新检测；known 不显示额外文案（B12/B13/B14）。
function renderReasoningEffortState(loadState, staleCachedAt) {
  const stateEl = document.querySelector('#reasoning-effort-state');
  if (!stateEl) return;
  stateEl.textContent = '';
  stateEl.className = 'reasoning-effort-state';
  stateEl.hidden = false;
  if (loadState === 'loading') {
    stateEl.textContent = '检测能力中…';
    stateEl.classList.add('is-loading');
    return;
  }
  if (loadState === 'unknown') {
    stateEl.textContent = '能力未确认';
    stateEl.classList.add('is-unknown');
    appendRecheckButton(stateEl);
    return;
  }
  if (loadState === 'stale') {
    const when = staleCachedAt ? formatStaleTime(staleCachedAt) : '';
    stateEl.textContent = when ? `沿用 ${when} 前的能力检测结果` : '沿用旧能力检测结果';
    stateEl.classList.add('is-stale');
    appendRecheckButton(stateEl);
    return;
  }
  stateEl.hidden = true;
}

function appendRecheckButton(stateEl) {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'secondary-button reasoning-effort-recheck';
  btn.textContent = '重新检测';
  btn.setAttribute('aria-label', '重新检测模型能力');
  btn.addEventListener('click', () => { loadReasoningOptions(activeModel, { refresh: true }); });
  stateEl.appendChild(btn);
}

function formatStaleTime(cachedAt) {
  const then = new Date(cachedAt).getTime();
  if (!Number.isFinite(then)) return '';
  const diff = Date.now() - then;
  if (diff < 0) return '';
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return `${sec} 秒`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} 分钟`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} 小时`;
  return `${Math.floor(hr / 24)} 天`;
}

function showEffortCorrectionNotice(fromLabel, toLabel) {
  const el = document.querySelector('#reasoning-effort-notice');
  if (!el) return;
  el.textContent = `已因模型能力从『${fromLabel}』调整为『${toLabel}』`;
  el.hidden = false;
  clearTimeout(showEffortCorrectionNotice._timer);
  showEffortCorrectionNotice._timer = setTimeout(() => { el.hidden = true; }, 4000);
}

async function loadReasoningOptions(model, { selectedEffort = null, refresh = false, source = null } = {}) {
  if (!reasoningEffortSelect || !model) return;
  const loadToken = ++reasoningOptionsState.loadToken;
  const requestedModel = String(model);
  reasoningOptionsState.loadState = 'loading';
  syncReasoningEffortOptions('loading', null, null);
  try {
    const response = await fetch(`/api/chat/reasoning-options?model=${encodeURIComponent(requestedModel)}${refresh ? '&refresh=1' : ''}`);
    let data = null;
    try { data = await response.json(); } catch (_) { data = null; }
    if (!response.ok) throw new Error(conversationError(data, '思考档位暂不可用'));
    if (loadToken !== reasoningOptionsState.loadToken || activeModel !== requestedModel) return;
    reasoningOptionsState.model = requestedModel;
    reasoningOptionsState.supported = Array.isArray(data?.supported_efforts) ? data.supported_efforts : null;
    const capSource = data?.source;
    if (capSource === 'stale') {
      reasoningOptionsState.loadState = 'stale';
      reasoningOptionsState.staleCachedAt = data?.cached_at || null;
    } else if (capSource === 'unknown') {
      reasoningOptionsState.loadState = 'unknown';
      reasoningOptionsState.staleCachedAt = null;
    } else {
      reasoningOptionsState.loadState = 'known';
      reasoningOptionsState.staleCachedAt = data?.cached_at || null;
    }
    const backendDefault = normalizeReasoningEffort(data?.default_effort, null);
    reasoningOptionsState.defaultEffort = backendDefault || highestSupportedReasoningEffort() || 'off';
    syncReasoningEffortOptions(reasoningOptionsState.loadState, reasoningOptionsState.supported, reasoningOptionsState.staleCachedAt);
    if (reasoningOptionsState.loadState === 'unknown') {
      setReasoningEffort('off', { remember: false });
    } else {
      // 区分调用来源（spec 026 Task05 缺陷修复）：
      // - 刷新（重新检测能力，source==='refresh'）：保留用户当前选中的档位（lastEffort），
      //   越界再由 reconcileEffortWithCapabilities 校正到支持的最高档。
      // - 首次加载 / 切换模型 / 载入会话：用户未显式选过时优先后端 default_effort
      //   （Task02/03 已保证它 == 该模型支持的最高档），不沿用 lastEffort——其初值为
      //   'off'，会在全新页面首次加载时错误地压过低档。
      const callSource = source || (refresh ? 'refresh' : 'initial');
      let desired;
      if (callSource === 'refresh') {
        // 重新检测：保留用户当前选中档位（lastEffort），越界再交由 reconcile 校正
        desired = selectedEffort || reasoningOptionsState.lastEffort || conversationState.conversation?.reasoning_effort || reasoningOptionsState.defaultEffort || 'off';
      } else if (callSource === 'initial') {
        // 首屏：优先后端 default_effort（= 该模型支持的最高档），不沿用切换前选中的档位
        // （其初值为 'off'，会在全新页面首次加载时错误地压过低档）
        desired = selectedEffort || reasoningOptionsState.defaultEffort || 'off';
      } else {
        // model-switch / session：保留用户在切换前已选的档位（此刻 lastEffort 仍是切换前的值，
        // 尚未被下方 setReasoningEffort 覆盖）。交由 reconcile 校正到新模型支持的最高档并弹一次性提示，
        // 避免“显式选择被无声丢弃且无提示”的静默降档，违反 Spec024 红线（B9）。
        // 注意 defaultEffort 已在上方被重置为新模型默认值，不能在此用它兜底——否则显式选择会
        // 被当作“合法默认值”跳过校正与提示。
        desired = selectedEffort || reasoningOptionsState.lastEffort || reasoningOptionsState.defaultEffort || 'off';
      }
      const corrected = reconcileEffortWithCapabilities('load', desired);
      setReasoningEffort(corrected, { remember: false });
    }
  } catch (_) {
    if (loadToken !== reasoningOptionsState.loadToken || activeModel !== requestedModel) return;
    reasoningOptionsState.model = requestedModel;
    reasoningOptionsState.supported = null;
    reasoningOptionsState.defaultEffort = 'off';
    reasoningOptionsState.loadState = 'unknown';
    reasoningOptionsState.staleCachedAt = null;
    syncReasoningEffortOptions('unknown', null, null);
    setReasoningEffort('off', { remember: false });
  }
}

async function persistConversationReasoningEffort(effort, previousEffort, previousDefaultEffort) {
  const conversationId = conversationState.conversationId;
  if (!conversationId) return;
  const serial = ++reasoningOptionsState.patchSerial;
  try {
    const data = await conversationFetch(`/api/conversations/${encodeURIComponent(conversationId)}/reasoning`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reasoning_effort: effort }),
    });
    if (serial !== reasoningOptionsState.patchSerial || conversationState.conversationId !== conversationId) return;
    conversationState.conversation = { ...(conversationState.conversation || {}), ...(data || {}), reasoning_effort: data?.reasoning_effort || effort };
  } catch (error) {
    if (serial !== reasoningOptionsState.patchSerial || conversationState.conversationId !== conversationId) return;
    reasoningOptionsState.defaultEffort = previousDefaultEffort;
    setReasoningEffort(previousEffort, { remember: false });
    setConversationStatus(`思考档位更新失败：${error.message}`, 'error');
  }
}

reasoningEffortSelect?.addEventListener('change', () => {
  const previous = reasoningOptionsState.lastEffort;
  const previousDefault = reasoningOptionsState.defaultEffort;
  const effort = setReasoningEffort(reasoningEffortSelect.value);
  persistConversationReasoningEffort(effort, previous, previousDefault);
});

function conversationError(data, fallback = '请求失败') {
  const detail = data?.detail;
  if (typeof detail === 'object' && detail?.message) return detail.message;
  if (typeof detail === 'string') return detail;
  return data?.message || fallback;
}

async function conversationFetch(url, options = {}) {
  const response = await fetch(url, options);
  let data = null;
  try { data = await response.json(); } catch (_) { data = null; }
  if (!response.ok) {
    const error = new Error(conversationError(data));
    error.code = data?.detail?.code || data?.code;
    error.status = response.status;
    error.retryable = data?.detail?.retryable ?? data?.retryable;
    throw error;
  }
  return data;
}

const CONVERSATION_STATUS_AUTO_CLEAR_MS = 4000;
const CONVERSATION_STATUS_PERSISTENT_STATES = new Set(['error', 'loading']);
let conversationStatusTimer = null;
/* ---------- Spec025：上下文占比与手动压缩 ----------
 * 数据来自 GET /api/conversations/{id}/context-usage，只在「加载会话后」与
 * 「每轮消息完成后」刷新，不做常驻轮询；手动压缩后做一次有上限的跟随刷新
 * （终止即停，最多 ~12s），仅用于把「压缩中」中态收口。
 */
const contextMeter = document.getElementById('context-meter');
const contextRing = document.getElementById('context-ring');
const contextRingFill = document.getElementById('context-ring-fill');
const contextMeterText = document.getElementById('context-meter-text');
const contextMeterValue = document.getElementById('context-meter-value');
const contextCompactButton = document.getElementById('context-compact-button');
const contextStatus = document.getElementById('context-status');
const contextState = { inflight: false, followTimer: null, followTries: 0 };

function setContextStatus(text) {
  if (!contextStatus) return;
  const value = text || '';
  contextStatus.textContent = value;
  contextStatus.hidden = !value;
}

// r=15 的圆周长 2πr ≈ 94.25，与 CSS 的 stroke-dasharray 保持一致。
const CONTEXT_RING_CIRCUMFERENCE = 2 * Math.PI * 15;

function renderContextUsage(usage) {
  if (!contextMeter || !contextRing || !contextRingFill || !contextMeterText) return;
  // 无会话时保留占位（visibility 隐藏），避免底部行抖动，同时移出 Tab 焦点。
  const idle = !usage;
  contextMeter.classList.toggle('is-idle', idle);
  if (contextCompactButton && !contextState.inflight) contextCompactButton.tabIndex = idle ? -1 : 0;
  if (idle) {
    if (contextMeterValue) contextMeterValue.textContent = '0%';
    contextRing.setAttribute('aria-valuenow', '0');
    return;
  }
  const ratio = Number(usage.ratio);
  const safe = Number.isFinite(ratio) ? Math.min(1, Math.max(0, ratio)) : 0;
  const percent = Math.round(safe * 100);
  contextRingFill.style.strokeDasharray = `${CONTEXT_RING_CIRCUMFERENCE.toFixed(2)}`;
  contextRingFill.style.strokeDashoffset = `${(CONTEXT_RING_CIRCUMFERENCE * (1 - safe)).toFixed(2)}`;
  contextRing.setAttribute('aria-valuenow', String(percent));
  if (contextMeterValue) contextMeterValue.textContent = `${percent}%`;
  const status = usage.compaction_status;
  if (status === 'queued' || status === 'running') setContextStatus('压缩中…');
  else if (status === 'failed') setContextStatus('上次压缩失败，可重试');
  else if (status === 'done') setContextStatus('');
}

async function loadContextUsage() {
  const conversationId = conversationState.conversationId;
  if (!conversationId) { renderContextUsage(null); return null; }
  try {
    const usage = await conversationFetch(`/api/conversations/${encodeURIComponent(conversationId)}/context-usage`);
    renderContextUsage(usage);
    return usage;
  } catch (error) {
    renderContextUsage(null);
    return null;
  }
}

function stopContextFollow() {
  if (contextState.followTimer) { clearTimeout(contextState.followTimer); contextState.followTimer = null; }
  contextState.followTries = 0;
}

function followContextCompaction() {
  stopContextFollow();
  const tick = async () => {
    const usage = await loadContextUsage();
    contextState.followTimer = null;
    if (!usage) { stopContextFollow(); return; }
    const status = usage.compaction_status;
    if (status === 'queued' || status === 'running') {
      contextState.followTries += 1;
      if (contextState.followTries >= 6) { setContextStatus('压缩仍在进行，稍后自动生效'); stopContextFollow(); return; }
      contextState.followTimer = setTimeout(tick, 2000);
      return;
    }
    stopContextFollow();
  };
  contextState.followTimer = setTimeout(tick, 1200);
}

async function compactConversationContext() {
  if (!contextCompactButton || contextState.inflight) return;
  const conversationId = conversationState.conversationId;
  if (!conversationId) return;
  contextState.inflight = true;
  contextCompactButton.disabled = true;
  const original = contextCompactButton.textContent;
  contextCompactButton.textContent = '压缩中';
  setContextStatus('已触发压缩');
  try {
    await conversationFetch(`/api/conversations/${encodeURIComponent(conversationId)}/compactions`, { method: 'POST' });
    followContextCompaction();
  } catch (error) {
    if (error && error.status === 409) setContextStatus('压缩进行中');
    else setContextStatus(error && error.message ? error.message : '压缩失败');
  } finally {
    contextState.inflight = false;
    if (contextCompactButton) { contextCompactButton.disabled = false; contextCompactButton.textContent = original; }
  }
}

if (contextCompactButton) contextCompactButton.addEventListener('click', compactConversationContext);

// 输入框：3 行起步，随内容自适应增长到上限（与 CSS max-height 一致），避免底部行被推高。
const COMPOSER_INPUT_MAX_HEIGHT = 176;
function autoGrowInput() {
  if (!input) return;
  input.style.height = 'auto';
  input.style.height = `${Math.min(input.scrollHeight, COMPOSER_INPUT_MAX_HEIGHT)}px`;
}
if (input) {
  input.addEventListener('input', autoGrowInput);
  autoGrowInput();
}

function setConversationStatus(text, state = '') {
  if (!conversationStatus) return;
  if (conversationStatusTimer) { clearTimeout(conversationStatusTimer); conversationStatusTimer = null; }
  conversationStatus.textContent = text || '';
  if (state) conversationStatus.dataset.state = state;
  else delete conversationStatus.dataset.state;
  const message = text || '';
  if (message && !CONVERSATION_STATUS_PERSISTENT_STATES.has(state)) {
    conversationStatusTimer = setTimeout(() => {
      conversationStatusTimer = null;
      if (!conversationStatus) return;
      conversationStatus.textContent = '';
      delete conversationStatus.dataset.state;
    }, CONVERSATION_STATUS_AUTO_CLEAR_MS);
  }
}

function conversationTime(item) {
  const time = Date.parse(item?.created_at || '');
  return Number.isFinite(time) ? time : 0;
}

function orderConversationMessages(items) {
  const source = Array.isArray(items) ? items.filter(Boolean) : [];
  const byId = new Map(source.filter((item) => item.message_id).map((item) => [item.message_id, item]));
  const children = new Map();
  source.forEach((item) => {
    if (!item.parent_message_id || !byId.has(item.parent_message_id)) return;
    const list = children.get(item.parent_message_id) || [];
    list.push(item);
    children.set(item.parent_message_id, list);
  });
  const chronological = (left, right) => conversationTime(left) - conversationTime(right);
  source.forEach((item) => children.get(item.message_id)?.sort(chronological));
  const roots = source.filter((item) => !item.parent_message_id || !byId.has(item.parent_message_id));
  roots.sort(chronological);
  const ordered = [];
  const visited = new Set();
  const visit = (item) => {
    if (!item || visited.has(item.message_id)) return;
    visited.add(item.message_id);
    ordered.push(item);
    (children.get(item.message_id) || []).forEach((child) => {
      // A linear turn is user -> its assistant. Preserve any tool/orphan child
      // after the direct answer without guessing from timestamps.
      visit(child);
    });
  };
  roots.forEach(visit);
  source.slice().sort(chronological).forEach(visit);
  return ordered;
}

function formatReasoningDuration(durationMs) {
  const value = Number(durationMs);
  if (!Number.isFinite(value) || value < 0) return '';
  return ` · 用时 ${(value / 1000).toFixed(value >= 10000 ? 0 : 1)} 秒`;
}

const REASONING_PROTOCOL_MARKERS = [
  '<think>', '</think>', '<analysis>', '</analysis>', '<reasoning>', '</reasoning>',
  '[INST]', '[/INST]', '<<SYS>>', '<</SYS>>',
  '<|assistant|>', '<|user|>', '<|system|>', '<|im_start|>', '<|im_end|>', '<|endoftext|>',
  '<|start_header_id|>', '<|end_header_id|>', '<|eot_id|>', '<|eom_id|>',
  '[[assistant]]', '[[user]]', '[[system]]', '[[thinking]]', '[[answer]]',
  '### System:', '### User:', '### Assistant:',
  '\nassistant:', '\nuser:', '\nsystem:', 'assistant:', 'user:', 'system:',
];
const reasoningFilters = new WeakMap();
const KNOWN_CONVERSATION_EVENT_TYPES = new Set(['meta', 'progress', 'memory', 'reconnect', 'skill_activation', 'intake', 'reasoning_started', 'reasoning_delta', 'reasoning_completed', 'token', 'sources', 'error', 'done']);

function createReasoningFilter() {
  let carry = '';
  const isControl = (char) => /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/.test(char);
  const isBareRoleMarker = (marker) => ['assistant:', 'user:', 'system:'].includes(marker);
  const markerAt = (value, index) => REASONING_PROTOCOL_MARKERS.find((marker) => value.startsWith(marker, index) && (!isBareRoleMarker(marker) || index === 0));
  const hasMarkerPrefix = (value, index) => {
    const suffix = value.slice(index);
    return suffix.length > 0 && REASONING_PROTOCOL_MARKERS.some((marker) => marker.startsWith(suffix) && (!isBareRoleMarker(marker) || index === 0));
  };
  return {
    push(value, { final = false } = {}) {
      const input = carry + String(value || '');
      carry = '';
      let output = '';
      let index = 0;
      while (index < input.length) {
        const marker = markerAt(input, index);
        if (marker) { index += marker.length; continue; }
        if (!final && hasMarkerPrefix(input, index)) { carry = input.slice(index); break; }
        const char = input[index];
        if (!isControl(char)) output += char;
        index += 1;
      }
      if (final && carry) {
        for (const char of carry) if (!isControl(char)) output += char;
        carry = '';
      }
      return output;
    },
  };
}

function filterVisibleReasoning(value) {
  return createReasoningFilter().push(value, { final: true });
}

function appendConversationReasoningText(panel, value) {
  if (!panel || !value) return;
  let filter = reasoningFilters.get(panel);
  if (!filter) { filter = createReasoningFilter(); reasoningFilters.set(panel, filter); }
  const visible = filter.push(value);
  if (!visible) return;
  const target = panel.querySelector('.conversation-reasoning-content');
  if (target) {
    target.appendChild(document.createTextNode(visible));
    panel.dataset.hasContent = 'true';
  }
}

function flushConversationReasoningText(panel) {
  if (!panel) return;
  let filter = reasoningFilters.get(panel);
  if (!filter) return;
  const visible = filter.push('', { final: true });
  if (!visible) return;
  const target = panel.querySelector('.conversation-reasoning-content');
  if (target) {
    target.appendChild(document.createTextNode(visible));
    panel.dataset.hasContent = 'true';
  }
}

function reasoningPanelStatusText(status, durationMs) {
  if (status === 'running') return '正在思考…';
  if (status === 'failed') return '思考失败';
  if (status === 'interrupted') return '思考已中止';
  if (status === 'completed') return `思考完成${formatReasoningDuration(durationMs)}`;
  return '思考草稿';
}

function createConversationReasoning(assistantMessage, { effort = 'xhigh', status = 'running', content = '', durationMs = null, truncated = false } = {}) {
  if (!assistantMessage || normalizeReasoningEffort(effort) === 'off') return null;
  const existing = assistantMessage.querySelector('.conversation-reasoning');
  if (existing) return existing;
  const reasoningFilter = createReasoningFilter();
  const visibleContent = reasoningFilter.push(content, { final: status !== 'running' });
  const panel = document.createElement('section');
  panel.className = 'conversation-reasoning';
  panel.dataset.status = status;
  panel.dataset.effort = normalizeReasoningEffort(effort);
  panel.dataset.hasContent = visibleContent ? 'true' : 'false';
  panel.setAttribute('aria-label', '思考草稿');
  panel.setAttribute('aria-busy', status === 'running' ? 'true' : 'false');
  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'conversation-reasoning-toggle';
  toggle.setAttribute('aria-expanded', status === 'running' ? 'true' : 'false');
  toggle.dataset.userToggled = 'false';
  const title = document.createElement('span');
  title.className = 'conversation-reasoning-title';
  title.textContent = '思考草稿';
  const summary = document.createElement('span');
  summary.className = 'conversation-reasoning-summary';
  summary.textContent = reasoningPanelStatusText(status, durationMs);
  toggle.append(title, summary);
  const body = document.createElement('div');
  body.className = 'conversation-reasoning-body';
  body.hidden = status !== 'running';
  const notice = document.createElement('p');
  notice.className = 'conversation-reasoning-notice';
  notice.textContent = '思考草稿可能不准确';
  const text = document.createElement('div');
  text.className = 'conversation-reasoning-content';
  text.setAttribute('aria-live', 'polite');
  text.textContent = visibleContent;
  if (truncated) {
    const truncatedNotice = document.createElement('p');
    truncatedNotice.className = 'conversation-reasoning-truncated';
    truncatedNotice.textContent = '（思考草稿过长，已折叠部分内容）';
    body.append(notice, text, truncatedNotice);
  } else {
    body.append(notice, text);
  }
  toggle.addEventListener('click', () => {
    const expanded = toggle.getAttribute('aria-expanded') === 'true';
    toggle.setAttribute('aria-expanded', expanded ? 'false' : 'true');
    toggle.dataset.userToggled = 'true';
    body.hidden = expanded;
  });
  panel.append(toggle, body);
  reasoningFilters.set(panel, reasoningFilter);
  const bubble = assistantMessage.querySelector('.bubble');
  const answer = bubble?.querySelector('.answer');
  if (answer) bubble.insertBefore(panel, answer);
  else if (bubble) bubble.appendChild(panel);
  return panel;
}

function updateConversationReasoning(panel, { status, content, durationMs = null, completedAt = null } = {}) {
  if (!panel || ['terminal', 'completed', 'failed', 'interrupted'].includes(panel.dataset.status)) return;
  if (content) {
    appendConversationReasoningText(panel, content);
  }
  if (status) {
    panel.dataset.status = status;
    panel.setAttribute('aria-busy', status === 'running' ? 'true' : 'false');
    const summary = panel.querySelector('.conversation-reasoning-summary');
    if (summary) summary.textContent = reasoningPanelStatusText(status, durationMs);
    if (status !== 'running') {
      const toggle = panel.querySelector('.conversation-reasoning-toggle');
      const body = panel.querySelector('.conversation-reasoning-body');
      if (toggle && body) {
        toggle.setAttribute('aria-expanded', 'false');
        body.hidden = true;
      }
    }
    if (completedAt) panel.dataset.completedAt = completedAt;
  }
}

function finalizeConversationReasoning(panel, status = 'completed', durationMs = null) {
  if (!panel) return;
  const current = panel.dataset.status;
  if (current === 'completed' && status !== 'completed') return;
  if (['completed', 'failed', 'interrupted'].includes(current) && status === 'running') return;
  if (status === 'completed') flushConversationReasoningText(panel);
  updateConversationReasoning(panel, { status, durationMs });
  panel.dataset.status = status;
  panel.setAttribute('aria-busy', 'false');
  const toggle = panel.querySelector('.conversation-reasoning-toggle');
  const body = panel.querySelector('.conversation-reasoning-body');
  if (toggle && body) {
    toggle.setAttribute('aria-expanded', 'false');
    body.hidden = true;
  }
}

function acceptConversationEvent(assistantMessage, eventData) {
  if (!assistantMessage || !eventData) return false;
  const finalEnvelope = ['done', 'error'].includes(eventData.type);
  if (assistantMessage.dataset.doneSeen === 'true') return false;
  if (assistantMessage.dataset.terminal === 'true' && assistantMessage.dataset.sequenceGap !== 'true') return false;
  if ((assistantMessage.dataset.sequenceGap === 'true' || assistantMessage.dataset.errorSeen === 'true') && !finalEnvelope) return false;
  if (eventData.type === 'meta' && assistantMessage.dataset.metaSeen === 'true') return false;
  const seq = Number(eventData.event_seq);
  if (!Number.isInteger(seq) || seq < 1) {
    assistantMessage.dataset.sequenceGap = 'true';
    assistantMessage.dataset.terminal = 'true';
    assistantMessage.dataset.status = 'interrupted';
    finalizeConversationReasoning(assistantMessage.querySelector('.conversation-reasoning'), 'interrupted');
    addConversationErrorNotice(assistantMessage, Object.assign(new Error('事件流中断：缺少有效事件序号'), { code: 'STREAM_INTERRUPTED', retryable: true }));
    return false;
  }
  const last = Number(assistantMessage.dataset.lastEventSeq || 0);
  if (seq <= last) return false;
  if (last > 0 && seq > last + 1) {
    assistantMessage.dataset.sequenceGap = 'true';
    assistantMessage.dataset.terminal = 'true';
    assistantMessage.dataset.status = 'interrupted';
    const panel = assistantMessage.querySelector('.conversation-reasoning');
    finalizeConversationReasoning(panel, 'interrupted');
    addConversationErrorNotice(assistantMessage, Object.assign(new Error('事件流中断'), { code: 'STREAM_INTERRUPTED', retryable: true }));
    if (!finalEnvelope) return false;
  }
  assistantMessage.dataset.lastEventSeq = String(seq);
  return true;
}

function markConversationEventTerminal(assistantMessage, status) {
  if (!assistantMessage) return;
  if (['completed', 'failed', 'interrupted'].includes(status)) {
    if (assistantMessage.dataset.sequenceGap === 'true') status = 'interrupted';
    assistantMessage.dataset.terminal = 'true';
    assistantMessage.dataset.status = status;
  }
}

function renderConversationMessage(item) {
  const message = document.createElement('div');
  const role = item.role === 'user' ? 'user' : item.role === 'tool' ? 'tool' : 'assistant';
  message.className = `message ${role}`;
  if (item.message_id) message.dataset.messageId = item.message_id;
  if (item.parent_message_id) message.dataset.parentMessageId = item.parent_message_id;
  if (item.status === 'failed') message.classList.add('is-failed');
  if (item.status === 'interrupted') message.classList.add('is-interrupted');
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  if (role === 'user' || role === 'tool') {
    bubble.textContent = item.content || '';
    if (role === 'user') attachSystemRuleSuggestion(message, item.content || '');
    message.appendChild(bubble);
    return message;
  }
  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.textContent = 'O';
  const model = document.createElement('span');
  model.className = 'model-tag';
  model.textContent = item.model || activeModel;
  bubble.appendChild(model);
  const historicalReasoningContent = String(item.reasoning_content || '');
  const historicalReasoning = filterVisibleReasoning(historicalReasoningContent);
  const answer = document.createElement('div');
  answer.className = 'answer md-body';
  setConversationAnswer(answer, item.content || '');
  bubble.append(answer);
  const memoryResults = document.createElement('section');
  memoryResults.className = 'conversation-memory-results';
  memoryResults.hidden = true;
  memoryResults.setAttribute('aria-live', 'polite');
  bubble.appendChild(memoryResults);
  const sources = document.createElement('section');
  sources.className = 'conversation-sources';
  sources.hidden = true;
  sources.setAttribute('aria-label', '参考来源');
  bubble.appendChild(sources);
  message.append(avatar, bubble);
  const historicalIntake = item.intake || item.research_intake;
  if (historicalIntake && typeof historicalIntake === 'object') {
    const historicalPanel = updateConversationIntake(message, historicalIntake);
    const historicalStatus = item.status === 'failed' || historicalIntake.status === 'failed' ? 'failed' : 'completed';
    finalizeConversationIntake(historicalPanel, historicalStatus);
  }
  if (historicalReasoning) {
    createConversationReasoning(message, {
      effort: item.reasoning_effort || 'xhigh',
      status: item.reasoning_status === 'running' ? 'running' : (item.reasoning_status || 'completed'),
      content: historicalReasoningContent,
      durationMs: item.reasoning_duration_ms,
      truncated: Boolean(item.reasoning_truncated),
    });
  }
  message.dataset.lastEventSeq = String(Number(item.last_event_seq) || 0);
  return message;
}

function createConversationProcessing(assistantMessage) {
  const existing = assistantMessage?.querySelector('.conversation-processing');
  if (existing) return existing;
  const processing = document.createElement('section');
  processing.className = 'conversation-processing';
  processing.setAttribute('aria-label', '处理过程');
  processing.setAttribute('aria-busy', 'true');
  processing.dataset.running = 'true';
  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'conversation-processing-toggle';
  toggle.setAttribute('aria-expanded', 'true');
  toggle.dataset.userToggled = 'false';
  toggle.textContent = '处理过程';
  const list = document.createElement('div');
  list.className = 'conversation-processing-list';
  toggle.addEventListener('click', () => {
    const expanded = toggle.getAttribute('aria-expanded') === 'true';
    toggle.setAttribute('aria-expanded', expanded ? 'false' : 'true');
    toggle.dataset.userToggled = 'true';
    list.hidden = expanded;
  });
  processing.append(toggle, list);
  const bubble = assistantMessage.querySelector('.bubble');
  const answer = bubble.querySelector('.answer');
  if (answer) bubble.insertBefore(processing, answer);
  else bubble.appendChild(processing);
  return processing;
}

function setConversationAnswer(element, content) {
  element.innerHTML = renderMarkdown(content);
}

const INTAKE_FIELD_LABELS = {
  topic: '主题', objective: '研究目标', time_range: '时间范围', language: '语言',
  sources: '来源', depth: '研究深度', output: '输出格式', citations: '引用方式', constraints: '约束',
};
const INTAKE_SOURCE_LABELS = {
  user_explicit: '用户明确', context_inferred: '上下文推断', system_default: '系统默认',
};
const INTAKE_CONFIRMATION_LABELS = {
  unconfirmed: '待确认', confirmed: '已确认', not_required: '无需确认',
};
const INTAKE_CHOICE_LABELS = {
  modify_current: '修改当前研究', cancel_then_new: '取消后新建', new_conversation: '在新会话研究',
};

function intakeFieldValue(valueJson) {
  if (valueJson === null || valueJson === undefined) return '';
  if (typeof valueJson !== 'string') return valueJson;
  try { return JSON.parse(valueJson); } catch (_) { return valueJson; }
}

function intakeDisplayValue(valueJson) {
  const value = intakeFieldValue(valueJson);
  if (value === null || value === undefined || value === '') return '未提供';
  if (typeof value === 'object') {
    try { return JSON.stringify(value); } catch (_) { return '未提供'; }
  }
  return String(value);
}

function intakeStatusLabel(status, missing = []) {
  if (status === 'active_conflict') return '已有进行中的研究';
  if (status === 'clarification') return '需要补充说明';
  if (status === 'failed') return '研究 Intake 失败';
  if (status === 'completed' || status === 'ready' || (status === 'intake' && !missing.length)) return '参数已齐';
  if (status === 'running') return '正在准备…';
  return '收集中';
}

function createConversationIntake(assistantMessage) {
  if (!assistantMessage) return null;
  const existing = assistantMessage.querySelector('.conversation-intake');
  if (existing) return existing;
  const panel = document.createElement('section');
  panel.className = 'conversation-intake';
  panel.dataset.status = 'running';
  panel.setAttribute('aria-label', '研究 Intake');
  panel.setAttribute('aria-busy', 'true');
  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'conversation-intake-toggle';
  toggle.setAttribute('aria-expanded', 'true');
  toggle.dataset.userToggled = 'false';
  const title = document.createElement('span');
  title.className = 'conversation-intake-title';
  title.textContent = '研究 Intake';
  const summary = document.createElement('span');
  summary.className = 'conversation-intake-summary';
  summary.textContent = '正在准备…';
  toggle.append(title, summary);
  const body = document.createElement('div');
  body.className = 'conversation-intake-body';
  const skill = document.createElement('div');
  skill.className = 'conversation-intake-skill';
  skill.hidden = true;
  const skillName = document.createElement('strong');
  skillName.className = 'conversation-intake-skill-name';
  const skillDescription = document.createElement('span');
  skillDescription.className = 'conversation-intake-skill-description';
  const skillMeta = document.createElement('span');
  skillMeta.className = 'conversation-intake-skill-meta';
  skill.append(skillName, skillDescription, skillMeta);
  const fields = document.createElement('div');
  fields.className = 'conversation-intake-fields';
  const missing = document.createElement('p');
  missing.className = 'conversation-intake-missing';
  missing.hidden = true;
  const question = document.createElement('p');
  question.className = 'conversation-intake-question';
  question.hidden = true;
  const choices = document.createElement('div');
  choices.className = 'conversation-intake-choices';
  choices.hidden = true;
  body.append(skill, fields, missing, question, choices);
  toggle.addEventListener('click', () => {
    const expanded = toggle.getAttribute('aria-expanded') === 'true';
    toggle.setAttribute('aria-expanded', expanded ? 'false' : 'true');
    toggle.dataset.userToggled = 'true';
    body.hidden = expanded;
  });
  panel.append(toggle, body);
  const bubble = assistantMessage.querySelector('.bubble');
  const answer = bubble?.querySelector('.answer');
  if (answer) bubble.insertBefore(panel, answer);
  else if (bubble) bubble.appendChild(panel);
  return panel;
}

function updateConversationIntake(assistantMessage, payload = {}) {
  const panel = createConversationIntake(assistantMessage);
  if (!panel) return null;
  const skill = payload.skill || {};
  const skillName = panel.querySelector('.conversation-intake-skill-name');
  const skillDescription = panel.querySelector('.conversation-intake-skill-description');
  const skillMeta = panel.querySelector('.conversation-intake-skill-meta');
  const skillNode = panel.querySelector('.conversation-intake-skill');
  if (payload.skill || payload.skill_name) {
    skillNode.hidden = false;
    skillName.textContent = `Skill：${skill.name || payload.skill_name || 'deep-research-orchestration'}`;
    skillDescription.textContent = skill.description || payload.description || '';
    const tools = Array.isArray(skill.tools) ? skill.tools.filter((name) => typeof name === 'string') : [];
    skillMeta.textContent = [skill.version ? `版本 ${skill.version}` : '', skill.content_hash ? `快照 ${String(skill.content_hash).slice(0, 12)}` : '', tools.length ? `Tools ${tools.join('、')}` : ''].filter(Boolean).join(' · ');
  }
  const status = String(payload.status || panel.dataset.status || 'running');
  const fields = Array.isArray(payload.fields) ? payload.fields : [];
  const missingNames = Array.isArray(payload.missing) ? payload.missing.filter((name) => typeof name === 'string') : [];
  panel.dataset.status = status;
  panel.dataset.researchSessionId = payload.research_session?.research_session_id || panel.dataset.researchSessionId || '';
  panel.setAttribute('aria-busy', ['running', 'intake'].includes(status) && missingNames.length > 0 ? 'true' : 'false');
  const summary = panel.querySelector('.conversation-intake-summary');
  summary.textContent = intakeStatusLabel(status, missingNames);
  const fieldList = panel.querySelector('.conversation-intake-fields');
  fieldList.replaceChildren();
  fields.forEach((field) => {
    if (!field || typeof field.field_name !== 'string') return;
    const row = document.createElement('div');
    row.className = 'conversation-intake-field';
    row.dataset.fieldName = field.field_name;
    const name = document.createElement('span');
    name.className = 'conversation-intake-field-name';
    name.textContent = INTAKE_FIELD_LABELS[field.field_name] || field.field_name;
    const value = document.createElement('span');
    value.className = 'conversation-intake-field-value';
    value.textContent = intakeDisplayValue(field.value_json ?? field.value);
    const meta = document.createElement('span');
    meta.className = 'conversation-intake-field-meta';
    const confidence = Number(field.confidence);
    const confidenceText = Number.isFinite(confidence) ? `置信度 ${Math.round(Math.max(0, Math.min(1, confidence)) * 100)}%` : '置信度未知';
    meta.textContent = [INTAKE_SOURCE_LABELS[field.source] || field.source || '来源未知', confidenceText, INTAKE_CONFIRMATION_LABELS[field.confirmation_status] || field.confirmation_status || '确认状态未知'].join(' · ');
    row.append(name, value, meta);
    fieldList.appendChild(row);
  });
  const missingNode = panel.querySelector('.conversation-intake-missing');
  missingNode.hidden = !missingNames.length;
  missingNode.textContent = missingNames.length ? `待补充：${missingNames.map((name) => INTAKE_FIELD_LABELS[name] || name).join('、')}` : '';
  const questionNode = panel.querySelector('.conversation-intake-question');
  questionNode.hidden = !payload.question;
  questionNode.textContent = payload.question || '';
  const choicesNode = panel.querySelector('.conversation-intake-choices');
  const choices = Array.isArray(payload.choices) ? payload.choices.filter((choice) => INTAKE_CHOICE_LABELS[choice?.id]) : [];
  choicesNode.replaceChildren();
  choicesNode.hidden = !choices.length;
  choices.forEach((choice) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'secondary-button conversation-intake-choice';
    button.dataset.intakeChoice = choice.id;
    button.setAttribute('aria-pressed', 'false');
    button.textContent = INTAKE_CHOICE_LABELS[choice.id];
    button.addEventListener('click', () => {
      choicesNode.querySelectorAll('.conversation-intake-choice').forEach((item) => {
        const selected = item === button;
        item.setAttribute('aria-pressed', selected ? 'true' : 'false');
        item.classList.toggle('is-selected', selected);
      });
    });
    choicesNode.appendChild(button);
  });
  return panel;
}

function collapseConversationIntake(panel) {
  if (!panel) return;
  const toggle = panel.querySelector('.conversation-intake-toggle');
  const body = panel.querySelector('.conversation-intake-body');
  if (toggle && body) {
    toggle.setAttribute('aria-expanded', 'false');
    body.hidden = true;
  }
}

function finalizeConversationIntake(panel, status = 'completed') {
  if (!panel) return;
  const intakeStatus = panel.dataset.status || '';
  const hasMissing = Boolean(panel.querySelector('.conversation-intake-missing:not([hidden])')?.textContent);
  const hasChoices = Boolean(panel.querySelector('.conversation-intake-choice'));
  const needsUserAction = ['clarification', 'active_conflict'].includes(intakeStatus) || hasMissing || hasChoices;
  const finalStatus = status === 'completed' ? 'completed' : 'failed';
  panel.dataset.status = needsUserAction && finalStatus === 'completed' ? intakeStatus || 'intake' : finalStatus;
  panel.setAttribute('aria-busy', 'false');
  const summary = panel.querySelector('.conversation-intake-summary');
  if (summary && finalStatus === 'failed') summary.textContent = '研究 Intake 失败';
  if (finalStatus !== 'running' && (finalStatus !== 'completed' || !needsUserAction)) collapseConversationIntake(panel);
}

function updateConversationProcessing(processing, step) {
  if (!processing || !step) return;
  const list = processing.querySelector('.conversation-processing-list') || processing;
  const isSystemRuleStep = step.kind === 'system_rule' || step.kind === 'system-rule' || /系统规则/.test(String(step.label || ''));
  const stepId = isSystemRuleStep ? 'system-rule-applied' : String(step.step_id || step.kind || `step-${list.children.length}`);
  let item = [...list.querySelectorAll('.conversation-processing-item')].find((candidate) => candidate.dataset.stepId === stepId);
  if (!item) {
    item = document.createElement('div');
    item.className = 'conversation-processing-item';
    item.dataset.stepId = stepId;
    const label = document.createElement('span');
    label.className = 'conversation-processing-label';
    const summary = document.createElement('span');
    summary.className = 'conversation-processing-summary';
    item.append(label, summary);
    list.appendChild(item);
  }
  const status = ['running', 'completed', 'failed', 'skipped', 'interrupted'].includes(step.status) ? step.status : 'running';
  if (item.dataset.status && item.dataset.status !== 'running' && status === 'running') return;
  item.dataset.status = status;
  item.querySelector('.conversation-processing-label').textContent = isSystemRuleStep ? '已应用系统规则' : (step.label || step.kind || '处理中');
  item.querySelector('.conversation-processing-summary').textContent = step.summary || step.status || '';
  syncConversationProcessingState(processing);
}

function syncConversationProcessingState(processing) {
  if (!processing) return false;
  const running = Boolean(processing.querySelector('.conversation-processing-item[data-status="running"]'));
  processing.setAttribute('aria-busy', running ? 'true' : 'false');
  processing.dataset.running = running ? 'true' : 'false';
  return running;
}

function collapseConversationProcessing(processing) {
  if (!processing) return;
  const toggle = processing.querySelector('.conversation-processing-toggle');
  const list = processing.querySelector('.conversation-processing-list');
  if (toggle && list) {
    toggle.setAttribute('aria-expanded', 'false');
    list.hidden = true;
  }
}

function stopConversationProcessing(processing, status = 'failed', summary = '处理过程已结束') {
  if (!processing) return;
  const list = processing.querySelector('.conversation-processing-list');
  if (list) {
    list.querySelectorAll('.conversation-processing-item').forEach((item) => {
      if (item.dataset.status !== 'running') return;
      item.dataset.status = status;
      const detail = item.querySelector('.conversation-processing-summary');
      if (detail) detail.textContent = summary;
    });
  }
  processing.setAttribute('aria-busy', 'false');
  processing.dataset.running = 'false';
}

function showConversationProcessingDegraded(processing, message = '处理过程暂不可用，已降级显示') {
  if (!processing) return;
  const list = processing.querySelector('.conversation-processing-list');
  if (!list) return;
  const notice = document.createElement('p');
  notice.className = 'conversation-processing-degraded';
  notice.textContent = message;
  list.appendChild(notice);
  processing.dataset.degraded = 'true';
  stopConversationProcessing(processing, 'skipped', message);
  collapseConversationProcessing(processing);
}

async function hydrateConversationProcessing(messageElement, messageId, loadGeneration, conversationId) {
  if (!messageElement || !messageId) return;
  try {
    const data = await conversationFetch(`/api/messages/${encodeURIComponent(messageId)}/processing-steps`);
    if (conversationState.streamGeneration !== loadGeneration || conversationState.conversationId !== conversationId || messageElement.dataset.messageId !== messageId || !messageElement.parentNode) return;
    const steps = Array.isArray(data.steps) ? data.steps : [];
    if (!steps.length) return;
    const processing = createConversationProcessing(messageElement);
    steps.forEach((step) => updateConversationProcessing(processing, step));
    syncConversationProcessingState(processing);
    collapseConversationProcessing(processing);
  } catch (error) {
    if (conversationState.streamGeneration !== loadGeneration || conversationState.conversationId !== conversationId || messageElement.dataset.messageId !== messageId || !messageElement.parentNode) return;
    const processing = createConversationProcessing(messageElement);
    showConversationProcessingDegraded(processing);
  }
}

function enqueueConversationProcessingHydration(rendered, loadGeneration, conversationId) {
  if (!rendered?.length) return;
  const previous = conversationState.processingHydrationQueue || Promise.resolve();
  conversationState.processingHydrationQueue = previous.catch(() => {}).then(async () => {
    for (const { item, element } of rendered) {
      if (conversationState.streamGeneration !== loadGeneration || conversationState.conversationId !== conversationId) return;
      if (item.role !== 'assistant') continue;
      await hydrateConversationProcessing(element, item.message_id, loadGeneration, conversationId);
      if (conversationState.streamGeneration !== loadGeneration || conversationState.conversationId !== conversationId) return;
    }
  });
}

function enqueueConversationMemoryHydration(rendered, loadGeneration, conversationId) {
  if (!rendered?.length) return;
  const byMessageId = new Map(rendered.map(({ item, element }) => [item.message_id, { item, element }]));
  rendered.forEach(({ item, element }) => {
    if (item.role !== 'assistant' || !item.parent_message_id) return;
    const user = byMessageId.get(item.parent_message_id);
    if (!user) return;
    const section = createConversationMemoryResults(element, user.item.message_id);
    if (section) startMemoryAnalysisPolling(user.item.message_id, element, conversationState.projectId);
  });
}

function createConversationSources(assistantMessage) {
  const container = assistantMessage?.querySelector('.conversation-sources');
  const factory = window.ConversationResearch?.createSourceRenderer;
  return container && factory ? factory({ document, container }) : null;
}

function showConversationMemoryNotice(bubble, eventData) {
  if (!bubble || !eventData) return;
  const notice = document.createElement('div');
  notice.className = 'conversation-memory-notice';
  notice.dataset.status = eventData.status || 'info';
  const labels = { saved: '已保存项目记忆', used: '本次回答使用了项目记忆', needs_confirmation: '可能是长期偏好，确认后保存', not_analyzed: '记忆未分析/未保存', not_saved: '记忆未保存' };
  const title = document.createElement('strong');
  title.textContent = labels[eventData.status] || '记忆提示';
  notice.appendChild(title);
  if (eventData.statement) {
    const statement = document.createElement('span');
    statement.textContent = ` · ${eventData.statement}`;
    notice.appendChild(statement);
  } else if (eventData.message) {
    const detail = document.createElement('span');
    detail.textContent = ` · ${eventData.message}`;
    notice.appendChild(detail);
  }
  const sources = bubble.querySelector('.conversation-sources');
  if (sources) bubble.insertBefore(notice, sources);
  else bubble.appendChild(notice);
  if (conversationMemoryStatus) conversationMemoryStatus.textContent = notice.textContent;
}

function memoryAnalysisSummary(job = {}, items = []) {
  const values = items.filter((item) => item && item.intent !== 'none');
  const saved = values.filter((item) => ['auto_saved', 'saved', 'duplicate', 'superseded'].includes(item.decision_status)).length;
  const pending = values.filter((item) => ['pending_confirmation', 'pending', 'conflict'].includes(item.decision_status)).length;
  const failed = values.filter((item) => ['failed', 'error'].includes(item.decision_status)).length;
  return { total: values.length, saved, pending, failed, status: job.status || 'pending' };
}

function memoryAnalysisLabel(item) {
  const labels = {
    auto_saved: '已自动保存', saved: '已保存', duplicate: '已有相同记忆',
    superseded: '已更新旧版本', pending_confirmation: '待确认', pending: '待确认',
    conflict: '存在冲突', ignored: '不保存', failed: '处理失败',
  };
  return labels[item.decision_status] || '待确认';
}

function createConversationMemoryResults(assistantMessage, userMessageId) {
  if (!assistantMessage || !userMessageId) return null;
  const bubble = assistantMessage.querySelector('.bubble');
  let section = bubble?.querySelector('.conversation-memory-results');
  if (!section) {
    section = document.createElement('section');
    section.className = 'conversation-memory-results';
    bubble.insertBefore(section, bubble.querySelector('.conversation-sources') || null);
  }
  // Live assistant messages and hydrated history both start with an empty
  // placeholder.  Populate that placeholder in place instead of returning
  // early; otherwise polling has no toggle/list nodes to render into.
  if (section.dataset.userMessageId === userMessageId && section.querySelector('.conversation-memory-results-toggle')) return section;
  section.dataset.userMessageId = userMessageId;
  section.replaceChildren();
  const header = document.createElement('div'); header.className = 'conversation-memory-results-head';
  const title = document.createElement('button'); title.type = 'button'; title.className = 'conversation-memory-results-toggle'; title.setAttribute('aria-expanded', 'false'); title.textContent = '记忆分析';
  const summary = document.createElement('span'); summary.className = 'conversation-memory-results-summary';
  const body = document.createElement('div'); body.className = 'conversation-memory-results-body'; body.hidden = true;
  const list = document.createElement('div'); list.className = 'conversation-memory-results-list';
  const actions = document.createElement('div'); actions.className = 'conversation-memory-results-actions';
  const more = document.createElement('button'); more.type = 'button'; more.className = 'secondary-button memory-analysis-more'; more.textContent = '加载更多'; more.hidden = true;
  title.addEventListener('click', () => { const expanded = title.getAttribute('aria-expanded') === 'true'; title.setAttribute('aria-expanded', expanded ? 'false' : 'true'); body.hidden = expanded; });
  more.addEventListener('click', () => loadMemoryAnalysisPage(userMessageId, assistantMessage, section));
  header.append(title, summary); body.append(list, actions, more); section.append(header, body);
  return section;
}

function renderMemoryAnalysisResult(section, userMessageId) {
  const state = conversationState.memoryAnalysis.get(userMessageId);
  if (!state || !section) return;
  const visibleItems = [...state.items.values()].filter((item) => item && item.intent !== 'none');
  const summary = memoryAnalysisSummary(state.job, visibleItems);
  section.hidden = state.job.status === 'completed' && !visibleItems.length && !(state.failures || []).length;
  if (section.hidden) return;
  const title = section.querySelector('.conversation-memory-results-toggle');
  const summaryNode = section.querySelector('.conversation-memory-results-summary');
  const list = section.querySelector('.conversation-memory-results-list');
  const actions = section.querySelector('.conversation-memory-results-actions');
  const more = section.querySelector('.memory-analysis-more');
  if (!title || !summaryNode || !list || !actions) return;
  const stateLabel = { pending: '正在判断是否需要记住…', running: '正在判断是否需要记住…', partial: '记忆分析进行中…', completed: '记忆分析完成', failed: '记忆分析失败' }[summary.status] || '记忆分析';
  title.textContent = stateLabel;
  const failureCount = (state.failures || []).length + summary.failed;
  summaryNode.textContent = summary.total || failureCount ? `已保存 ${summary.saved} · 待确认 ${summary.pending}${failureCount ? ` · 失败 ${failureCount}` : ''}` : '';
  list.replaceChildren();
  visibleItems.forEach((item) => {
    const row = document.createElement('article'); row.className = 'conversation-memory-result'; row.dataset.itemId = item.item_id || '';
    row.dataset.status = item.decision_status || 'pending_confirmation';
    const statement = document.createElement('p'); statement.className = 'conversation-memory-result-statement'; statement.textContent = item.statement || '未提供记忆陈述';
    const meta = document.createElement('p'); meta.className = 'conversation-memory-result-meta'; meta.textContent = `${memoryAnalysisLabel(item)} · ${item.suggested_scope || item.scope || 'project'} · 置信度 ${Math.round(Number(item.confidence || 0) * 100)}%`;
    const rationale = document.createElement('p'); rationale.className = 'conversation-memory-result-rationale'; rationale.textContent = item.rationale_summary || '';
    const buttons = document.createElement('div'); buttons.className = 'conversation-memory-result-actions';
    const addDecision = (label, decision) => { const button = document.createElement('button'); button.type = 'button'; button.className = decision === 'ignore' ? 'secondary-button' : 'send-button'; button.dataset.memoryDecision = decision; button.dataset.itemId = item.item_id || ''; button.textContent = label; button.disabled = !item.item_id || !['pending_confirmation', 'pending', 'conflict'].includes(item.decision_status); buttons.appendChild(button); };
    if (['pending_confirmation', 'pending', 'conflict'].includes(item.decision_status)) {
      const currentProjectId = conversationState.projectId || null;
      if (!currentProjectId) {
        const picker = document.createElement('select'); picker.className = 'memory-analysis-project-select'; picker.dataset.memoryProject = item.item_id || ''; picker.setAttribute('aria-label', '选择要保存的项目');
        const placeholder = document.createElement('option'); placeholder.value = ''; placeholder.textContent = '选择已有 active 项目'; picker.appendChild(placeholder);
        projectState.items.filter((project) => project.status === 'active').forEach((project) => { const option = document.createElement('option'); option.value = project.project_id; option.textContent = project.name || '未命名项目'; picker.appendChild(option); });
        row.appendChild(picker);
      }
      addDecision('保存到当前项目', 'save_project');
      if (currentProjectId || item.suggested_scope === 'global' || item.scope === 'global') addDecision('保存为全局', 'save_global');
      addDecision('不保存', 'ignore');
    }
    row.append(statement, meta);
    if (rationale.textContent) row.appendChild(rationale);
    row.appendChild(buttons); list.appendChild(row);
  });
  if (state.failures?.length) {
    const failures = document.createElement('p'); failures.className = 'conversation-memory-results-failures';
    const details = state.failures.map((failure) => `${failure.code || '失败'}：${failure.message || '该条未保存'}`).join('；');
    failures.textContent = `失败 ${state.failures.length} 条 · ${details}`;
    list.appendChild(failures);
  }
  actions.replaceChildren();
  const decisionItems = visibleItems.filter((item) => ['pending_confirmation', 'pending', 'conflict'].includes(item.decision_status));
  if (decisionItems.length) {
    const saveAll = document.createElement('button'); saveAll.type = 'button'; saveAll.className = 'send-button'; saveAll.dataset.memoryBatchDecision = 'save_suggested'; saveAll.textContent = '按建议保存全部';
    const ignoreAll = document.createElement('button'); ignoreAll.type = 'button'; ignoreAll.className = 'secondary-button'; ignoreAll.dataset.memoryBatchDecision = 'ignore'; ignoreAll.textContent = '全部不保存';
    actions.append(saveAll, ignoreAll);
  }
  more.hidden = !state.nextCursor;
  more.disabled = Boolean(state.loading);
  if (summary.pending && title.getAttribute('aria-expanded') !== 'true') { title.setAttribute('aria-expanded', 'true'); section.querySelector('.conversation-memory-results-body').hidden = false; }
}

async function decideMemoryAnalysisItem(userMessageId, assistantMessage, section, itemId, decision) {
  const state = conversationState.memoryAnalysis.get(userMessageId); if (!state || state.deciding.has(itemId)) return;
  const item = state.items.get(itemId); if (!item) return;
  state.deciding.add(itemId);
  try {
    const payload = { decision };
    if (decision === 'save_project') {
      const picker = section.querySelector(`[data-memory-project="${CSS.escape(itemId)}"]`);
      const selectedProjectId = conversationState.projectId || picker?.value || null;
      if (!selectedProjectId) { setConversationStatus('请选择一个已有 active 项目，再保存项目记忆', 'error'); state.deciding.delete(itemId); return; }
      payload.project_id = selectedProjectId;
    }
    const data = await conversationFetch(`/api/memory-analysis/items/${encodeURIComponent(itemId)}/decision`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    state.items.set(itemId, { ...item, ...(data.item || data) });
    renderMemoryAnalysisResult(section, userMessageId);
  } catch (error) { state.items.set(itemId, { ...item, decision_status: 'failed', error_message: error.message }); renderMemoryAnalysisResult(section, userMessageId); }
  finally { state.deciding.delete(itemId); }
}

async function decideMemoryAnalysisBatch(userMessageId, assistantMessage, section, decision) {
  const state = conversationState.memoryAnalysis.get(userMessageId); if (!state || state.decidingBatch) return;
  state.decidingBatch = true;
  try {
    const payload = { decision };
    if (decision === 'save_project') {
      const picker = section.querySelector('[data-memory-project]');
      const selectedProjectId = conversationState.projectId || picker?.value || null;
      if (!selectedProjectId) { setConversationStatus('请选择一个已有 active 项目，再保存项目记忆', 'error'); return; }
      payload.project_id = selectedProjectId;
    }
    const data = await conversationFetch(`/api/messages/${encodeURIComponent(userMessageId)}/memory-analysis/decisions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    (data.items || data.results || []).forEach((item) => { if (item.item_id) state.items.set(item.item_id, item); });
    state.failures = Array.isArray(data.failed) ? data.failed : [];
    state.job = { ...state.job, ...(data.job || data.analysis || {}) };
    renderMemoryAnalysisResult(section, userMessageId);
  } catch (error) { setConversationStatus(`批量记忆决策失败：${error.message}`, 'error'); }
  finally { state.decidingBatch = false; }
}

async function loadMemoryAnalysisPage(userMessageId, assistantMessage, section, { refresh = false } = {}) {
  const state = conversationState.memoryAnalysis.get(userMessageId) || { job: { status: 'pending' }, items: new Map(), failures: [], nextCursor: null, loading: false, deciding: new Set() };
  if (state.loading || (!refresh && state.loaded && !state.nextCursor)) return;
  state.loading = true; conversationState.memoryAnalysis.set(userMessageId, state);
  try {
    const params = new URLSearchParams({ limit: '10' }); if (!refresh && state.nextCursor) params.set('cursor', state.nextCursor);
    const data = await conversationFetch(`/api/messages/${encodeURIComponent(userMessageId)}/memory-analysis?${params}`);
    state.job = { ...state.job, ...(data.job || data.analysis || {}) }; (data.items || data.results || []).forEach((item) => { if (item.intent !== 'none' && item.item_id) state.items.set(item.item_id, item); });
    const responseCursor = data.next_cursor || data.nextCursor || null;
    if (!refresh || responseCursor) state.nextCursor = responseCursor;
    state.loaded = true; renderMemoryAnalysisResult(section, userMessageId);
  } catch (error) {
    if (error.status === 404 || error.code === 'MEMORY_ANALYSIS_NOT_FOUND' || error.code === 'ANALYSIS_NOT_FOUND') { state.job = { ...state.job, status: 'pending' }; }
    else { state.job = { ...state.job, status: 'failed', error_code: error.code }; }
    renderMemoryAnalysisResult(section, userMessageId);
  } finally { state.loading = false; }
}

function startMemoryAnalysisPolling(userMessageId, assistantMessage, projectId = null) {
  if (!userMessageId || !assistantMessage) return;
  const section = createConversationMemoryResults(assistantMessage, userMessageId); if (!section) return;
  let state = conversationState.memoryAnalysis.get(userMessageId);
  if (!state) { state = { job: { status: 'pending' }, items: new Map(), failures: [], nextCursor: null, loaded: false, loading: false, deciding: new Set(), attempts: 0 }; conversationState.memoryAnalysis.set(userMessageId, state); }
  const poll = async () => {
    if (!conversationState.memoryAnalysis.has(userMessageId) || !section.isConnected) return;
    await loadMemoryAnalysisPage(userMessageId, assistantMessage, section, { refresh: true });
    const current = conversationState.memoryAnalysis.get(userMessageId); if (!current) return;
    renderMemoryAnalysisResult(section, userMessageId);
    if (['pending', 'running', 'partial'].includes(current.job.status) && current.attempts < 30) { current.attempts += 1; window.setTimeout(poll, 1500); }
  };
  poll();
  if (section.dataset.listenerAttached !== 'true') {
    section.dataset.listenerAttached = 'true';
    section.addEventListener('click', (event) => {
      const decision = event.target.closest('[data-memory-decision]'); if (decision) decideMemoryAnalysisItem(userMessageId, assistantMessage, section, decision.dataset.itemId, decision.dataset.memoryDecision);
      const batch = event.target.closest('[data-memory-batch-decision]'); if (batch) decideMemoryAnalysisBatch(userMessageId, assistantMessage, section, batch.dataset.memoryBatchDecision);
    });
  }
}

function resetConversationMessages() {
  messages.replaceChildren();
  const welcome = document.createElement('div');
  welcome.className = 'message assistant';
  const avatar = document.createElement('div'); avatar.className = 'avatar'; avatar.textContent = 'O';
  const bubble = document.createElement('div'); bubble.className = 'bubble';
  const model = document.createElement('span'); model.className = 'model-tag'; model.textContent = '本地会话';
  const answer = document.createElement('span'); answer.className = 'answer'; answer.textContent = '你好，我已经准备好了。问我任何问题。';
  bubble.append(model, answer); welcome.append(avatar, bubble); messages.appendChild(welcome);
}

function targetCharsForMessages() {
  const width = messages.clientWidth || 720;
  const height = messages.clientHeight || 520;
  return Math.max(1200, Math.min(8000, Math.round((width * height) / 2.5)));
}

function updateConversationUrl(conversationId, replace = false) {
  if (!conversationId) return;
  const next = `/c/${encodeURIComponent(conversationId)}`;
  if (window.location.pathname !== next) {
    if (replace) window.history.replaceState({}, '', next);
    else window.history.pushState({}, '', next);
  }
}

function closeFloatingMenu(restore = true) {
  if (!menuState.panel) return;
  const trigger = menuState.trigger;
  menuState.panel.remove(); menuState.panel = null; menuState.trigger = null;
  if (trigger) trigger.setAttribute('aria-expanded', 'false');
  if (restore && trigger?.isConnected) trigger.focus();
}

function openFloatingMenu(trigger, panel) {
  closeFloatingMenu(false);
  menuState.trigger = trigger; menuState.panel = panel;
  panel.classList.add('floating-menu'); panel.setAttribute('role', 'menu'); document.body.appendChild(panel);
  const rect = trigger.getBoundingClientRect(); const width = Math.max(150, panel.offsetWidth || 170);
  const left = Math.min(Math.max(8, rect.right - width), window.innerWidth - width - 8);
  const below = rect.bottom + 8; const above = rect.top - panel.offsetHeight - 8;
  panel.style.left = `${left}px`; panel.style.top = `${above >= 8 ? above : below}px`;
  trigger.setAttribute('aria-expanded', 'true'); panel.querySelector('button')?.focus();
}

function menuButton(label, handler, danger = false) {
  const button = document.createElement('button'); button.type = 'button'; button.setAttribute('role', 'menuitem'); button.textContent = label;
  if (danger) button.classList.add('danger-button');
  button.addEventListener('click', (event) => { event.stopPropagation(); closeFloatingMenu(true); closeMobileDrawer(true); handler(); }); return button;
}

function renderProjectOptions(projects) {
  projectState.items = Array.isArray(projects) ? projects.slice() : [];
  renderMemoryProjectOptions(projectState.items);
  if (!projectState.expandedProjectId && conversationState.projectId) projectState.expandedProjectId = conversationState.projectId;
  renderProjectList(projectState.items);
}

function saveProjectSort(value) {
  projectState.sort = value === 'name' ? 'name' : 'recent';
  try { localStorage.setItem(PROJECT_SORT_KEY, projectState.sort); } catch (_) {}
  renderProjectList(projectState.items);
}

function visibleProjects(projects) {
  const visible = (projects || []).filter((item) => projectState.showArchived ? item.status === 'archived' : item.status !== 'archived' && item.status !== 'deleted');
  return visible.sort((left, right) => projectState.sort === 'name'
    ? String(left.name || '').localeCompare(String(right.name || ''), 'zh-CN')
    : String(right.last_activity_at || right.updated_at || '').localeCompare(String(left.last_activity_at || left.updated_at || '')) || String(right.project_id).localeCompare(String(left.project_id)));
}

function renderConversationRow(item, container, owner = 'recent') {
  if (!item?.conversation_id || container.querySelector(`[data-conversation-id="${CSS.escape(item.conversation_id)}"]`)) return;
  const row = document.createElement('div'); row.className = 'conversation-item'; row.dataset.conversationId = item.conversation_id; row.dataset.owner = owner; row.setAttribute('role', 'option'); row.setAttribute('aria-selected', item.conversation_id === conversationState.conversationId ? 'true' : 'false');
  const button = document.createElement('button'); button.type = 'button'; button.className = 'conversation-item-main'; button.setAttribute('aria-label', `打开会话 ${item.title || '新对话'}`);
  const title = document.createElement('span'); title.className = 'conversation-item-title'; title.textContent = item.title || '新对话';
  button.append(title); button.addEventListener('click', () => openConversationFromWorkspace(item.conversation_id));
  const menu = document.createElement('button'); menu.type = 'button'; menu.className = 'conversation-item-menu'; menu.setAttribute('aria-label', `管理会话 ${item.title || '新对话'}`); menu.setAttribute('aria-haspopup', 'menu'); menu.setAttribute('aria-expanded', 'false'); menu.textContent = '⋯';
  menu.addEventListener('click', (event) => { event.stopPropagation(); const panel = document.createElement('div'); panel.append(menuButton('重命名', () => openActionDialog('rename-conversation', item))); panel.append(menuButton('移动到项目', () => openActionDialog('move-conversation', item))); if (item.project_id) panel.append(menuButton('移出项目', () => moveConversation(item, null))); panel.append(menuButton(item.status === 'archived' ? '恢复' : '归档', () => confirmAction('conversation-status', item))); panel.append(menuButton('删除', () => confirmAction('conversation-delete', item), true)); openFloatingMenu(menu, panel); });
  row.append(button, menu); container.appendChild(row);
}

function renderConversationRows(items, container, owner, append = false) {
  if (!append) container.replaceChildren();
  const showArchived = owner === 'recent' ? conversationListState.showArchived : false;
  const visibleItems = (items || []).filter((item) => showArchived ? item.status === 'archived' : item.status !== 'archived' && item.status !== 'deleted');
  visibleItems.forEach((item) => renderConversationRow(item, container, owner));
}

function renderConversationList(items, append = false) { if (conversationList) renderConversationRows(items, conversationList, 'recent', append); }

function createProjectFolderIcon(open = false) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.classList.add('project-folder-icon'); svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('width', '16'); svg.setAttribute('height', '16'); svg.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', open ? 'M3.5 7.5h6l1.7 2H20a1 1 0 0 1 .98 1.2l-1.5 7.2a1.5 1.5 0 0 1-1.47 1.2H5.2a1.5 1.5 0 0 1-1.47-1.2L2.5 9.2a1.5 1.5 0 0 1 1-1.7Z' : 'M3.5 6.5h6l1.7 2H20a1 1 0 0 1 1 1v7.5a1.5 1.5 0 0 1-1.5 1.5H4.5A1.5 1.5 0 0 1 3 17V8a1.5 1.5 0 0 1 .5-1.5Z');
  path.setAttribute('fill', 'none'); path.setAttribute('stroke', 'currentColor'); path.setAttribute('stroke-width', '1.5'); path.setAttribute('stroke-linejoin', 'round'); svg.appendChild(path); return svg;
}

function renderProjectList(projects) {
  if (!projectList) return;
  projectList.replaceChildren(); projectList.hidden = projectState.collapsed;
  for (const project of visibleProjects(projects)) {
    const row = document.createElement('div'); row.className = 'project-item'; row.dataset.projectId = project.project_id; row.dataset.status = project.status || 'active';
    const head = document.createElement('div'); head.className = 'project-item-head';
    const selectedContextId = conversationState.conversationId ? conversationState.draftProjectId : conversationState.projectId;
    const isExpanded = projectState.expandedProjectId === project.project_id;
    const main = document.createElement('button'); main.type = 'button'; main.className = 'project-item-main'; main.setAttribute('aria-pressed', project.project_id === selectedContextId ? 'true' : 'false'); main.setAttribute('aria-expanded', isExpanded ? 'true' : 'false'); main.setAttribute('aria-label', `${isExpanded ? '收起' : '展开'}项目 ${project.name || '未命名项目'}`);
    const icon = createProjectFolderIcon(isExpanded); icon.classList.add('project-item-icon'); const title = document.createElement('span'); title.className = 'project-item-title'; title.textContent = project.name || '未命名项目'; main.append(icon, title);
    main.addEventListener('click', () => { selectProjectContext(project.project_id); projectState.expandedProjectId = isExpanded ? null : project.project_id; renderProjectList(projectState.items); if (!isExpanded) loadProjectConversations(project.project_id); });
    const menu = document.createElement('button'); menu.type = 'button'; menu.className = 'project-item-menu'; menu.setAttribute('aria-label', `管理项目 ${project.name || ''}`); menu.setAttribute('aria-haspopup', 'menu'); menu.setAttribute('aria-expanded', 'false'); menu.textContent = '⋯';
    menu.addEventListener('click', (event) => { event.stopPropagation(); const panel = document.createElement('div'); if (project.status !== 'archived') panel.append(menuButton('重命名', () => openActionDialog('rename-project', project))); panel.append(menuButton(project.status === 'archived' ? '恢复' : '归档', () => confirmAction('project-status', project))); panel.append(menuButton('删除', () => confirmAction('project-delete', project), true)); openFloatingMenu(menu, panel); });
    head.append(main, menu); row.appendChild(head);
    const child = document.createElement('div'); child.className = 'project-conversation-list'; child.dataset.projectId = project.project_id; child.hidden = projectState.expandedProjectId !== project.project_id;
    const entry = projectState.conversations.get(project.project_id);
    if (entry?.items?.length) renderConversationRows(entry.items, child, `project:${project.project_id}`); else if (entry?.loaded && !entry.items.length) { const empty = document.createElement('button'); empty.type = 'button'; empty.className = 'project-empty-action'; empty.textContent = '＋ 在此项目中新建对话'; empty.addEventListener('click', () => { selectProjectContext(project.project_id); beginDraft(); }); child.appendChild(empty); }
    if (entry?.cursor) { const more = document.createElement('button'); more.type = 'button'; more.className = 'project-load-more'; more.textContent = '查看更多'; more.addEventListener('click', () => loadProjectConversations(project.project_id, true)); child.appendChild(more); }
    row.appendChild(child); projectList.appendChild(row);
  }
}

function selectProjectContext(projectId) {
  const nextProjectId = projectId || null;
  if (conversationState.conversationId) conversationState.draftProjectId = nextProjectId;
  else conversationState.projectId = nextProjectId;
  renderProjectList(projectState.items); updateGovernanceControls();
}

async function loadProjectConversations(projectId, append = false) {
  const entry = projectState.conversations.get(projectId) || { items: [], cursor: null, loaded: false, loading: false }; if (entry.loading) return; entry.loading = true; projectState.conversations.set(projectId, entry);
  const params = new URLSearchParams({ project_id: projectId, status: 'active', limit: '10' }); if (append && entry.cursor) params.set('cursor', entry.cursor);
  try { const data = await conversationFetch(`/api/conversations?${params}`); entry.items = append ? entry.items.concat(data.conversations || []) : (data.conversations || []); entry.cursor = data.next_cursor || null; entry.loaded = true; renderProjectList(projectState.items); }
  catch (error) { setConversationStatus(`项目会话加载失败：${error.message}`, 'error'); } finally { entry.loading = false; }
}

function openActionDialog(action, target) {
  dialogState.action = action; dialogState.target = target; dialogState.restoreFocus = document.activeElement;
  conversationActionNameField.hidden = !action.includes('rename'); conversationActionProjectSearchField.hidden = action !== 'move-conversation'; conversationActionProjectField.hidden = action !== 'move-conversation'; conversationActionHistoryField.hidden = action !== 'move-conversation'; conversationActionStatus.textContent = '';
  if (action === 'rename-project') { conversationActionTitle.textContent = '重命名项目'; conversationActionName.value = target.name || ''; }
  if (action === 'rename-conversation') { conversationActionTitle.textContent = '重命名会话'; conversationActionName.value = target.title || ''; }
  if (action === 'move-conversation') { conversationActionTitle.textContent = '移动到项目'; conversationActionHistory.checked = false; conversationActionProjectSearch.value = ''; renderMoveProjectOptions(target); if (!conversationActionProject.options.length) { setConversationStatus('没有可用的目标项目', 'error'); return; } }
  conversationActionDialog.showModal(); (action.includes('rename') ? conversationActionName : conversationActionProjectSearch)?.focus();
}

function activeMoveProjects(excludeProjectId) {
  return projectState.items.filter((item) => item.status === 'active' && item.project_id !== excludeProjectId).sort((a, b) => String(a.name || '').localeCompare(String(b.name || ''), 'zh-CN'));
}

function renderMoveProjectOptions(target, query = '') {
  conversationActionProject.replaceChildren();
  const normalizedQuery = String(query || '').trim().toLocaleLowerCase('zh-CN');
  activeMoveProjects(target?.project_id).filter((item) => !normalizedQuery || String(item.name || '').toLocaleLowerCase('zh-CN').includes(normalizedQuery)).forEach((item) => { const option = document.createElement('option'); option.value = item.project_id; option.textContent = item.name || '未命名项目'; conversationActionProject.appendChild(option); });
}

function confirmAction(action, target) { dialogState.action = action; dialogState.target = target; dialogState.restoreFocus = document.activeElement; conversationConfirmTitle.textContent = action.includes('delete') ? '删除确认' : (target.status === 'archived' ? '恢复确认' : '归档确认'); conversationConfirmMessage.textContent = action === 'project-delete' ? `删除项目“${target.name}”？项目文档关联会解除，原件保留。` : action === 'conversation-delete' ? '删除该会话？消息会被删除，但记忆及审计记录不会联动删除。' : (target.status === 'archived' ? '恢复该项目或会话？' : '归档该项目或会话？消息和记忆仍会保留，可恢复。'); conversationConfirmDialog.showModal(); conversationConfirmSubmit.focus(); }

async function moveConversation(conversation, targetProjectId, includePriorHistory = false) {
  const previousProjectId = conversation.project_id || null;
  const payload = { project_id: targetProjectId, memory_history_policy: includePriorHistory ? 'include_prior_history' : 'from_binding', confirm_move: true }; const updated = await conversationFetch(`/api/conversations/${encodeURIComponent(conversation.conversation_id)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  if (conversationState.conversationId === conversation.conversation_id) { conversationState.conversation = updated; conversationState.projectId = updated.project_id || null; conversationState.draftProjectId = updated.project_id || null; }
  projectState.conversations.forEach((entry) => { entry.items = (entry.items || []).filter((item) => item.conversation_id !== conversation.conversation_id); });
  projectState.expandedProjectId = updated.project_id || (projectState.expandedProjectId === previousProjectId ? null : projectState.expandedProjectId);
  await loadProjects(); await loadConversationList(); if (updated.project_id) await loadProjectConversations(updated.project_id); renderProjectList(projectState.items); setConversationStatus(targetProjectId ? '会话已移动到项目' : '会话已移出项目');
}

async function loadConversationList({ append = false, guard = null } = {}) {
  if (!conversationList || conversationListState.loading) return; if (!append) conversationListState.cursor = null; conversationListState.loading = true; const params = new URLSearchParams({ status: conversationListState.showArchived ? 'archived' : 'active', limit: '20' }); if (!conversationListState.showArchived) params.set('unbound_only', 'true'); if (append && conversationListState.cursor) params.set('cursor', conversationListState.cursor);
  try { const data = await conversationFetch(`/api/conversations?${params}`); if (guard && !guard()) return; conversationListState.cursor = data.next_cursor || null; renderConversationList(data.conversations || [], append); }
  catch (error) { if (!guard || guard()) setConversationStatus(`最近会话加载失败：${error.message}`, 'error'); } finally { conversationListState.loading = false; }
}

async function loadProjects() { try { const data = await conversationFetch('/api/projects?limit=100'); renderProjectOptions(data.projects || []); } catch (error) { setConversationStatus(`项目列表加载失败：${error.message}`, 'error'); } }

async function loadConversationMessages(conversationId, { replace = true } = {}) {
  if (!conversationId || (conversationState.loadingMessages && conversationState.loadingConversationId === conversationId)) return;
  const loadGeneration = conversationState.streamGeneration;
  const loadToken = Symbol('conversation-message-load');
  conversationState.loadingConversationId = conversationId;
  conversationState.messageLoadToken = loadToken;
  conversationState.loadingMessages = true;
  try {
    const params = new URLSearchParams({ target_chars: String(targetCharsForMessages()) });
    const data = await conversationFetch(`/api/conversations/${encodeURIComponent(conversationId)}/messages?${params}`);
    if (conversationState.streamGeneration !== loadGeneration || conversationState.conversationId !== conversationId) return;
    conversationState.messageCursor = data.next_cursor || null;
    if (replace) messages.replaceChildren();
    const items = orderConversationMessages(data.messages || []);
    const rendered = items.map((item) => ({ item, element: renderConversationMessage(item) }));
    rendered.forEach(({ item, element }) => { element.dataset.messageId = item.message_id || ''; messages.appendChild(element); });
    enqueueConversationProcessingHydration(rendered, loadGeneration, conversationId);
    enqueueConversationMemoryHydration(rendered, loadGeneration, conversationId);
    workspace.classList.toggle('has-started', (data.messages || []).length > 0);
    messages.scrollTop = messages.scrollHeight;
    if (loadOlderMessagesButton) loadOlderMessagesButton.hidden = !conversationState.messageCursor;
  } catch (error) {
    if (conversationState.streamGeneration !== loadGeneration || conversationState.conversationId !== conversationId) return;
    setConversationRetryStatus(`消息加载失败：${error.message}`, () => loadConversationMessages(conversationId));
    conversationStatus.dataset.state = 'error';
  }
  finally {
    if (conversationState.messageLoadToken === loadToken) {
      conversationState.loadingMessages = false;
      conversationState.loadingConversationId = null;
      conversationState.messageLoadToken = null;
    }
  }
}

async function loadOlderConversationMessages() {
  if (!conversationState.conversationId || !conversationState.messageCursor) return;
  const conversationId = conversationState.conversationId;
  if (conversationState.loadingMessages && conversationState.loadingConversationId === conversationId) return;
  const loadGeneration = conversationState.streamGeneration;
  const loadToken = Symbol('conversation-older-message-load');
  conversationState.loadingConversationId = conversationId;
  conversationState.messageLoadToken = loadToken;
  conversationState.loadingMessages = true;
  const height = messages.scrollHeight; const top = messages.scrollTop;
  try {
    const params = new URLSearchParams({ before: conversationState.messageCursor, target_chars: String(targetCharsForMessages()) });
    const data = await conversationFetch(`/api/conversations/${encodeURIComponent(conversationId)}/messages?${params}`);
    if (conversationState.streamGeneration !== loadGeneration || conversationState.conversationId !== conversationId) return;
    const fragment = document.createDocumentFragment();
    const items = orderConversationMessages(data.messages || []);
    const rendered = items.map((item) => ({ item, element: renderConversationMessage(item) }));
    rendered.forEach(({ item, element }) => { element.dataset.messageId = item.message_id || ''; fragment.appendChild(element); });
    messages.insertBefore(fragment, messages.firstChild);
    enqueueConversationProcessingHydration(rendered, loadGeneration, conversationId);
    enqueueConversationMemoryHydration(rendered, loadGeneration, conversationId);
    conversationState.messageCursor = data.next_cursor || null;
    if (loadOlderMessagesButton) loadOlderMessagesButton.hidden = !conversationState.messageCursor;
    requestAnimationFrame(() => { messages.scrollTop = top + (messages.scrollHeight - height); });
  } catch (error) {
    if (conversationState.streamGeneration !== loadGeneration || conversationState.conversationId !== conversationId) return;
    setConversationRetryStatus(`更早消息加载失败：${error.message}`, () => loadOlderConversationMessages());
    conversationStatus.dataset.state = 'error';
  }
  finally {
    if (conversationState.messageLoadToken === loadToken) {
      conversationState.loadingMessages = false;
      conversationState.loadingConversationId = null;
      conversationState.messageLoadToken = null;
    }
  }
}

function abortConversationStream() {
  const activeAssistant = [...(messages?.querySelectorAll('.message.assistant[data-stream-active="true"]') || [])].at(-1);
  if (activeAssistant) {
    markConversationEventTerminal(activeAssistant, 'interrupted');
    activeAssistant.dataset.streamActive = 'false';
    activeAssistant.dataset.doneSeen = 'true';
    activeAssistant.classList.add('is-interrupted');
    addConversationErrorNotice(activeAssistant, Object.assign(new Error('本轮已中止'), { code: 'ABORTED' }));
  }
  messages?.querySelectorAll('.conversation-processing[data-running="true"]').forEach((processing) => {
    stopConversationProcessing(processing, 'interrupted', '处理过程已中断');
    collapseConversationProcessing(processing);
  });
  messages?.querySelectorAll('.conversation-reasoning[data-status="running"]').forEach((panel) => finalizeConversationReasoning(panel, 'interrupted'));
  conversationState.streamGeneration += 1;
  conversationState.openToken = null;
  if (conversationState.streamController) { conversationState.streamController.abort(); conversationState.streamController = null; }
}

async function openConversation(conversationId, { replace = false } = {}) {
  if (!conversationId) return;
  showView('chat');
  abortConversationStream();
  const openToken = Symbol('conversation-open');
  const openGeneration = conversationState.streamGeneration;
  conversationState.openToken = openToken;
  const isCurrent = () => conversationState.openToken === openToken && conversationState.streamGeneration === openGeneration && conversationState.conversationId === conversationId;
  conversationState.conversationId = conversationId; conversationState.messageCursor = null; updateConversationUrl(conversationId, replace);
  setConversationStatus('正在加载会话…', 'loading');
  try {
    const scopes = [null, ...projectState.items.map((item) => item.project_id).filter(Boolean)];
    let found = null;
    for (const scope of scopes) {
      const query = scope ? `&project_id=${encodeURIComponent(scope)}` : '';
      const conversations = await conversationFetch(`/api/conversations?limit=100${query}`);
      if (!isCurrent()) return;
      found = (conversations.conversations || []).find((item) => item.conversation_id === conversationId) || null;
      if (found) break;
    }
    if (!isCurrent()) return;
    conversationState.conversation = found;
    conversationState.projectId = conversationState.conversation?.project_id || null;
    conversationState.draftProjectId = conversationState.projectId;
    setReasoningEffort(conversationState.conversation?.reasoning_effort || reasoningOptionsState.defaultEffort, { remember: false });
    loadReasoningOptions(activeModel, { selectedEffort: conversationState.conversation?.reasoning_effort || null, source: 'session' });
    projectState.expandedProjectId = conversationState.projectId || projectState.expandedProjectId;
    renderProjectList(projectState.items);
    if (conversationState.projectId) await loadProjectConversations(conversationState.projectId);
    await loadConversationMessages(conversationId);
    if (!isCurrent()) return;
    stopContextFollow();
    await loadContextUsage();
    if (!isCurrent()) return;
    await loadConversationList({ append: false, guard: isCurrent });
    if (!isCurrent()) return;
    const title = document.querySelector('.breadcrumb strong'); if (title) title.textContent = conversationState.conversation?.title || '会话';
    const state = document.querySelector('.chat-state'); if (state) state.textContent = '已保存会话';
    updateGovernanceControls();
    setConversationStatus('');
  } catch (error) {
    if (!isCurrent()) return;
    setConversationStatus(`会话打开失败：${error.message}`, 'error');
  }
}

function beginDraft() {
  showView('chat'); abortConversationStream(); conversationState.conversationId = null; conversationState.conversation = null; conversationState.projectId = conversationState.draftProjectId || null; conversationState.messageCursor = null; workspace.classList.remove('has-started');
  setReasoningEffort(reasoningOptionsState.defaultEffort || reasoningOptionsState.lastEffort || 'off', { remember: false });
  if (window.location.pathname.startsWith('/c/')) window.history.replaceState({}, '', '/');
  const title = document.querySelector('.breadcrumb strong'); if (title) title.textContent = '新对话';
  const state = document.querySelector('.chat-state'); if (state) state.textContent = '新对话';
  if (conversationMemoryStatus) conversationMemoryStatus.textContent = '';
  resetConversationMessages(); loadConversationList(); input.focus();
  updateGovernanceControls();
}

async function createProject(event) {
  if (event.submitter?.value === 'cancel') { event.preventDefault(); projectDialog?.close(); return; }
  event?.preventDefault(); const name = projectDialogName?.value.trim(); if (!name) return;
  try {
    const project = await conversationFetch('/api/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) });
    if (projectDialogName) projectDialogName.value = ''; if (projectDialog?.open) projectDialog.close();
    conversationState.draftProjectId = project.project_id; projectState.expandedProjectId = project.project_id; await loadProjects(); beginDraft();
  } catch (error) { setConversationStatus(`项目创建失败：${error.message}`, 'error'); }
}

// Native form validation runs before a submit event.  The project name is
// required, so an empty form must close from the click path rather than wait
// for the submit handler to see the cancel submitter.
function closeDialogFromCancelClick(event) {
  const cancelButton = event.target?.closest?.('button[value="cancel"]');
  if (!cancelButton) return;
  event.preventDefault();
  const dialog = cancelButton.form?.closest('dialog');
  if (dialog === conversationActionDialog || dialog === conversationConfirmDialog) {
    dialogState.action = null;
    dialogState.target = null;
  }
  dialog?.close('cancel');
}

function selectedProject() {
  return projectState.items.find((item) => item.project_id === conversationState.projectId) || null;
}

function updateGovernanceControls() {
  // Task09 keeps governance actions in row menus and dialogs; this hook remains
  // as a no-op for message and memory code that updates controls after opening.
}

async function submitActionDialog(event) {
  if (event.submitter?.value === 'cancel') { event.preventDefault(); conversationActionDialog?.close(); dialogState.action = null; dialogState.target = null; return; }
  event.preventDefault(); const { action, target } = dialogState;
  try {
    if (action === 'rename-project' || action === 'rename-conversation') {
      const value = conversationActionName.value.trim(); if (!value || value === (target.name || target.title)) return;
      const endpoint = action === 'rename-project' ? `/api/projects/${encodeURIComponent(target.project_id)}` : `/api/conversations/${encodeURIComponent(target.conversation_id)}`;
      const updated = await conversationFetch(endpoint, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(action === 'rename-project' ? { name: value } : { title: value }) });
      if (action === 'rename-conversation' && conversationState.conversationId === target.conversation_id) { conversationState.conversation = updated; const breadcrumb = document.querySelector('.breadcrumb strong'); if (breadcrumb) breadcrumb.textContent = value; }
      await loadProjects(); await loadConversationList(); if (target.project_id) await loadProjectConversations(target.project_id); setConversationStatus(action === 'rename-project' ? '项目已重命名' : '会话已重命名');
    } else if (action === 'move-conversation') {
      const targetProjectId = conversationActionProject.value || null; if (!targetProjectId) return;
      await moveConversation(target, targetProjectId, conversationActionHistory.checked);
    }
    conversationActionDialog.close(); dialogState.restoreFocus?.focus();
  } catch (error) { conversationActionStatus.textContent = `操作失败：${error.message}`; }
}

async function submitConfirmDialog(event) {
  if (event.submitter?.value === 'cancel') { event.preventDefault(); conversationConfirmDialog?.close(); dialogState.action = null; dialogState.target = null; return; }
  event.preventDefault(); const { action, target } = dialogState;
  try {
    if (action === 'project-delete' || action === 'conversation-delete') {
      const endpoint = action === 'project-delete' ? `/api/projects/${encodeURIComponent(target.project_id)}` : `/api/conversations/${encodeURIComponent(target.conversation_id)}`;
      await conversationFetch(endpoint, { method: 'DELETE' }); if (action === 'conversation-delete' && conversationState.conversationId === target.conversation_id) beginDraft(); if (action === 'project-delete') { if (conversationState.projectId === target.project_id || conversationState.draftProjectId === target.project_id) { conversationState.projectId = null; conversationState.draftProjectId = null; beginDraft(); } projectState.expandedProjectId = projectState.expandedProjectId === target.project_id ? null : projectState.expandedProjectId; projectState.conversations.delete(target.project_id); projectState.showArchived = false; }
      await loadProjects(); await loadConversationList(); setConversationStatus(action === 'project-delete' ? '项目已删除；文档原件仍保留' : '会话已删除；记忆未联动删除');
    } else {
      const nextStatus = target.status === 'archived' ? 'active' : 'archived'; const endpoint = action === 'project-status' ? `/api/projects/${encodeURIComponent(target.project_id)}` : `/api/conversations/${encodeURIComponent(target.conversation_id)}`; const updated = await conversationFetch(endpoint, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: nextStatus }) });
      if (action === 'conversation-status' && conversationState.conversationId === target.conversation_id) conversationState.conversation = updated; await loadProjects(); await loadConversationList(); if (target.project_id) await loadProjectConversations(target.project_id); setConversationStatus(nextStatus === 'archived' ? '已归档' : '已恢复');
    }
    conversationConfirmDialog.close(); dialogState.restoreFocus?.focus();
  } catch (error) { setConversationStatus(`操作失败：${error.message}`, 'error'); }
}

const MEMORY_STATUS_LABELS = { candidate: '待确认', active: '有效', superseded: '旧版本', disabled: '已停用', deleted: '已删除' };
const MEMORY_SCOPE_LABELS = { global: '全局', project: '项目' };

function setMemoryStatus(text, state = '') {
  if (!memoryStatus) return;
  memoryStatus.textContent = text || '';
  if (state) memoryStatus.dataset.state = state; else delete memoryStatus.dataset.state;
}

function setSystemRuleStatus(text, state = '') {
  [systemRuleStatus, systemRuleDialogStatus, systemRuleClearStatus].forEach((node) => {
    if (!node) return;
    node.textContent = text || '';
    if (state) node.dataset.state = state; else delete node.dataset.state;
  });
}

function renderSystemRule() {
  if (!systemRuleCard) return;
  const content = String(systemRuleState.content || '');
  if (systemRuleContent) systemRuleContent.textContent = content || '尚未设置系统规则。';
  if (systemRuleStatusBadge) {
    systemRuleStatusBadge.dataset.enabled = systemRuleState.enabled ? 'true' : 'false';
    systemRuleStatusBadge.textContent = systemRuleState.enabled ? '已启用' : '已停用';
  }
  if (systemRuleUpdated) systemRuleUpdated.textContent = systemRuleState.updatedAt ? `更新时间：${systemRuleState.updatedAt}` : '';
  if (systemRuleToggleButton) {
    systemRuleToggleButton.textContent = systemRuleState.enabled ? '停用' : '启用';
    systemRuleToggleButton.disabled = !content && !systemRuleState.enabled;
  }
  if (systemRuleEditButton) systemRuleEditButton.disabled = systemRuleState.loading;
  if (systemRuleClearButton) systemRuleClearButton.disabled = systemRuleState.loading || (!content && !systemRuleState.enabled);
}

async function loadSystemRule() {
  if (!systemRuleCard || systemRuleState.loading) return;
  systemRuleState.loading = true; renderSystemRule(); setSystemRuleStatus('正在读取系统规则…');
  try {
    const data = await conversationFetch('/api/system-rule');
    const rule = data?.system_rule || data?.rule || data || {};
    systemRuleState.content = String(rule.content || '');
    systemRuleState.enabled = Boolean(rule.enabled) && Boolean(systemRuleState.content);
    systemRuleState.updatedAt = rule.updated_at || rule.updatedAt || null;
    systemRuleState.loaded = true;
    setSystemRuleStatus('');
  } catch (error) {
    setSystemRuleStatus(`系统规则读取失败：${error.message}`, 'error');
  } finally {
    systemRuleState.loading = false; renderSystemRule();
  }
}

function updateSystemRuleCount() {
  if (!systemRuleCount || !systemRuleInput) return;
  const length = Array.from(systemRuleInput.value).length;
  systemRuleCount.textContent = `${length} / 12000`;
  systemRuleCount.dataset.overLimit = length > 12000 ? 'true' : 'false';
}

function openSystemRuleEditor(prefill = null) {
  if (!systemRuleDialog || !systemRuleInput) return;
  systemRuleInput.value = prefill === null ? systemRuleState.content : String(prefill);
  if (systemRuleEnabledInput) systemRuleEnabledInput.checked = Boolean(systemRuleState.enabled);
  setSystemRuleStatus(''); updateSystemRuleCount(); systemRuleDialog.showModal(); systemRuleInput.focus();
}

async function saveSystemRule(event) {
  if (event?.submitter?.value === 'cancel') { event.preventDefault(); systemRuleDialog?.close('cancel'); return; }
  event?.preventDefault();
  const content = String(systemRuleInput?.value || '');
  if (Array.from(content).length > 12000) { setSystemRuleStatus('系统规则最多 12,000 个 Unicode 字符，请缩短后再保存。', 'error'); return; }
  const enabled = Boolean(systemRuleEnabledInput?.checked);
  try {
    systemRuleState.loading = true; renderSystemRule(); setSystemRuleStatus('正在保存系统规则…');
    const data = await conversationFetch('/api/system-rule', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content, enabled }) });
    const rule = data?.system_rule || data?.rule || data || {};
    systemRuleState.content = String(rule.content ?? content);
    systemRuleState.enabled = Boolean(rule.enabled ?? enabled);
    systemRuleState.updatedAt = rule.updated_at || rule.updatedAt || null;
    systemRuleState.loaded = true; systemRuleDialog?.close(); setSystemRuleStatus('系统规则已保存');
  } catch (error) { setSystemRuleStatus(`系统规则保存失败：${error.message}`, 'error'); }
  finally { systemRuleState.loading = false; renderSystemRule(); }
}

async function toggleSystemRule() {
  if (!systemRuleState.content && !systemRuleState.enabled) { openSystemRuleEditor(); return; }
  try {
    systemRuleState.loading = true; renderSystemRule(); setSystemRuleStatus('正在更新系统规则状态…');
    const data = await conversationFetch('/api/system-rule', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: !systemRuleState.enabled }) });
    const rule = data?.system_rule || data?.rule || data || {};
    systemRuleState.content = String(rule.content ?? systemRuleState.content);
    systemRuleState.enabled = Boolean(rule.enabled);
    systemRuleState.updatedAt = rule.updated_at || rule.updatedAt || systemRuleState.updatedAt;
    setSystemRuleStatus(systemRuleState.enabled ? '系统规则已启用' : '系统规则已停用');
  } catch (error) { setSystemRuleStatus(`系统规则状态更新失败：${error.message}`, 'error'); }
  finally { systemRuleState.loading = false; renderSystemRule(); }
}

function openSystemRuleClearDialog() {
  if (!systemRuleClearDialog) return;
  setSystemRuleStatus(''); systemRuleClearDialog.showModal(); systemRuleClearSubmit?.focus();
}

async function clearSystemRule(event) {
  if (event?.submitter?.value === 'cancel') { event.preventDefault(); systemRuleClearDialog?.close('cancel'); return; }
  event?.preventDefault();
  try {
    systemRuleState.loading = true; renderSystemRule(); setSystemRuleStatus('正在清空系统规则…');
    await conversationFetch('/api/system-rule', { method: 'DELETE' });
    systemRuleState.content = ''; systemRuleState.enabled = false; systemRuleState.updatedAt = null; systemRuleState.loaded = true;
    systemRuleClearDialog?.close(); setSystemRuleStatus('系统规则已清空');
  } catch (error) { setSystemRuleStatus(`系统规则清空失败：${error.message}`, 'error'); }
  finally { systemRuleState.loading = false; renderSystemRule(); }
}

function captureMemoryViewState() {
  if (!memoryView || memoryView.hidden) return;
  memoryNavigationSnapshot.scope = memoryScopeSelect?.value || 'global';
  memoryNavigationSnapshot.status = memoryStatusSelect?.value || 'active';
  memoryNavigationSnapshot.projectId = memoryProjectSelect?.value || null;
  memoryNavigationSnapshot.scrollTop = Number(window.scrollY || document.documentElement?.scrollTop || 0);
  memoryNavigationSnapshot.projectCollapsed = projectState.collapsed;
  memoryNavigationSnapshot.expandedProjectId = projectState.expandedProjectId;
}

function restoreMemoryViewState() {
  if (!memoryView || memoryNavigationSnapshot.scope === null) return;
  if (memoryScopeSelect) memoryScopeSelect.value = memoryNavigationSnapshot.scope;
  if (memoryStatusSelect) memoryStatusSelect.value = memoryNavigationSnapshot.status || 'active';
  if (memoryProjectSelect && memoryNavigationSnapshot.projectId) memoryProjectSelect.value = memoryNavigationSnapshot.projectId;
  const isProject = memoryScopeSelect?.value === 'project';
  if (memoryProjectLabel) memoryProjectLabel.hidden = !isProject;
  projectState.collapsed = Boolean(memoryNavigationSnapshot.projectCollapsed);
  projectState.expandedProjectId = memoryNavigationSnapshot.expandedProjectId || null;
  projectTreeToggle?.setAttribute('aria-expanded', projectState.collapsed ? 'false' : 'true');
  renderProjectList(projectState.items);
  window.requestAnimationFrame(() => window.scrollTo(0, memoryNavigationSnapshot.scrollTop || 0));
  loadMemories();
}

function systemRuleSuggestionFromText(text) {
  const value = String(text || '');
  if (!/设为系统规则/.test(value)) return '';
  const suggestion = value.replace(/^[\s，,:：；;。.!！?？]*设为系统规则[\s，,:：；;。.!！?？-]*/u, '').trim();
  return suggestion || value.trim();
}

function attachSystemRuleSuggestion(message, text) {
  const suggestion = systemRuleSuggestionFromText(text);
  if (!suggestion || !message) return;
  const bubble = message.querySelector('.bubble');
  if (!bubble || bubble.querySelector('[data-system-rule-suggestion]')) return;
  const hint = document.createElement('p'); hint.className = 'system-rule-suggestion'; hint.textContent = '识别到系统规则建议；保存前请先确认。';
  const button = document.createElement('button'); button.type = 'button'; button.className = 'secondary-button'; button.dataset.systemRuleSuggestion = 'true'; button.textContent = '预填系统规则编辑器';
  button.addEventListener('click', () => openSystemRuleEditor(suggestion));
  bubble.append(hint, button);
}

function openConversationFromWorkspace(conversationId) {
  if (!conversationId) return;
  captureMemoryViewState();
  showView('chat');
  openConversation(conversationId);
}

function renderMemoryProjectOptions(projects) {
  if (!memoryProjectSelect) return;
  memoryProjectSelect.replaceChildren();
  for (const project of projects || []) {
    const option = document.createElement('option'); option.value = project.project_id; option.textContent = project.name || '未命名项目'; memoryProjectSelect.appendChild(option);
  }
  if (conversationState.projectId) memoryProjectSelect.value = conversationState.projectId;
}

function renderMemoryEvidence(memoryId, evidence, container) {
  if (!container) return;
  container.replaceChildren();
  const heading = document.createElement('strong'); heading.textContent = '来源记录'; container.appendChild(heading);
  if (!evidence?.length) { const empty = document.createElement('span'); empty.textContent = '暂无可见来源'; container.appendChild(empty); return; }
  for (const item of evidence) {
    const row = document.createElement('div');
    const details = document.createElement('span');
    details.textContent = [item.evidence_type || '来源', item.excerpt || ''].filter(Boolean).join(' · ');
    row.appendChild(details);
    if (item.conversation_id) {
      const open = document.createElement('button'); open.type = 'button'; open.className = 'secondary-button memory-open-conversation'; open.dataset.openConversation = item.conversation_id; open.textContent = '打开来源会话';
      row.appendChild(open);
    }
    container.appendChild(row);
  }
  memoryState.evidence.set(memoryId, evidence);
}

function renderMemoryList(items) {
  if (!memoryList) return;
  memoryList.replaceChildren();
  for (const item of items || []) {
    const card = document.createElement('article'); card.className = 'memory-item'; card.dataset.memoryId = item.memory_id; card.setAttribute('role', 'listitem');
    const head = document.createElement('div'); head.className = 'memory-item-head';
    const scope = document.createElement('span'); scope.className = 'memory-scope'; scope.textContent = MEMORY_SCOPE_LABELS[item.scope] || item.scope || '未知作用域';
    const state = document.createElement('span'); state.className = 'memory-status-badge'; state.dataset.status = item.status || ''; state.textContent = MEMORY_STATUS_LABELS[item.status] || item.status || '未知状态';
    head.append(scope, state);
    const statement = document.createElement('p'); statement.className = 'memory-statement'; statement.textContent = item.statement || '';
    const meta = document.createElement('span'); meta.className = 'memory-meta'; meta.textContent = `${item.category || '未分类'} · 来源 ${item.source_kind || 'unknown'} · 置信度 ${Math.round(Number(item.confidence || 0) * 100)}%`;
    const actions = document.createElement('div'); actions.className = 'memory-item-actions';
    const addAction = (label, action, className = 'secondary-button') => { const button = document.createElement('button'); button.type = 'button'; button.className = className; button.dataset.memoryAction = action; button.dataset.memoryId = item.memory_id; button.textContent = label; actions.appendChild(button); };
    addAction('查看来源', 'source');
    if (item.status === 'candidate') addAction('确认候选', 'confirm', 'send-button');
    if (item.status === 'deleted') addAction('撤销', 'undo');
    else if (item.status !== 'superseded') { addAction('编辑为新版本', 'edit'); addAction('停用', 'disable'); addAction('删除', 'delete', 'secondary-button danger-button'); }
    const evidence = document.createElement('div'); evidence.className = 'memory-evidence'; evidence.hidden = true; evidence.dataset.memoryEvidence = item.memory_id;
    const sourceConversationId = item.conversation_id || item.source_conversation_id || item.evidence?.conversation_id;
    if (sourceConversationId) {
      const openSource = document.createElement('button'); openSource.type = 'button'; openSource.className = 'secondary-button memory-open-conversation'; openSource.dataset.openConversation = sourceConversationId; openSource.textContent = '打开来源会话'; actions.appendChild(openSource);
    }
    card.append(head, statement, meta, actions, evidence); memoryList.appendChild(card);
  }
  if (memoryEmpty) memoryEmpty.hidden = Boolean(items?.length);
}

async function loadMemories() {
  if (!memoryList || memoryState.loading) return;
  memoryState.loading = true; setMemoryStatus('正在加载记忆…');
  const scope = memoryScopeSelect?.value || 'global'; const status = memoryStatusSelect?.value || 'active';
  const params = new URLSearchParams({ scope, status });
  if (scope === 'project' && memoryProjectSelect?.value) params.set('project_id', memoryProjectSelect.value);
  try {
    const data = await conversationFetch(`/api/memories?${params}`); memoryState.items = data.memories || []; renderMemoryList(memoryState.items); setMemoryStatus(`已加载 ${memoryState.items.length} 条${MEMORY_SCOPE_LABELS[scope] || ''}记忆`);
  } catch (error) { renderMemoryList([]); setMemoryStatus(`记忆加载失败：${error.message}`, 'error'); }
  finally { memoryState.loading = false; }
}

async function createManualMemory() {
  const statement = window.prompt('输入要长期保留的记忆陈述')?.trim();
  if (!statement) return;
  const scope = memoryScopeSelect?.value || 'global'; const projectId = scope === 'project' ? memoryProjectSelect?.value || null : null;
  if (scope === 'project' && !projectId) { setMemoryStatus('请先选择项目', 'error'); return; }
  try {
    await conversationFetch('/api/memories', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scope, project_id: projectId, statement, source_kind: 'manual', category: scope === 'project' ? 'project_rule' : 'user_preference', status: 'active' }) });
    await loadMemories(); setMemoryStatus('记忆已创建');
  } catch (error) { setMemoryStatus(`记忆创建失败：${error.message}`, 'error'); }
}

async function handleMemoryAction(action, memoryId, card) {
  const memory = memoryState.items.find((item) => item.memory_id === memoryId);
  if (!memory) return;
  try {
    if (action === 'source') {
      const evidence = card.querySelector(`[data-memory-evidence="${CSS.escape(memoryId)}"]`);
      if (!evidence.hidden) { evidence.hidden = true; return; }
      const data = await conversationFetch(`/api/memories/${encodeURIComponent(memoryId)}/evidence`); renderMemoryEvidence(memoryId, data.evidence || [], evidence); evidence.hidden = false; return;
    }
    if (action === 'confirm') await conversationFetch(`/api/memories/${encodeURIComponent(memoryId)}/confirm`, { method: 'POST' });
    if (action === 'edit') {
      const statement = window.prompt('编辑为新版本（旧版本和来源会保留）', memory.statement)?.trim();
      if (!statement || statement === memory.statement) return;
      await conversationFetch(`/api/memories/${encodeURIComponent(memoryId)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ statement }) });
    }
    if (action === 'disable') {
      if (!window.confirm('停用这条记忆？它将不再参与召回，但仍保留审计记录。')) return;
      await conversationFetch(`/api/memories/${encodeURIComponent(memoryId)}/disable`, { method: 'POST' });
    }
    if (action === 'delete') {
      if (!window.confirm('删除这条记忆？系统会保留可撤销的治理记录。')) return;
      await conversationFetch(`/api/memories/${encodeURIComponent(memoryId)}`, { method: 'DELETE' });
    }
    if (action === 'undo') await conversationFetch(`/api/memories/${encodeURIComponent(memoryId)}/undo`, { method: 'POST' });
    await loadMemories(); setMemoryStatus('记忆治理操作已完成');
  } catch (error) { setMemoryStatus(`记忆操作失败：${error.message}`, 'error'); }
}

function appendConversationEvent(assistantMessage, processing, eventData) {
  if (eventData.type === 'progress') updateConversationProcessing(processing, eventData);
  if (eventData.type === 'memory') showConversationMemoryNotice(assistantMessage?.querySelector('.bubble'), eventData);
  if (eventData.type === 'skill_activation') {
    updateConversationIntake(assistantMessage, {
      status: eventData.status === 'failed' ? 'failed' : 'running',
      skill: { name: eventData.skill, description: eventData.description },
    });
  }
  if (eventData.type === 'intake') updateConversationIntake(assistantMessage, eventData);
  if (eventData.type === 'reconnect') {
    stopConversationProcessing(processing, 'skipped', '连接中断，可重试');
    updateConversationProcessing(processing, {
      step_id: eventData.step_id || 'connection',
      kind: 'connection',
      label: '连接状态',
      status: 'skipped',
      summary: '连接中断，可重试',
    });
    collapseConversationProcessing(processing);
    if (conversationStatus) conversationStatus.textContent = '正在重新连接…';
  }
}

async function sendConversationMessage(question, { appendUser = true, userBubble = null } = {}) {
  // 校验不通过时直接返回，绝不留下空的乐观卡片。
  if (!String(question || '').trim()) return;
  abortConversationStream(); const generation = conversationState.streamGeneration; const controller = new AbortController(); conversationState.streamController = controller;
  workspace.classList.add('has-started');
  setConversationStatus('模型正在准备…');
  const userMessage = appendUser
    ? addMessage(question, 'user')
    : (userBubble || [...messages.querySelectorAll('.message.user')].at(-1));
  const payload = { content: question, mode: modeSelect.value, model: modelSelect.value, reasoning_effort: pickSendReasoningEffort(reasoningOptionsState.loadState, reasoningEffortSelect?.value, reasoningOptionsState.lastEffort) };
  const endpoint = conversationState.conversationId ? `/api/conversations/${encodeURIComponent(conversationState.conversationId)}/messages` : '/api/conversations/messages';
  if (!conversationState.conversationId && conversationState.projectId) payload.project_id = conversationState.projectId;
  // 乐观建卡：在 await fetch 之前就把卡片插进聊天流，避免协议建立前的空白等待。
  let assistantMessage = createAssistantMessage(activeModel);
  setConversationPending(assistantMessage);
  let processing = null; let writer = null; let streamError = null; let userMessageId = null;
  let sourcesRenderer = null; let pendingSources = null; let generationCompleted = false; let doneReceived = false;
  try {
    const response = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: controller.signal });
    if (!response.ok) { let data = null; try { data = await response.json(); } catch (_) {} const error = new Error(conversationError(data)); error.code = data?.detail?.code ?? data?.code; error.status = response.status; error.effort = payload.reasoning_effort; error.retryable = data?.detail?.retryable ?? data?.retryable ?? false; throw error; }
    const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
    const handleSse = (chunk) => {
      const line = chunk.split('\n').find((item) => item.startsWith('data: ')); if (!line) return;
      let eventData; try { eventData = JSON.parse(line.slice(6)); } catch (_) { return; }
      if (streamError) return;
      if (eventData.type === 'meta') {
        if (assistantMessage.dataset.metaSeen !== 'true') {
          const metaSeq = Number(eventData.event_seq);
          if (!Number.isInteger(metaSeq) || metaSeq !== 1) {
            streamError = Object.assign(new Error('事件流中断：首个 meta 序号无效'), { code: 'STREAM_INTERRUPTED', retryable: true });
            return;
          }
          // 填充乐观卡片，绝不新建第二张。
          if (!acceptConversationEvent(assistantMessage, eventData)) {
            streamError = Object.assign(new Error('事件流中断：首个 meta 未被接受'), { code: 'STREAM_INTERRUPTED', retryable: true });
            return;
          }
          assistantMessage.dataset.metaSeen = 'true';
          clearConversationPending(assistantMessage);
          const modelTag = assistantMessage.querySelector('.model-tag');
          if (modelTag) modelTag.textContent = `${eventData.model || activeModel}${modeSelect.value === 'developer' ? ' · Developer' : ''}`;
        } else if (!acceptConversationEvent(assistantMessage, eventData)) {
          if (assistantMessage.dataset.sequenceGap === 'true') {
            assistantMessage.dataset.streamActive = 'false';
            assistantMessage.classList.add('is-interrupted');
            finalizeConversationReasoning(assistantMessage.querySelector('.conversation-reasoning'), 'interrupted');
            stopConversationProcessing(processing, 'interrupted', '事件流中断');
            collapseConversationProcessing(processing);
          }
          return;
        }
        userMessageId = eventData.user_message_id || userMessageId;
        if (userMessageId) userMessage.dataset.messageId = userMessageId;
        if (eventData.conversation_id && !conversationState.conversationId) {
          conversationState.conversationId = eventData.conversation_id; conversationState.conversation = { conversation_id: eventData.conversation_id, project_id: eventData.project_id || conversationState.projectId, title: question.slice(0, 80), status: 'active' }; updateConversationUrl(eventData.conversation_id); updateGovernanceControls(); loadConversationList();
        }
        processing = createConversationProcessing(assistantMessage); sourcesRenderer = createConversationSources(assistantMessage); writer = createMarkdownWriter(assistantMessage.querySelector('.answer'), messages);
        if (eventData.assistant_message_id) assistantMessage.dataset.messageId = eventData.assistant_message_id;
        if (eventData.user_message_id) assistantMessage.dataset.parentMessageId = eventData.user_message_id;
        assistantMessage.dataset.reasoningEffort = normalizeReasoningEffort(eventData.reasoning_effort || payload.reasoning_effort);
        assistantMessage.dataset.streamActive = 'true';
        setConversationStatus(assistantMessage.dataset.reasoningEffort === 'off' ? '正在生成回答…' : '模型正在准备思考…');
      } else if (!acceptConversationEvent(assistantMessage, eventData)) {
        if (assistantMessage?.dataset.sequenceGap === 'true') {
          assistantMessage.dataset.streamActive = 'false';
          assistantMessage.classList.add('is-interrupted');
          finalizeConversationReasoning(assistantMessage.querySelector('.conversation-reasoning'), 'interrupted');
          stopConversationProcessing(processing, 'interrupted', '事件流中断');
          collapseConversationProcessing(processing);
        }
        return;
      }
      if (eventData.type === 'progress') appendConversationEvent(assistantMessage, processing, eventData);
      else if (eventData.type === 'memory') appendConversationEvent(assistantMessage, processing, eventData);
      else if (eventData.type === 'reconnect') appendConversationEvent(assistantMessage, processing, eventData);
      else if (eventData.type === 'skill_activation') appendConversationEvent(assistantMessage, processing, eventData);
      else if (eventData.type === 'intake') appendConversationEvent(assistantMessage, processing, eventData);
      else if (eventData.type === 'reasoning_started') {
        const effort = assistantMessage?.dataset.reasoningEffort || payload.reasoning_effort;
        if (effort !== 'off') {
          setConversationStatus('模型正在思考…');
          const panel = createConversationReasoning(assistantMessage, { effort, status: 'running' });
          updateConversationReasoning(panel, { status: 'running' });
        }
      } else if (eventData.type === 'reasoning_delta') {
        const effort = assistantMessage?.dataset.reasoningEffort || payload.reasoning_effort;
        if (effort !== 'off') {
          const panel = createConversationReasoning(assistantMessage, { effort, status: 'running' });
          updateConversationReasoning(panel, { content: eventData.content || '' });
        }
      } else if (eventData.type === 'reasoning_completed') {
        finalizeConversationReasoning(assistantMessage?.querySelector('.conversation-reasoning'), eventData.status || 'completed', eventData.duration_ms);
      } else if (eventData.type === 'token' && assistantMessage && writer) {
        const panel = assistantMessage.querySelector('.conversation-reasoning');
        if (panel?.dataset.status === 'running') finalizeConversationReasoning(panel, 'completed');
        writer.write(eventData.content || '');
      } else if (eventData.type === 'sources') { pendingSources = eventData.sources || eventData.citations || []; if (generationCompleted && sourcesRenderer) sourcesRenderer.render(pendingSources); }
      else if (eventData.type === 'error') {
        streamError = new Error(eventData.message || eventData.detail || '请求失败');
        assistantMessage.dataset.errorSeen = 'true';
        const panel = assistantMessage?.querySelector('.conversation-reasoning');
        finalizeConversationReasoning(panel, eventData.code === 'STREAM_INTERRUPTED' ? 'interrupted' : 'failed', eventData.duration_ms);
        pendingSources = null; if (sourcesRenderer) sourcesRenderer.clear(); if (assistantMessage) showConversationMemoryNotice(assistantMessage.querySelector('.bubble'), { status: 'not_saved', message: streamError.message });
        finalizeConversationIntake(assistantMessage?.querySelector('.conversation-intake'), 'failed');
      }
      else if (eventData.type === 'done') {
        doneReceived = true;
        const doneStatus = assistantMessage?.dataset.sequenceGap === 'true'
          ? 'interrupted'
          : (assistantMessage?.dataset.errorSeen === 'true' ? 'failed' : (['completed', 'failed', 'interrupted'].includes(eventData.status) ? eventData.status : 'failed'));
        assistantMessage.dataset.doneSeen = 'true';
        assistantMessage.dataset.streamActive = 'false';
        finalizeConversationReasoning(assistantMessage?.querySelector('.conversation-reasoning'), doneStatus, eventData.reasoning_duration_ms);
        finalizeConversationIntake(assistantMessage?.querySelector('.conversation-intake'), doneStatus);
        markConversationEventTerminal(assistantMessage, doneStatus);
        stopConversationProcessing(processing, doneStatus === 'completed' ? 'completed' : doneStatus, doneStatus === 'completed' ? '处理完成' : '处理过程已结束'); collapseConversationProcessing(processing);
        if (doneStatus !== 'completed' && sourcesRenderer) sourcesRenderer.clear(); if (assistantMessage && doneStatus !== 'completed') assistantMessage.classList.add(`is-${doneStatus}`); if (assistantMessage && userMessageId && doneStatus === 'completed') startMemoryAnalysisPolling(userMessageId, assistantMessage, conversationState.projectId); const state = document.querySelector('.chat-state'); if (state) state.textContent = doneStatus === 'completed' ? '已保存' : doneStatus;
      }
      if (!KNOWN_CONVERSATION_EVENT_TYPES.has(eventData.type)) console.debug('Ignored conversation event type:', eventData.type);
      if (eventData.type === 'progress' && eventData.kind === 'generation' && eventData.status === 'completed') { generationCompleted = true; if (pendingSources && sourcesRenderer) sourcesRenderer.render(pendingSources); }
    };
    while (true) { const result = await reader.read(); if (result.done) break; if (generation !== conversationState.streamGeneration) return; buffer += decoder.decode(result.value, { stream: true }); const chunks = buffer.split('\n\n'); buffer = chunks.pop(); chunks.forEach(handleSse); }
    if (buffer.trim()) handleSse(buffer);
    if (!doneReceived && !controller.signal.aborted && generation === conversationState.streamGeneration) {
      finalizeConversationReasoning(assistantMessage?.querySelector('.conversation-reasoning'), 'interrupted');
      markConversationEventTerminal(assistantMessage, 'interrupted');
      if (assistantMessage) assistantMessage.dataset.streamActive = 'false';
      stopConversationProcessing(processing, 'failed', '流式连接中断，可重试');
      collapseConversationProcessing(processing);
      pendingSources = null;
      if (sourcesRenderer) sourcesRenderer.clear();
      if (assistantMessage) {
        assistantMessage.classList.add('is-interrupted');
        showConversationMemoryNotice(assistantMessage.querySelector('.bubble'), { status: 'not_saved', message: '流式连接中断，已保存已生成内容' });
      }
      streamError = new Error('流式连接中断');
      streamError.connectionInterrupted = true;
    }
    if (streamError) throw streamError;
  } catch (error) {
    if (error.name === 'AbortError' || generation !== conversationState.streamGeneration) {
      // 被新一轮发送中止：卡片若仍停在占位阶段就清掉占位，避免永久「模型正在准备…」。
      if (assistantMessage?.dataset.phase === 'pending') {
        clearConversationPending(assistantMessage);
        assistantMessage.dataset.phase = 'aborted';
        assistantMessage.dataset.streamActive = 'false';
      }
      return;
    }
    if (error.connectionInterrupted) { if (writer) writer.flush(); }
    else if (writer) writer.cancel();
    if (processing) { updateConversationProcessing(processing, { step_id: 'connection', kind: 'connection', label: '连接状态', status: error.retryable ? 'skipped' : 'failed', summary: error.retryable ? '连接中断，可重试' : '连接失败' }); stopConversationProcessing(processing, error.retryable ? 'skipped' : 'failed', error.retryable ? '连接中断，可重试' : '连接失败'); collapseConversationProcessing(processing); }
    finalizeConversationReasoning(assistantMessage?.querySelector('.conversation-reasoning'), error.connectionInterrupted || error.retryable ? 'interrupted' : 'failed');
    if (assistantMessage) {
      assistantMessage.dataset.streamActive = 'false';
      if (error.name !== 'AbortError') markConversationEventTerminal(assistantMessage, error.connectionInterrupted || error.retryable ? 'interrupted' : 'failed');
    }
    if (sourcesRenderer) sourcesRenderer.clear();
    // 失败终态：卡片就地转错误态，不移除、不把内容回填输入框。
    if (assistantMessage) renderConversationFailure(assistantMessage, error, { question, userMessage });
    else if (!streamError) addConversationError(error, { question });
  } finally {
    if (writer) writer.flush(); if (conversationState.streamController === controller) conversationState.streamController = null; sendButton.disabled = false; sendButton.innerHTML = sendLabel; input.focus(); autoGrowInput(); loadConversationList(); loadContextUsage();
  }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault(); const question = input.value.trim(); if (!question || sendButton.disabled) return; input.value = ''; sendButton.disabled = true; sendButton.innerHTML = '<span class="sending-indicator">•••</span>'; await sendConversationMessage(question);
});

messages.addEventListener('click', async (event) => {
  const action = event.target.closest('.candidate-action');
  if (!action) return;
  action.disabled = true;
  action.textContent = '处理中...';
  try {
    const isLoginResume = action.classList.contains('login-action');
    const endpoint = isLoginResume
      ? `/api/agent/tasks/${action.dataset.taskId}/human-actions/login-completed`
      : '/api/agent/articles/download';
    const response = await fetch(endpoint, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: action.dataset.taskId, candidate_id: action.dataset.candidateId }),
    });
    const data = await response.json();
    if (!response.ok) {
      const detail = typeof data.detail === 'object' ? data.detail.user_message : data.detail;
      throw new Error(detail || '下载失败');
    }
    if (data.status === 'waiting_login') {
      action.disabled = false;
      action.textContent = '已完成登录';
      action.classList.add('login-action');
      if (data.login_url) window.open(data.login_url, '_blank', 'noopener,noreferrer');
      addMessage(`请在 ${data.source_name || '目标网站'} 完成登录，然后点击“已完成登录”。`, 'assistant');
    } else {
      action.textContent = '下载完成';
      addMessage(data.user_message ? `${data.user_message} ${data.file_path || ''}` : `文章已下载：${data.file_path}`, 'assistant');
    }
  } catch (error) {
    action.disabled = false;
    action.textContent = '重试下载';
    addMessage(`下载结果：${error.message}`, 'assistant');
  }
});

mobileNavToggle?.addEventListener('click', () => {
  if (mobileSidebar?.classList.contains('mobile-nav-open')) closeMobileDrawer(true);
  else openMobileDrawer();
});
mobileNavClose?.addEventListener('click', () => closeMobileDrawer(true));
mobileNavBackdrop?.addEventListener('click', () => closeMobileDrawer(true));
mobileSidebar?.addEventListener('click', (event) => {
  if (!mobileSidebar.classList.contains('mobile-nav-open')) return;
  if (event.target.closest('.mobile-nav-close')) return;
  if (event.target.closest('#new-project-button')) { closeMobileDrawer(false); return; }
  if (event.target.closest('.project-item-menu, .conversation-item-menu, .project-tree-menu-trigger, .conversation-list-menu-trigger')) return;
  if (event.target.closest('button, .nav-item')) closeMobileDrawer(true);
});

newChatButton.addEventListener('click', () => {
  window.currentAgentTaskId = null;
  clearSkillHint();
  beginDraft();
});

if (newProjectButton) newProjectButton.addEventListener('click', () => { dialogState.restoreFocus = mobileTriggerIsVisible() ? mobileNavToggle : newProjectButton; projectDialogName.value = ''; projectDialog?.showModal(); projectDialogName?.focus(); });
if (projectDialogForm) projectDialogForm.addEventListener('submit', createProject);
for (const dialogForm of [projectDialogForm, conversationActionForm, conversationConfirmForm]) {
  dialogForm?.addEventListener('click', closeDialogFromCancelClick);
}
if (projectTreeToggle) projectTreeToggle.addEventListener('click', () => { projectState.collapsed = !projectState.collapsed; projectTreeToggle.setAttribute('aria-expanded', projectState.collapsed ? 'false' : 'true'); projectTreeToggle.querySelector('[aria-hidden]')?.replaceChildren(document.createTextNode(projectState.collapsed ? '▶' : '▼')); renderProjectList(projectState.items); });
if (projectTreeMenuButton) projectTreeMenuButton.addEventListener('click', (event) => { event.stopPropagation(); const panel = document.createElement('div'); panel.append(menuButton('最近更新', () => { projectState.showArchived = false; saveProjectSort('recent'); })); panel.append(menuButton('名称 A–Z', () => { projectState.showArchived = false; saveProjectSort('name'); })); panel.append(menuButton(projectState.showArchived ? '返回当前项目' : '查看归档项目', () => { projectState.showArchived = !projectState.showArchived; renderProjectList(projectState.items); })); openFloatingMenu(projectTreeMenuButton, panel); });
if (conversationListMenuTrigger) conversationListMenuTrigger.addEventListener('click', (event) => { event.stopPropagation(); const panel = document.createElement('div'); panel.append(menuButton(conversationListState.showArchived ? '返回最近会话' : '查看归档会话', () => { conversationListState.showArchived = !conversationListState.showArchived; loadConversationList(); })); openFloatingMenu(conversationListMenuTrigger, panel); });
if (conversationActionForm) conversationActionForm.addEventListener('submit', submitActionDialog);
if (conversationConfirmForm) conversationConfirmForm.addEventListener('submit', submitConfirmDialog);
if (conversationActionProjectSearch) conversationActionProjectSearch.addEventListener('input', () => { if (dialogState.action === 'move-conversation') renderMoveProjectOptions(dialogState.target, conversationActionProjectSearch.value); });
conversationActionDialog?.addEventListener('close', () => { if (dialogState.restoreFocus?.isConnected) dialogState.restoreFocus.focus(); dialogState.restoreFocus = null; });
conversationConfirmDialog?.addEventListener('close', () => { if (dialogState.restoreFocus?.isConnected) dialogState.restoreFocus.focus(); dialogState.restoreFocus = null; });
projectDialog?.addEventListener('close', () => { if (dialogState.restoreFocus?.isConnected) dialogState.restoreFocus.focus(); dialogState.restoreFocus = null; });
projectDialog?.addEventListener('cancel', () => { dialogState.action = null; dialogState.target = null; });
conversationActionDialog?.addEventListener('cancel', () => { dialogState.action = null; dialogState.target = null; });
conversationConfirmDialog?.addEventListener('cancel', () => { dialogState.action = null; dialogState.target = null; });
document.addEventListener('pointerdown', (event) => { if (menuState.panel && !menuState.panel.contains(event.target) && event.target !== menuState.trigger) closeFloatingMenu(); });
document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape') return;
  if (menuState.panel) closeFloatingMenu();
  if (mobileSidebar?.classList.contains('mobile-nav-open')) closeMobileDrawer(true);
});
if (memoryScopeSelect) memoryScopeSelect.addEventListener('change', () => {
  const isProject = memoryScopeSelect.value === 'project';
  if (memoryProjectLabel) memoryProjectLabel.hidden = !isProject;
  loadMemories();
});
if (memoryProjectSelect) memoryProjectSelect.addEventListener('change', loadMemories);
if (memoryStatusSelect) memoryStatusSelect.addEventListener('change', loadMemories);
if (memoryRefreshButton) memoryRefreshButton.addEventListener('click', loadMemories);
if (memoryCreateButton) memoryCreateButton.addEventListener('click', createManualMemory);
if (systemRuleEditButton) systemRuleEditButton.addEventListener('click', () => openSystemRuleEditor());
if (systemRuleToggleButton) systemRuleToggleButton.addEventListener('click', toggleSystemRule);
if (systemRuleClearButton) systemRuleClearButton.addEventListener('click', openSystemRuleClearDialog);
if (systemRuleForm) systemRuleForm.addEventListener('submit', saveSystemRule);
if (systemRuleClearForm) systemRuleClearForm.addEventListener('submit', clearSystemRule);
if (systemRuleInput) systemRuleInput.addEventListener('input', updateSystemRuleCount);
for (const dialogForm of [systemRuleForm, systemRuleClearForm]) dialogForm?.addEventListener('click', (event) => {
  if (event.target?.closest?.('button[value="cancel"]')) { event.preventDefault(); dialogForm.closest('dialog')?.close('cancel'); }
});
if (memoryList) memoryList.addEventListener('click', (event) => {
  const openButton = event.target.closest('[data-open-conversation]');
  if (openButton) { openConversationFromWorkspace(openButton.dataset.openConversation); return; }
  const button = event.target.closest('[data-memory-action]');
  if (!button) return;
  const card = button.closest('.memory-item');
  handleMemoryAction(button.dataset.memoryAction, button.dataset.memoryId, card);
});
if (loadOlderMessagesButton) loadOlderMessagesButton.addEventListener('click', loadOlderConversationMessages);
if (conversationList) conversationList.addEventListener('scroll', () => {
  if (conversationList.scrollTop + conversationList.clientHeight >= conversationList.scrollHeight - 24) loadConversationList({ append: true });
});
messages.addEventListener('scroll', () => {
  if (messages.scrollTop <= 24) loadOlderConversationMessages();
});
window.addEventListener('popstate', () => {
  const match = window.location.pathname.match(/^\/c\/([^/]+)$/);
  if (match) openConversation(decodeURIComponent(match[1]), { replace: true });
  else beginDraft();
});

loadProjects().then(() => {
  const match = window.location.pathname.match(/^\/c\/([^/]+)$/);
  if (match) openConversation(decodeURIComponent(match[1]), { replace: true });
  else loadConversationList();
});

// 输入法（IME）组合期间按 Enter 是"选词"，不是提交：拼音/注音/日语输入必须等 compositionend。
// keyCode 229 是部分浏览器在 IME 处理中给出的键值，一并拦截。
function onEnterKey(target, handler) {
  let composing = false;
  target.addEventListener('compositionstart', () => { composing = true; });
  target.addEventListener('compositionend', () => { composing = false; });
  target.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter') return;
    if (composing || event.isComposing || event.keyCode === 229) return;
    handler(event);
  });
}

onEnterKey(input, (event) => {
  if (event.shiftKey) return;
  event.preventDefault();
  form.requestSubmit();
});

// ===== 论文检索视图（spec-015 / Task07）：只消费服务端 opaque ID =====
const paperNav = document.querySelector('[data-view="papers"]');
const paperView = document.querySelector('#papers-view');
const paperForm = document.querySelector('#paper-search-form');
const paperQuery = document.querySelector('#paper-query');
const paperConferenceList = document.querySelector('#paper-conference-list');
const paperConferenceEmpty = document.querySelector('#paper-conference-empty');
const paperYearFrom = document.querySelector('#paper-year-from');
const paperYearTo = document.querySelector('#paper-year-to');
const paperSearchButton = document.querySelector('#paper-search-button');
const paperSearchStatus = document.querySelector('#paper-search-status');
const paperSearchError = document.querySelector('#paper-search-error');
const paperProgressPanel = document.querySelector('#paper-search-progress');
const paperProgressStatus = document.querySelector('#paper-progress-status');
const paperResultCount = document.querySelector('#paper-result-count');
const paperResults = document.querySelector('#paper-results');
const paperResultsEmpty = document.querySelector('#paper-results-empty');
const paperPagination = document.querySelector('#paper-pagination');
const paperPrevPage = document.querySelector('#paper-prev-page');
const paperNextPage = document.querySelector('#paper-next-page');
const paperPageStatus = document.querySelector('#paper-page-status');
const paperResultsToolbar = document.querySelector('#paper-results-toolbar');
const paperSelectAll = document.querySelector('#paper-select-all');
const paperSelectedCount = document.querySelector('#paper-selected-count');
const paperImportSelected = document.querySelector('#paper-import-selected');
const paperImportPanel = document.querySelector('#paper-import-panel');
const paperImportStatus = document.querySelector('#paper-import-status');
const paperImportSummary = document.querySelector('#paper-import-summary');
const paperImportItems = document.querySelector('#paper-import-items');
const paperLoginQueue = document.querySelector('#paper-login-queue');
const paperLoginItems = document.querySelector('#paper-login-items');
const paperConferenceSearch = document.querySelector('#paper-conference-search');
const paperConferenceSearchButton = document.querySelector('#paper-conference-search-button');
const paperConferenceSearchResults = document.querySelector('#paper-conference-search-results');
const paperConferenceStatus = document.querySelector('#paper-conference-status');
const paperManageButton = document.querySelector('#paper-conference-manage-button');
const paperConferenceDialog = document.querySelector('#paper-conference-dialog');
const paperManagedConferences = document.querySelector('#paper-managed-conferences');
const paperConferenceDialogStatus = document.querySelector('#paper-conference-dialog-status');

function readPaperFeatureFlag() {
  const configured = globalThis.PAPER_DISCOVERY_ENABLED
    ?? globalThis.__PAPER_DISCOVERY_ENABLED__
    ?? document.documentElement?.dataset.paperDiscoveryEnabled;
  if (configured === undefined || configured === null || configured === '') return true;
  if (typeof configured === 'boolean') return configured;
  return !['0', 'false', 'no', 'off', 'disabled'].includes(String(configured).trim().toLowerCase());
}

const paperState = {
  enabled: readPaperFeatureFlag(),
  conferences: [],
  candidates: [],
  candidateSearchIds: new Map(),
  searchIds: [],
  searchId: null,
  searchPage: 1,
  searchTotalPages: 0,
  searchHasNext: false,
  searchSerial: 0,
  searchController: null,
  conferencesLoaded: false,
  batches: new Map(),
  candidateById: new Map(),
  inFlightImports: new Set(),
  batchPollTimer: null,
  batchPollSerial: 0,
  pendingKbPaperId: null,
  importPhase: 'idle',
  failedGroups: [],
  skippedImports: 0,
  directSuccess: 0,
  directImports: [],
  lastImportError: null,
  currentRoundBatchIds: new Set(),
  pendingGroups: 0,
  submitInflight: 0,
  retryingBatchIds: new Set(),
};

const SLOW_IMPORT_MS = 3 * 60 * 1000; // 软提示阈值：批次非终态且 updated_at 超 3 分钟未变化时提示"仍在导入，可离开此页"。

const PAPER_STATUS_TEXT = {
  queued: '排队中', downloading: '下载中', waiting_login: '等待登录', validating: '校验中',
  indexing: '建索引中', completed: '已完成', failed: '失败', cancelled: '已取消',
  partial_success: '部分完成', running: '处理中', completed_count: '已完成',
};
const PAPER_SOURCE_STATUS_TEXT = {
  queued: '未开始', checking_cache: '正在检查本地目录', cached: '已使用缓存',
  fetching: '正在从该来源获取', merging: '正在整理元数据', completed: '检索完成',
  failed: '该来源暂时不可用', partial: '部分完成',
};
const PAPER_SOURCE_MESSAGE_TEXT = {
  SOURCE_QUEUED: '未开始', CHECKING_CACHE: '正在检查本地目录', CACHE_HIT: '已使用缓存',
  FETCHING_SOURCE: '正在从该来源获取', MERGING_METADATA: '正在整理元数据',
  SOURCE_COMPLETED: '检索完成', SOURCE_PARTIAL: '部分完成', SOURCE_FAILED: '该来源暂时不可用',
};
const PAPER_SOURCE_LABELS = { usenix: 'USENIX Security 官网', dblp: 'DBLP 辅助书目' };
const PAPER_PUBLICATION_STAGE_TEXT = {
  published: '已发表', accepted: '已接收', prepublication: '预发表',
};
const PAPER_SOURCE_ERROR_TEXT = {
  USENIX_UNAVAILABLE: '该来源暂时不可用', DBLP_UNAVAILABLE: '该来源暂时不可用',
  SOURCE_UNAVAILABLE: '该来源暂时不可用', SOURCE_FETCH_FAILED: '该来源暂时不可用',
};
const PAPER_ERROR_TEXT = {
  PAPER_DISCOVERY_DISABLED: '论文检索功能当前已关闭', PAPER_DISCOVERY_UNAVAILABLE: '检索服务暂时不可用',
  PAPER_DISCOVERY_STORE_UNAVAILABLE: '检索配置暂时不可用', SEARCH_EXPIRED: '搜索会话已过期，请重新检索',
  SEARCH_NOT_FOUND: '搜索会话不存在，请重新检索', CANDIDATE_NOT_FOUND: '候选论文不存在，请重新检索',
  INVALID_QUERY: '研究方向不能为空且最多 500 个字符', INVALID_YEARS: '年份需按从早到晚排序（例如 2021–2025），且在受支持范围内',
  UNSUPPORTED_CONFERENCE: '异步目录检索当前仅支持 USENIX Security', CONFERENCE_NOT_FOUND: '会议配置不存在',
  SEARCH_NO_RESULTS: '搜索没有可读结果', INVALID_PAGE: '页码必须从第 1 页开始',
  CATALOG_NOT_READY: '论文目录尚未准备好，请稍后重试', INVALID_ACCEPTED_YEAR: '年份必须为 1900 到当前年份之间的整数',
  INVALID_CONFERENCE: '请选择已启用的会议', CONFERENCE_DISABLED: '所选会议已停用',
  CONFERENCE_NOT_CONFIGURED: '会议配置不存在', BATCH_LIMIT_EXCEEDED: '单批最多导入 20 篇',
  BROWSER_SESSION_REQUIRED: '请先完成受控登录后再续传', BROWSER_UNAVAILABLE: '浏览器当前不可用',
  BROWSER_ORIGIN_NOT_ALLOWED: '该论文不支持受控登录', IMPORT_BATCH_UNAVAILABLE: '导入服务暂时不可用',
  IMPORT_BATCH_ERROR: '导入批次失败', PAPER_ALREADY_EXISTS: '论文已在知识库中', LOGIN_REQUIRED: '需要登录后才能下载',
  SEARCH_NOT_READY: '结果正在整理，请稍后重试',
  KB_STORAGE_LOCKED: '知识库存储被另一个实例占用，请关闭其他服务实例后重试',
  DUPLICATE_IMPORT: '该论文已在导入批次中，请在原批次重试',
};

class PaperApiError extends Error {
  constructor(code, retryable = false, details = null) {
    super(PAPER_ERROR_TEXT[code] || '论文服务暂时不可用');
    this.code = code || 'PAPER_API_ERROR';
    this.retryable = Boolean(retryable);
    this.details = details;
  }
}

async function paperJson(response) {
  let data = {};
  try { data = await response.json(); } catch (_) {}
  if (!response.ok) {
    const detail = data && typeof data.detail === 'object' ? data.detail : data;
    throw new PaperApiError(detail?.code || data?.code, detail?.retryable || data?.retryable, detail?.details || data?.details);
  }
  return data;
}

function setPaperEnabled(enabled) {
  paperState.enabled = Boolean(enabled);
  if (paperNav) paperNav.hidden = !paperState.enabled;
  if (!paperState.enabled) {
    paperState.searchSerial += 1;
    paperState.batchPollSerial += 1;
    paperState.searchController?.abort();
    paperState.searchController = null;
    paperState.searchId = null;
    if (paperProgressPanel) paperProgressPanel.hidden = true;
    if (paperPagination) paperPagination.hidden = true;
    if (paperSearchButton) paperSearchButton.disabled = false;
    if (paperResults) paperResults.setAttribute('aria-busy', 'false');
    if (paperState.batchPollTimer) {
      window.clearInterval(paperState.batchPollTimer);
      paperState.batchPollTimer = null;
    }
    paperState.inFlightImports.clear();
    if (paperView) paperView.hidden = true;
  }
}

setPaperEnabled(paperState.enabled);

function paperYearList() {
  const from = Number(paperYearFrom?.value);
  const to = Number(paperYearTo?.value);
  if (!Number.isInteger(from) || !Number.isInteger(to) || from > to || to > new Date().getFullYear()) return null;
  const years = [];
  for (let year = from; year <= to; year += 1) years.push(year);
  return years.length > 10 ? null : years;
}

function renderPaperConferences() {
  if (!paperConferenceList) return;
  const selected = new Set([...paperConferenceList.querySelectorAll('input:checked')].map((input) => input.value));
  paperConferenceList.replaceChildren();
  const enabled = paperState.conferences.filter((conference) => conference.enabled);
  if (paperConferenceEmpty) paperConferenceEmpty.hidden = enabled.length > 0;
  enabled.forEach((conference) => {
    const label = document.createElement('label');
    label.className = 'paper-conference-option';
    const input = document.createElement('input');
    input.type = 'checkbox'; input.name = 'conference_id'; input.value = conference.conference_id;
    input.checked = selected.size ? selected.has(conference.conference_id) : conference.conference_id === 'usenix-security';
    input.addEventListener('change', syncPaperConferenceSearchSelection);
    const text = document.createElement('span');
    const onlyUsenix = conference.conference_id === 'usenix-security';
    const note = onlyUsenix ? '' : '（暂仅支持 USENIX Security 异步检索）';
    text.textContent = `${conference.short_name || conference.name || '未命名会议'}${note}`;
    label.append(input, text); paperConferenceList.appendChild(label);
  });
  updatePaperSelection();
}

function updatePaperSelection() {
  const checked = paperResults ? [...paperResults.querySelectorAll('input[type="checkbox"]:checked')] : [];
  if (paperSelectedCount) paperSelectedCount.textContent = `已选 ${checked.length} 篇`;
  if (paperImportSelected) paperImportSelected.disabled = checked.length === 0;
  if (paperSelectAll && paperResults) {
    const selectable = [...paperResults.querySelectorAll('input[type="checkbox"]:not(:disabled)')];
    paperSelectAll.checked = selectable.length > 0 && selectable.every((input) => input.checked);
    paperSelectAll.indeterminate = selectable.some((input) => input.checked) && !paperSelectAll.checked;
  }
}

function paperCandidateScore(candidate) {
  const score = candidate.final_score ?? candidate.rerank_score ?? candidate.retrieval_score;
  return Number.isFinite(Number(score)) ? Number(score).toFixed(3) : '—';
}

function paperText(value, fallback = '—') {
  return value === null || value === undefined || value === '' ? fallback : String(value);
}

function paperIdempotencyKey(searchId, candidateIds) {
  const source = `${searchId}:${candidateIds.join(',')}`;
  let hash = 2166136261;
  for (let index = 0; index < source.length; index += 1) {
    hash ^= source.charCodeAt(index); hash = Math.imul(hash, 16777619);
  }
  return `paper-${(hash >>> 0).toString(16)}`;
}

function paperCandidateScoreValue(candidate) {
  return Number(candidate.final_score ?? candidate.rerank_score ?? candidate.retrieval_score);
}

function paperCandidateNumericValue(candidate, field) {
  const raw = candidate?.[field];
  if (raw === null || raw === undefined || (typeof raw === 'string' && !raw.trim())) return NaN;
  const value = Number(raw);
  return Number.isFinite(value) ? value : NaN;
}

function paperCandidateRankValue(candidate) {
  return paperCandidateNumericValue(candidate, 'rank');
}

function paperCandidateInitialRankValue(candidate) {
  return paperCandidateNumericValue(candidate, 'initial_rank');
}

function paperCandidateYearValue(candidate) {
  return paperCandidateNumericValue(candidate, 'year');
}

function paperCandidateNormalize(value) {
  return String(value ?? '')
    .normalize('NFKC')
    .toLocaleLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim();
}

function paperCandidateDoi(candidate) {
  return String(candidate?.doi ?? '')
    .trim()
    .replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, '')
    .replace(/^doi:\s*/i, '')
    .replace(/[.,;:)>\]}]+$/g, '')
    .toLocaleLowerCase();
}

function paperCandidateDblpKey(candidate) {
  return String(candidate?.dblp_key ?? candidate?.dblp ?? '')
    .normalize('NFKC')
    .trim()
    .toLocaleLowerCase();
}

function paperCandidateIdentityKeys(candidate) {
  const keys = [];
  const doi = paperCandidateDoi(candidate);
  if (doi) keys.push(`doi:${doi}`);
  const dblpKey = paperCandidateDblpKey(candidate);
  if (dblpKey) keys.push(`dblp:${dblpKey}`);
  const metadata = [
    paperCandidateNormalize(candidate.normalized_title || candidate.title),
    paperCandidateNormalize(candidate.year),
    paperCandidateNormalize(candidate.conference_id || candidate.conference_name),
  ];
  if (metadata.every(Boolean)) keys.push(`metadata:${metadata.join('|')}`);
  return keys;
}

function paperCandidateIdentityMatches(left, right) {
  const leftDoi = paperCandidateDoi(left);
  const rightDoi = paperCandidateDoi(right);
  const leftDblpKey = paperCandidateDblpKey(left);
  const rightDblpKey = paperCandidateDblpKey(right);
  if (leftDoi || rightDoi) {
    if (leftDoi && rightDoi) return leftDoi === rightDoi;
    return Boolean(leftDblpKey && rightDblpKey && leftDblpKey === rightDblpKey);
  }
  if (leftDblpKey || rightDblpKey) {
    return Boolean(leftDblpKey && rightDblpKey && leftDblpKey === rightDblpKey);
  }
  const leftKeys = paperCandidateIdentityKeys(left);
  const rightKeys = paperCandidateIdentityKeys(right);
  return Boolean(leftKeys[0] && rightKeys[0] && leftKeys[0] === rightKeys[0]);
}

function comparePaperCandidateNumbers(left, right, field, direction) {
  const leftValue = paperCandidateNumericValue(left.candidate, field);
  const rightValue = paperCandidateNumericValue(right.candidate, field);
  const leftHasValue = Number.isFinite(leftValue);
  const rightHasValue = Number.isFinite(rightValue);
  if (leftHasValue && rightHasValue && leftValue !== rightValue) {
    return direction * (leftValue - rightValue);
  }
  if (leftHasValue !== rightHasValue) return leftHasValue ? -1 : 1;
  return 0;
}

function comparePaperCandidateText(left, right, leftValue, rightValue) {
  const leftText = leftValue || '';
  const rightText = rightValue || '';
  if (leftText === rightText) return 0;
  if (!leftText || !rightText) return leftText ? -1 : 1;
  return leftText < rightText ? -1 : 1;
}

// Static contract: after score fields, same-score candidates use exactly this
// tuple. DOI/DBLP keys are identity-only and must not affect presentation order.
const PAPER_CANDIDATE_TIE_BREAK_ORDER = Object.freeze([
  'initial_rank asc',
  'year desc',
  'normalized_title asc',
  'candidate_id asc',
]);

function comparePaperCandidateRecords(left, right) {
  for (const field of ['final_score', 'rerank_score', 'retrieval_score']) {
    const scoreResult = comparePaperCandidateNumbers(left, right, field, -1);
    if (scoreResult) return scoreResult;
  }
  const initialRankResult = comparePaperCandidateNumbers(left, right, 'initial_rank', 1);
  if (initialRankResult) return initialRankResult;
  const leftYear = paperCandidateYearValue(left.candidate);
  const rightYear = paperCandidateYearValue(right.candidate);
  const leftHasYear = Number.isFinite(leftYear);
  const rightHasYear = Number.isFinite(rightYear);
  if (leftHasYear && rightHasYear && leftYear !== rightYear) return rightYear - leftYear;
  if (leftHasYear !== rightHasYear) return leftHasYear ? -1 : 1;
  const titleResult = comparePaperCandidateText(
    left,
    right,
    paperCandidateNormalize(left.candidate?.normalized_title || left.candidate?.title),
    paperCandidateNormalize(right.candidate?.normalized_title || right.candidate?.title),
  );
  if (titleResult) return titleResult;
  const candidateIdResult = comparePaperCandidateText(
    left,
    right,
    String(left.candidate?.candidate_id ?? '').normalize('NFKC').trim(),
    String(right.candidate?.candidate_id ?? '').normalize('NFKC').trim(),
  );
  if (candidateIdResult) return candidateIdResult;
  if (left.responseIndex !== right.responseIndex) return left.responseIndex - right.responseIndex;
  return left.candidateIndex - right.candidateIndex;
}

function paperUnitCount(value) {
  if (Array.isArray(value)) return value.length;
  const count = Number(value);
  return Number.isFinite(count) && count >= 0 ? count : 0;
}

function paperSourceProgressByKind(progress) {
  const byKind = new Map();
  (Array.isArray(progress) ? progress : []).forEach((item) => {
    if (item && (item.source_kind === 'usenix' || item.source_kind === 'dblp')) byKind.set(item.source_kind, item);
  });
  return byKind;
}

function renderPaperSourceProgress(payload = {}) {
  const progress = paperSourceProgressByKind(payload.source_progress || payload.sources);
  if (paperProgressPanel) paperProgressPanel.hidden = false;
  ['usenix', 'dblp'].forEach((sourceKind) => {
    const card = document.querySelector(`#paper-source-${sourceKind}`);
    const statusNode = document.querySelector(`#paper-source-${sourceKind}-status`);
    const countsNode = document.querySelector(`#paper-source-${sourceKind}-counts`);
    const errorNode = document.querySelector(`#paper-source-${sourceKind}-error`);
    const source = progress.get(sourceKind) || { status: 'queued', cached_units: [], fetching_units: [], completed_units: [], paper_count: 0 };
    const status = PAPER_SOURCE_STATUS_TEXT[source.status] ? source.status : 'queued';
    const message = PAPER_SOURCE_STATUS_TEXT[source.status]
      || PAPER_SOURCE_MESSAGE_TEXT[source.message_code] || '正在整理来源';
    const errorText = source.error_code ? (PAPER_SOURCE_ERROR_TEXT[source.error_code] || (status === 'failed' ? '该来源暂时不可用' : '')) : '';
    if (card) card.className = `paper-source-card status-${status}`;
    if (statusNode) statusNode.textContent = message;
    if (countsNode) countsNode.textContent = `缓存 ${paperUnitCount(source.cached_units)} · 获取 ${paperUnitCount(source.fetching_units)} · 完成 ${paperUnitCount(source.completed_units)} · 论文 ${paperUnitCount(source.paper_count)}`;
    if (errorNode) { errorNode.textContent = errorText; errorNode.hidden = !errorText; }
  });
  const jobStatus = payload.status;
  if (paperProgressStatus) {
    paperProgressStatus.textContent = jobStatus === 'partial'
      ? '部分来源未完成，以下结果来自可用目录'
      : jobStatus === 'completed' ? '检索完成' : jobStatus === 'failed' ? '检索失败' : '正在检索…';
  }
}

function normalizePaperResult(item, searchId) {
  const candidate = item && typeof item === 'object' ? item : {};
  const candidateId = paperText(candidate.catalog_paper_id || candidate.candidate_id, '');
  return {
    ...candidate,
    candidate_id: candidateId,
    search_id: searchId,
    authors: Array.isArray(candidate.authors) ? candidate.authors.map((author) => String(author)) : [],
    keywords: Array.isArray(candidate.keywords) ? candidate.keywords.map((keyword) => String(keyword)) : [],
    source_kinds: Array.isArray(candidate.source_kinds) ? candidate.source_kinds.map((kind) => String(kind)) : [],
  };
}

function renderPaperPagination(pageInfo = {}) {
  const page = Math.max(1, Number(pageInfo.page) || 1);
  const totalPages = Math.max(page, Number(pageInfo.total_pages) || 1);
  const hasNext = typeof pageInfo.has_next === 'boolean' ? pageInfo.has_next : page < totalPages;
  paperState.searchPage = page; paperState.searchTotalPages = totalPages; paperState.searchHasNext = hasNext;
  if (paperPagination) paperPagination.hidden = !paperState.candidates.length;
  if (paperPageStatus) paperPageStatus.textContent = `第 ${page} / ${totalPages} 页`;
  if (paperPrevPage) paperPrevPage.disabled = page <= 1;
  if (paperNextPage) paperNextPage.disabled = !hasNext;
}

function renderPaperResults(candidates, pageInfo = {}) {
  if (!paperResults) return;
  paperResults.replaceChildren();
  paperState.candidates = candidates;
  paperResultsEmpty.hidden = candidates.length > 0;
  paperResultsEmpty.textContent = candidates.length ? '' : '没有找到符合条件的论文。';
  if (paperResultCount) paperResultCount.textContent = candidates.length ? `${Number(pageInfo.total) || candidates.length} 篇` : '';
  if (paperResultsToolbar) paperResultsToolbar.hidden = candidates.length === 0;
  candidates.forEach((candidate) => {
    const item = document.createElement('li'); item.className = 'paper-result-item';
    const head = document.createElement('div'); head.className = 'paper-result-head';
    const select = document.createElement('input'); select.type = 'checkbox'; select.className = 'paper-result-select';
    select.dataset.candidateId = paperText(candidate.candidate_id, '');
    select.disabled = Boolean(candidate.existing_paper_id || !candidate.candidate_id);
    select.setAttribute('aria-label', `选择论文：${paperText(candidate.title, '未命名论文')}`);
    select.addEventListener('change', updatePaperSelection);
    const title = document.createElement('h3'); title.className = 'paper-result-title'; title.textContent = paperText(candidate.title, '未命名论文');
    head.append(select, title); item.appendChild(head);
    const meta = document.createElement('p'); meta.className = 'paper-result-meta';
    meta.textContent = [candidate.authors.join(', '), candidate.year, candidate.conference_name, `相关度 ${paperCandidateScore(candidate)}`].filter(Boolean).join(' · ');
    item.appendChild(meta);
    const abstract = document.createElement('p'); abstract.className = 'paper-result-abstract';
    abstract.textContent = candidate.abstract ? String(candidate.abstract) : '摘要暂不可用'; item.appendChild(abstract);
    if (candidate.keywords.length) {
      const keywords = document.createElement('p'); keywords.className = 'paper-result-meta paper-result-keywords';
      keywords.textContent = `关键词：${candidate.keywords.join('、')}`; item.appendChild(keywords);
    }
    const status = document.createElement('span'); status.className = 'paper-result-status';
    const sourceNames = candidate.source_kinds.map((kind) => PAPER_SOURCE_LABELS[kind] || '受控来源').join('、') || '受控来源';
    const stage = PAPER_PUBLICATION_STAGE_TEXT[candidate.publication_stage] || '出版阶段待确认';
    status.textContent = `出版阶段：${stage} · 来源：${sourceNames}`; item.appendChild(status);
    const action = document.createElement('button'); action.type = 'button'; action.className = 'secondary-button paper-import-one';
    action.dataset.candidateId = paperText(candidate.candidate_id, '');
    action.disabled = Boolean(candidate.existing_paper_id || !candidate.candidate_id); action.textContent = candidate.existing_paper_id ? '已在知识库' : '添加到知识库';
    action.addEventListener('click', () => importPaperCandidates([candidate])); item.appendChild(action);
    paperResults.appendChild(item);
    if (candidate.candidate_id) {
      paperState.candidateSearchIds.set(candidate.candidate_id, candidate.search_id);
      paperState.candidateById.set(candidate.candidate_id, candidate);
    }
  });
  renderPaperPagination(pageInfo);
  updatePaperSelection();
}

async function loadPaperResultsPage(searchId, page, serial, controller) {
  const response = await fetch(`/api/papers/searches/${encodeURIComponent(searchId)}/results?page=${encodeURIComponent(page)}`, { signal: controller.signal });
  const data = await paperJson(response);
  if (serial !== paperState.searchSerial) return null;
  const rawItems = Array.isArray(data.items) ? data.items : (Array.isArray(data.results) ? data.results : []);
  const candidates = rawItems.map((item) => normalizePaperResult(item, searchId));
  renderPaperResults(candidates, data);
  return data;
}

function waitForPaperPoll(delay, signal) {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(resolve, delay);
    signal.addEventListener('abort', () => { window.clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')); }, { once: true });
  });
}

async function pollPaperSearch(searchId, serial, controller) {
  while (serial === paperState.searchSerial && !controller.signal.aborted) {
    const response = await fetch(`/api/papers/searches/${encodeURIComponent(searchId)}`, { signal: controller.signal });
    const data = await paperJson(response);
    if (serial !== paperState.searchSerial) return;
    renderPaperSourceProgress(data);
    const status = data.status || 'running';
    if (paperSearchStatus) setPaperStatus(paperSearchStatus, status === 'partial'
      ? '部分来源未完成，以下结果来自可用目录' : status === 'completed' ? '检索完成' : status === 'failed' ? '检索失败' : '正在检索…',
      status === 'partial' ? 'partial' : status === 'completed' ? 'completed' : status === 'failed' ? 'failed' : 'running');
    if (['completed', 'partial', 'failed'].includes(status)) {
      try {
        const resultData = await loadPaperResultsPage(searchId, 1, serial, controller);
        const visibleItems = resultData?.items || resultData?.results || [];
        if (status === 'failed' && !visibleItems.length) showPaperError('PAPER_DISCOVERY_UNAVAILABLE');
        else if (status === 'failed' && visibleItems.length) {
          if (paperSearchStatus) setPaperStatus(paperSearchStatus, '部分来源未完成，以下结果来自可用目录', 'partial');
          if (paperProgressStatus) setPaperStatus(paperProgressStatus, '部分来源未完成，以下结果来自可用目录', 'partial');
        }
      } catch (error) {
        if (status === 'partial' && error.name !== 'AbortError') showPaperError('SEARCH_NOT_READY');
        else if (status === 'failed' && error.name !== 'AbortError') showPaperError(error.code || 'PAPER_DISCOVERY_UNAVAILABLE');
        else throw error;
      }
      return;
    }
    await waitForPaperPoll(1200, controller.signal);
  }
}

async function searchPapers(event) {
  event?.preventDefault();
  if (!paperState.enabled) return;
  const query = (paperQuery?.value || '').trim();
  const conferenceIds = paperConferenceList ? [...paperConferenceList.querySelectorAll('input:checked')].map((input) => input.value) : [];
  const years = paperYearList();
  if (!query) { showPaperError('INVALID_QUERY'); return; }
  if (!conferenceIds.length) { showPaperError('INVALID_CONFERENCE'); return; }
  if (!years) { showPaperError('INVALID_YEARS'); return; }
  paperState.searchController?.abort();
  const generation = ++paperState.searchSerial;
  const serial = generation;
  const controller = new AbortController(); paperState.searchController = controller;
  paperState.searchId = null; paperState.searchIds = []; paperState.searchPage = 1; paperState.searchTotalPages = 0; paperState.searchHasNext = false;
  paperState.candidateSearchIds.clear(); paperState.candidateById.clear(); paperState.candidates = [];
  // Keep the submit control available so a new search can supersede an
  // in-flight generation; the controller/generation guard cancels the old one.
  if (paperSearchButton) paperSearchButton.disabled = false;
  if (paperResults) paperResults.setAttribute('aria-busy', 'true');
  if (paperSearchError) paperSearchError.hidden = true;
  if (paperSearchStatus) setPaperStatus(paperSearchStatus, '正在检索…', 'running');
  renderPaperSourceProgress({ status: 'queued' });
  if (paperResults) paperResults.replaceChildren();
  if (paperResultsEmpty) { paperResultsEmpty.hidden = false; paperResultsEmpty.textContent = '正在准备检索…'; }
  if (paperResultsToolbar) paperResultsToolbar.hidden = true;
  if (paperPagination) paperPagination.hidden = true;
  try {
    const response = await fetch('/api/papers/searches', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
      body: JSON.stringify({ query, conference_ids: conferenceIds, years }),
    });
    const data = await paperJson(response);
    if (serial !== paperState.searchSerial) return;
    const searchId = paperText(data.search_id, '');
    if (!searchId) throw new PaperApiError('PAPER_DISCOVERY_UNAVAILABLE');
    paperState.searchId = searchId; paperState.searchIds = [searchId];
    renderPaperSourceProgress(data);
    await pollPaperSearch(searchId, serial, controller);
  } catch (error) {
    if (error.name === 'AbortError' || serial !== paperState.searchSerial) return;
    showPaperError(error.code, error.details);
    if (paperSearchStatus) setPaperStatus(paperSearchStatus, '检索失败', 'failed');
  } finally {
    if (serial === paperState.searchSerial) {
      if (paperSearchButton) paperSearchButton.disabled = false;
      if (paperResults) paperResults.setAttribute('aria-busy', 'false');
    }
  }
}

function cancelPaperSearchPolling() {
  paperState.searchSerial += 1;
  paperState.searchController?.abort();
  paperState.searchController = null;
  if (paperSearchButton) paperSearchButton.disabled = false;
}

function setPaperStatus(element, text, kind) {
  if (!element) return;
  element.textContent = text;
  element.classList.remove('is-running', 'is-completed', 'is-partial', 'is-failed');
  if (kind) element.classList.add(`is-${kind}`);
}

function showPaperError(code, details = null) {
  if (!paperSearchError) return;
  let text = PAPER_ERROR_TEXT[code] || '论文服务暂时不可用，请稍后重试';
  if (code === 'INVALID_YEARS' && details && Number.isInteger(details.min_year) && Number.isInteger(details.max_year)) {
    text = `年份需按从早到晚排序，且必须在受支持范围内（仅支持 ${details.min_year}–${details.max_year}）`;
  }
  paperSearchError.textContent = text;
  paperSearchError.hidden = false;
}

const PAPER_IMPORT_PHASES = ['idle', 'submitting', 'running', 'partial_success', 'completed', 'failed'];

// 仅作状态留痕（importPhase 字段不参与任何判定/渲染）；相位由 renderImportSummary 基于事实
//（submitInflight、批次态等）重算后在此写入。外部不得再"先写相位、再被事实重算覆盖"。
function setImportPhase(phase) {
  if (!PAPER_IMPORT_PHASES.includes(phase)) return;
  paperState.importPhase = phase;
}

function renderImportSummary() {
  if (!paperImportStatus) return;
  const roundBatchIds = paperState.currentRoundBatchIds || new Set();
  const batches = [...paperState.batches.entries()]
    .filter(([id]) => roundBatchIds.has(id))
    .map(([, batch]) => batch);
  let completedItems = 0;
  let failedItems = 0;
  let runningBatches = 0;
  for (const batch of batches) {
    const items = batch.items || [];
    if (!paperBatchTerminal(batch)) runningBatches += 1;
    for (const item of items) {
      const st = item.status || item.state;
      if (st === 'completed') completedItems += 1;
      else if (st === 'failed') failedItems += 1;
    }
    if (paperBatchTerminal(batch) && (batch.status || batch.state) === 'failed' && items.length === 0) {
      failedItems += Number(batch.total_count) || 1;
    }
  }
  const submitFailed = paperState.failedGroups.length;
  const skipped = paperState.skippedImports;
  const totalSuccess = completedItems + (paperState.directSuccess || 0);
  const totalFailed = failedItems + submitFailed;
  const totalBatches = batches.length;

  let phase;
  if (paperState.submitInflight > 0) {
    phase = 'submitting';
  } else if (runningBatches > 0) {
    phase = 'running';
  } else if (totalSuccess > 0 && totalFailed > 0) {
    phase = 'partial_success';
  } else if (totalSuccess > 0) {
    phase = 'completed';
  } else if (totalFailed > 0 || skipped > 0) {
    phase = 'failed';
  } else {
    phase = 'idle';
  }
  setImportPhase(phase);

  if (paperImportSummary) {
    paperImportSummary.textContent = `${totalBatches} 个批次 · ${totalSuccess} 成功 / ${totalFailed} 失败`;
  }

  let message;
  let kind;
  if (paperState.retryingBatchIds.size > 0) {
    message = `正在重试 ${paperState.retryingBatchIds.size} 项…`;
    kind = 'running';
  } else if (phase === 'submitting') {
    message = `正在提交 ${paperState.pendingGroups} 个导入批次…`;
    kind = 'running';
  } else if (phase === 'running') {
    message = `正在导入：${completedItems} 篇完成${failedItems ? `，${failedItems} 篇失败` : ''}${submitFailed ? `，${submitFailed} 个分组提交失败` : ''}`;
    kind = 'running';
  } else if (phase === 'completed') {
    message = `导入完成：${totalSuccess} 篇成功` + (skipped ? `；${skipped} 篇未能确定所属检索` : '');
    kind = 'completed';
  } else if (phase === 'partial_success') {
    const reasons = [...new Set(paperState.failedGroups.map((g) => PAPER_ERROR_TEXT[g.code] || '导入失败'))];
    message = `导入部分完成：${totalSuccess} 篇成功，${totalFailed} 篇失败`;
    if (reasons.length) message += `（${reasons.join('；')}）`;
    kind = 'partial';
  } else {
    kind = 'failed';
    if (submitFailed) {
      const reasons = [...new Set(paperState.failedGroups.map((g) => PAPER_ERROR_TEXT[g.code] || '导入失败'))];
      message = `导入失败：${reasons.join('；')}`;
    } else if (skipped) {
      message = '未能确定该论文所属检索，请重新检索后再导入';
    } else if (totalFailed) {
      message = `导入失败：${totalFailed} 篇`;
    } else {
      message = '导入未完成';
    }
    if (paperState.lastImportError) {
      const t = PAPER_ERROR_TEXT[paperState.lastImportError];
      if (t) message += `（${t}）`;
    }
  }
  let slow = false;
  for (const batch of batches) {
    if (paperBatchTerminal(batch)) continue;
    const updated = batch.updated_at ? Date.parse(batch.updated_at) : NaN;
    if (!Number.isNaN(updated) && Date.now() - updated > SLOW_IMPORT_MS) { slow = true; break; }
  }
  if (slow) message += '（仍在导入，可离开此页）';
  setPaperStatus(paperImportStatus, message, kind);
}

async function changePaperPage(page) {
  if (!paperState.searchId || !paperState.searchController || page < 1 || page > paperState.searchTotalPages) return;
  const serial = paperState.searchSerial;
  if (paperPrevPage) paperPrevPage.disabled = true;
  if (paperNextPage) paperNextPage.disabled = true;
  if (paperResults) paperResults.setAttribute('aria-busy', 'true');
  try {
    await loadPaperResultsPage(paperState.searchId, page, serial, paperState.searchController);
  } catch (error) {
    if (error.name !== 'AbortError' && serial === paperState.searchSerial) showPaperError(error.code || 'SEARCH_NOT_READY');
  } finally {
    if (serial === paperState.searchSerial) {
      if (paperResults) paperResults.setAttribute('aria-busy', 'false');
      renderPaperPagination({ page: paperState.searchPage, total_pages: paperState.searchTotalPages, has_next: paperState.searchHasNext });
    }
  }
}

async function importPaperCandidates(candidates) {
  if (!paperState.enabled) return;
  const groups = new Map();
  let skipped = 0;
  candidates.filter((candidate) => candidate && !candidate.existing_paper_id).forEach((candidate) => {
    const searchId = paperState.candidateSearchIds.get(candidate.candidate_id) || candidate.search_id;
    if (!searchId) { skipped += 1; return; }
    if (!groups.has(searchId)) groups.set(searchId, []);
    groups.get(searchId).push(candidate.candidate_id);
  });
  paperState.skippedImports = skipped;
  paperState.pendingGroups = groups.size;
  paperState.failedGroups = [];
  paperState.lastImportError = null;
  paperState.directSuccess = 0;
  paperState.directImports = [];
  paperState.currentRoundBatchIds = new Set();
  if (!groups.size) {
    if (paperImportPanel) paperImportPanel.hidden = false;
    renderImportSummary();
    return;
  }
  if (paperImportPanel) paperImportPanel.hidden = false;
  const created = [];
  for (const [search_id, candidate_ids] of groups) {
    const importKey = `${search_id}:${candidate_ids.join('|')}`;
    if (paperState.inFlightImports.has(importKey)) continue;
    paperState.inFlightImports.add(importKey);
    paperState.submitInflight += 1;
    renderImportSummary();
    try {
      const response = await fetch('/api/papers/imports', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(groups.size === 1 && candidate_ids.length === 1
          ? { search_id, candidate_id: candidate_ids[0] }
          : { search_id, candidate_ids, idempotency_key: paperIdempotencyKey(search_id, candidate_ids) }),
      });
      const data = await paperJson(response);
      if (data.batch_id) {
        paperState.batches.set(data.batch_id, data); created.push(data.batch_id); paperState.currentRoundBatchIds.add(data.batch_id); renderPaperBatch(data);
      } else {
        paperState.directSuccess += 1;
        if (data.paper_id || data.stored_name) {
          paperState.directImports.push({
            candidate_id: candidate_ids[0],
            paper_id: data.paper_id || null,
            stored_name: data.stored_name || '',
            existing: Boolean(data.existing),
          });
        }
      }
    } catch (error) {
      paperState.failedGroups.push({ search_id, candidate_ids, code: error.code || 'IMPORT_BATCH_ERROR' });
    } finally {
      paperState.submitInflight -= 1;
      paperState.inFlightImports.delete(importKey);
    }
  }
  if (created.length) schedulePaperBatchPoll();
  renderDirectImports();
  renderImportSummary();
}

function paperBatchTerminal(batch) {
  return ['completed', 'partial_success', 'failed', 'cancelled'].includes(batch?.status || batch?.state);
}

function schedulePaperBatchPoll() {
  if (!paperState.enabled || paperState.batchPollTimer) return;
  const pollSerial = ++paperState.batchPollSerial;
  const isCurrentPoll = () => paperState.enabled && pollSerial === paperState.batchPollSerial;
  paperState.batchPollTimer = window.setInterval(async () => {
    if (!isCurrentPoll()) {
      window.clearInterval(paperState.batchPollTimer);
      paperState.batchPollTimer = null;
      return;
    }
    const ids = [...paperState.batches.keys()];
    if (!ids.length || ids.every((id) => paperBatchTerminal(paperState.batches.get(id)))) {
      window.clearInterval(paperState.batchPollTimer); paperState.batchPollTimer = null;
      renderImportSummary();
      return;
    }
    await Promise.all(ids.map(async (batchId) => {
      if (!isCurrentPoll() || paperBatchTerminal(paperState.batches.get(batchId))) return;
      try {
        const response = await fetch(`/api/papers/imports/${encodeURIComponent(batchId)}`);
        const data = await paperJson(response);
        if (!isCurrentPoll()) return;
        paperState.batches.set(batchId, data); renderPaperBatch(data);
      } catch (error) {
        if (isCurrentPoll()) paperState.lastImportError = error.code || 'IMPORT_BATCH_ERROR';
      }
    }));
    renderImportSummary();
  }, 2500);
}

function renderPaperBatch(batch) {
  if (!paperImportPanel || !paperImportItems) return;
  const batchId = paperText(batch.batch_id, '');
  if (!batchId) return;
  paperImportPanel.hidden = false;
  let batchContainer = [...paperImportItems.children].find((node) => node.dataset.batchId === batchId);
  if (!batchContainer) {
    batchContainer = document.createElement('li');
    batchContainer.className = 'paper-import-batch';
    batchContainer.dataset.batchId = batchId;
    paperImportItems.appendChild(batchContainer);
  }
  batchContainer.classList.toggle('is-progressing', !paperBatchTerminal(batch) || paperState.retryingBatchIds.has(batchId));
  batchContainer.replaceChildren();
  const label = PAPER_STATUS_TEXT[batch.status || batch.state] || '处理中';
  const batchHeader = document.createElement('div'); batchHeader.className = 'paper-import-batch-header';
  const batchTitle = document.createElement('h3'); batchTitle.textContent = `批次 ${batchId} · ${label}`;
  const batchSummary = document.createElement('span'); batchSummary.textContent = `${batch.completed_count || 0}/${batch.total_count || batch.items?.length || 0} 已完成`;
  batchHeader.append(batchTitle, batchSummary); batchContainer.appendChild(batchHeader);
  const batchItems = document.createElement('ul'); batchItems.className = 'paper-import-items'; batchContainer.appendChild(batchItems);
  const candidatesById = paperState.candidateById;
  const loginItems = [];
  (batch.items || []).forEach((item) => {
    const row = document.createElement('li'); row.className = 'paper-import-item';
    const title = document.createElement('span'); title.className = 'paper-import-item-title';
    title.textContent = paperText(candidatesById.get(item.candidate_id)?.title, item.stored_name || '未命名论文'); row.appendChild(title);
    const state = document.createElement('span'); state.textContent = PAPER_STATUS_TEXT[item.status || item.state] || '处理中'; row.appendChild(state);
    if (item.error_code) { const error = document.createElement('span'); error.className = 'paper-import-error'; error.textContent = PAPER_ERROR_TEXT[item.error_code] || '该论文导入失败'; row.appendChild(error); }
    if ((item.status || item.state) === 'waiting_login') loginItems.push(item);
    if (item.paper_id) {
      const jump = document.createElement('button'); jump.type = 'button'; jump.className = 'secondary-button'; jump.textContent = '在知识库中查看';
      jump.addEventListener('click', () => jumpToKnowledgeBase(item.paper_id)); row.appendChild(jump);
    }
    if ((item.status || item.state) === 'failed' && item.item_id) {
      const retryItem = document.createElement('button'); retryItem.type = 'button'; retryItem.className = 'secondary-button'; retryItem.textContent = '重试';
      if (paperState.retryingBatchIds.has(batchId)) retryItem.disabled = true;
      retryItem.addEventListener('click', async () => {
        if (!paperState.enabled) return;
        retryItem.disabled = true;
        paperState.retryingBatchIds.add(batchId);
        paperState.submitInflight += 1;
        renderPaperBatch(batch);
        renderImportSummary();
        let ok = false;
        try {
          const response = await fetch(`/api/papers/import-items/${encodeURIComponent(item.item_id)}/retry`, { method: 'POST' });
          const data = await paperJson(response);
          paperState.batches.set(data.batch_id, data); renderPaperBatch(data); schedulePaperBatchPoll(); ok = true;
        } catch (error) {
          paperState.lastImportError = error.code || 'IMPORT_BATCH_ERROR';
        } finally {
          paperState.retryingBatchIds.delete(batchId);
          paperState.submitInflight -= 1;
          if (!ok) renderPaperBatch(batch);
          renderImportSummary();
        }
      });
      row.appendChild(retryItem);
    }
    batchItems.appendChild(row);
  });
  const failedItems = (batch.items || []).filter((item) => (item.status || item.state) === 'failed');
  if (failedItems.length) {
    const retry = document.createElement('button'); retry.type = 'button'; retry.className = 'secondary-button'; retry.textContent = '重试失败项';
    if (paperState.retryingBatchIds.has(batchId)) retry.disabled = true;
    retry.addEventListener('click', async () => {
      if (!paperState.enabled) return;
      retry.disabled = true;
      paperState.retryingBatchIds.add(batchId);
      paperState.submitInflight += 1;
      renderPaperBatch(batch);
      renderImportSummary();
      let ok = false;
      try {
        const response = await fetch(`/api/papers/imports/${encodeURIComponent(batch.batch_id)}/retry`, { method: 'POST' });
        const data = await paperJson(response); paperState.batches.set(data.batch_id, data); renderPaperBatch(data); schedulePaperBatchPoll(); ok = true;
      } catch (error) {
        paperState.lastImportError = error.code || 'IMPORT_BATCH_ERROR';
      } finally {
        paperState.retryingBatchIds.delete(batchId);
        paperState.submitInflight -= 1;
        if (!ok) renderPaperBatch(batch);
        renderImportSummary();
      }
    });
    batchItems.appendChild(retry);
  }
  const batchState = batch.status || batch.state;
  if (['queued', 'waiting_login', 'failed'].includes(batchState)) {
    const cancel = document.createElement('button'); cancel.type = 'button'; cancel.className = 'secondary-button'; cancel.textContent = '取消';
    cancel.addEventListener('click', async () => {
      if (!paperState.enabled) return;
      cancel.disabled = true;
      try {
        const response = await fetch(`/api/papers/import-batches/${encodeURIComponent(batch.batch_id)}/cancel`, { method: 'POST' });
        const data = await paperJson(response);
        paperState.batches.set(data.batch_id, data); renderPaperBatch(data);
      } catch (error) {
        paperState.lastImportError = error.code || 'IMPORT_BATCH_ERROR';
        renderPaperBatch(batch);
      }
      renderImportSummary();
    });
    batchItems.appendChild(cancel);
  }
  const loginQueue = document.createElement('section'); loginQueue.className = 'paper-login-queue';
  loginQueue.hidden = loginItems.length === 0;
  const loginTitle = document.createElement('h3'); loginTitle.textContent = '需要登录后继续'; loginQueue.appendChild(loginTitle);
  const loginList = document.createElement('ul'); loginQueue.appendChild(loginList);
  loginItems.forEach((item) => {
    const row = document.createElement('li'); const text = document.createElement('span'); text.textContent = '论文需要登录后下载'; row.appendChild(text);
    const login = document.createElement('button'); login.type = 'button'; login.className = 'secondary-button'; login.textContent = '打开登录';
    login.addEventListener('click', () => paperLogin(item, login));
    const resume = document.createElement('button'); resume.type = 'button'; resume.className = 'secondary-button'; resume.textContent = '登录完成，继续';
    resume.addEventListener('click', () => paperResume(item, resume)); row.append(login, resume); loginList.appendChild(row);
  });
  batchContainer.appendChild(loginQueue);
}

function renderDirectImports() {
  if (!paperImportPanel || !paperImportItems) return;
  const existing = [...paperImportItems.children].find((node) => node.dataset.direct === '1');
  if (!paperState.directImports.length) {
    if (existing) existing.remove();
    return;
  }
  paperImportPanel.hidden = false;
  const container = existing || document.createElement('li');
  container.className = 'paper-import-batch';
  container.dataset.direct = '1';
  if (!existing) paperImportItems.appendChild(container);
  container.replaceChildren();
  const header = document.createElement('div'); header.className = 'paper-import-batch-header';
  const heading = document.createElement('h3'); heading.textContent = '直接导入';
  const count = document.createElement('span'); count.textContent = `${paperState.directImports.length} 篇已完成`;
  header.append(heading, count); container.appendChild(header);
  const list = document.createElement('ul'); list.className = 'paper-import-items';
  paperState.directImports.forEach((item) => {
    const row = document.createElement('li'); row.className = 'paper-import-item';
    const title = document.createElement('span'); title.className = 'paper-import-item-title';
    title.textContent = paperText(paperState.candidateById.get(item.candidate_id)?.title, item.stored_name || '未命名论文');
    row.appendChild(title);
    const state = document.createElement('span'); state.textContent = item.existing ? '已在知识库' : '已完成';
    row.appendChild(state);
    if (item.paper_id) {
      const jump = document.createElement('button'); jump.type = 'button'; jump.className = 'secondary-button';
      jump.textContent = '在知识库中查看';
      jump.addEventListener('click', () => jumpToKnowledgeBase(item.paper_id));
      row.appendChild(jump);
    }
    list.appendChild(row);
  });
  container.appendChild(list);
}

function selectPaperConference(conferenceId) {
  let input = paperConferenceList
    ? [...paperConferenceList.querySelectorAll('input[type="checkbox"]')].find((candidate) => candidate.value === conferenceId)
    : null;
  if (!input && paperState.conferences.some((conference) => conference.conference_id === conferenceId && conference.enabled)) {
    renderPaperConferences();
    input = [...(paperConferenceList?.querySelectorAll('input[type="checkbox"]') || [])]
      .find((candidate) => candidate.value === conferenceId);
  }
  if (!input) return false;
  input.checked = true;
  syncPaperConferenceSearchSelection();
  input.dispatchEvent(new Event('change', { bubbles: true }));
  return true;
}

function syncPaperConferenceSearchSelection() {
  paperConferenceSearchResults?.querySelectorAll('[role="option"]').forEach((option) => {
    const selected = [...(paperConferenceList?.querySelectorAll('input[type="checkbox"]') || [])]
      .some((input) => input.value === option.dataset.conferenceId && input.checked);
    option.setAttribute('aria-selected', selected ? 'true' : 'false');
  });
}

async function paperLogin(item, button) {
  if (!paperState.enabled) return;
  button.disabled = true;
  try {
    const response = await fetch(`/api/papers/import-items/${encodeURIComponent(item.item_id)}/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    await paperJson(response); if (paperImportStatus) paperImportStatus.textContent = '已打开受控浏览器，请完成登录后返回继续。';
  } catch (error) { if (paperImportStatus) paperImportStatus.textContent = PAPER_ERROR_TEXT[error.code] || '浏览器当前不可用'; }
  finally { button.disabled = false; }
}

async function paperResume(item, button) {
  if (!paperState.enabled) return;
  button.disabled = true;
  try {
    const response = await fetch(`/api/papers/import-items/${encodeURIComponent(item.item_id)}/resume`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    const data = await paperJson(response); if (data.batch_id) { paperState.batches.set(data.batch_id, data); renderPaperBatch(data); schedulePaperBatchPoll(); }
  } catch (error) { if (paperImportStatus) paperImportStatus.textContent = PAPER_ERROR_TEXT[error.code] || '登录续传暂时不可用'; }
  finally { button.disabled = false; }
}

function jumpToKnowledgeBase(paperId) {
  paperState.pendingKbPaperId = paperId;
  showView('kb');
  loadKbPapers().then(() => {
    const item = [...document.querySelectorAll('[data-paper-id]')].find((node) => node.dataset.paperId === String(paperId));
    if (item) { item.scrollIntoView({ block: 'center' }); item.focus?.(); }
  });
}

async function loadPaperConferences() {
  if (!paperState.enabled) return;
  try {
    const conferenceResponse = await fetch('/api/papers/conferences');
    const data = await paperJson(conferenceResponse);
    if (!paperState.enabled) return;
    paperState.conferences = data.conferences || []; paperState.conferencesLoaded = true; renderPaperConferences();
    let count = 5;
    try {
      const settings = await paperJson(await fetch('/api/agent/settings'));
      count = Number(settings.paper_discovery_default_years) || count;
    } catch (_) {}
    const latest = new Date().getFullYear() - 1;
    if (paperYearFrom && !paperYearFrom.value) paperYearFrom.value = String(latest - count + 1);
    if (paperYearTo && !paperYearTo.value) paperYearTo.value = String(latest);
  } catch (error) {
    if (error.code === 'PAPER_DISCOVERY_DISABLED') setPaperEnabled(false);
    else if (paperConferenceStatus) paperConferenceStatus.textContent = PAPER_ERROR_TEXT[error.code] || '会议配置暂时不可用';
  }
}

async function searchPaperConferences() {
  if (!paperState.enabled) return;
  const query = (paperConferenceSearch?.value || '').trim();
  if (!query || !paperConferenceSearchResults) return;
  paperConferenceSearchResults.replaceChildren(); if (paperConferenceStatus) paperConferenceStatus.textContent = '正在搜索会议…';
  try {
    const params = new URLSearchParams({ q: query });
    const response = await fetch(`/api/papers/conferences/search?${params.toString()}`);
    const data = await paperJson(response);
    const matches = (data.conferences || []).filter((conference) => conference.conference_id && conference.enabled);
    matches.forEach((conference) => {
      const item = document.createElement('li');
      const selected = [...(paperConferenceList?.querySelectorAll('input[type="checkbox"]') || [])]
        .some((input) => input.value === conference.conference_id && input.checked);
      item.setAttribute('role', 'option'); item.setAttribute('aria-selected', selected ? 'true' : 'false'); item.tabIndex = 0;
      item.dataset.conferenceId = conference.conference_id;
      item.textContent = `${paperText(conference.short_name || conference.name, '未命名会议')} · ${paperText(conference.name, '')}`;
      const select = () => selectPaperConference(conference.conference_id);
      item.addEventListener('click', select);
      item.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(); }
      });
      paperConferenceSearchResults.appendChild(item);
    });
    if (paperConferenceStatus) paperConferenceStatus.textContent = matches.length ? '会议搜索完成' : '没有匹配的已配置会议';
  } catch (error) { if (paperConferenceStatus) paperConferenceStatus.textContent = PAPER_ERROR_TEXT[error.code] || '会议搜索暂时不可用'; }
}

async function renderManagedConferences() {
  if (!paperManagedConferences) return;
  paperManagedConferences.replaceChildren();
  paperState.conferences.forEach((conference) => {
    const item = document.createElement('li'); const label = document.createElement('span'); label.textContent = conference.short_name || conference.name || '未命名会议';
    const toggle = document.createElement('button'); toggle.type = 'button'; toggle.className = 'secondary-button'; toggle.textContent = conference.enabled ? '停用' : '启用'; toggle.disabled = !conference.conference_id;
    toggle.addEventListener('click', async () => {
      toggle.disabled = true;
      try {
        const response = await fetch(`/api/papers/conferences/${encodeURIComponent(conference.conference_id)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: !conference.enabled }) });
        const data = await paperJson(response); const updated = data.conference;
        paperState.conferences = paperState.conferences.map((value) => value.conference_id === updated.conference_id ? updated : value); renderPaperConferences(); renderManagedConferences();
      } catch (error) { if (paperConferenceDialogStatus) paperConferenceDialogStatus.textContent = PAPER_ERROR_TEXT[error.code] || '会议配置暂时无法更新'; toggle.disabled = false; }
    });
    item.append(label, toggle); paperManagedConferences.appendChild(item);
  });
}

if (paperForm) paperForm.addEventListener('submit', searchPapers);
if (paperSelectAll) paperSelectAll.addEventListener('change', () => { paperResults?.querySelectorAll('input[type="checkbox"]:not(:disabled)').forEach((input) => { input.checked = paperSelectAll.checked; }); updatePaperSelection(); });
if (paperImportSelected) paperImportSelected.addEventListener('click', () => importPaperCandidates([...paperResults.querySelectorAll('input[type="checkbox"]:checked')].map((input) => paperState.candidates.find((candidate) => candidate.candidate_id === input.dataset.candidateId))));
if (paperPrevPage) paperPrevPage.addEventListener('click', () => changePaperPage(paperState.searchPage - 1));
if (paperNextPage) paperNextPage.addEventListener('click', () => changePaperPage(paperState.searchPage + 1));
if (paperConferenceSearchButton) paperConferenceSearchButton.addEventListener('click', searchPaperConferences);
if (paperManageButton) paperManageButton.addEventListener('click', () => {
  if (!paperState.enabled) return;
  renderManagedConferences(); paperConferenceDialog?.showModal();
});
if (paperConferenceSearch) onEnterKey(paperConferenceSearch, (event) => { event.preventDefault(); searchPaperConferences(); });
// ===== Skill / Tool 管理视图（spec-023 Task08）：DOM 引用 =====
const stView = document.querySelector('#skill-tool-view');
const stSkillList = document.querySelector('#st-skill-list');
const stSkillEmpty = document.querySelector('#st-skill-empty');
const stSkillStatus = document.querySelector('#st-skill-status');
const stToolList = document.querySelector('#st-tool-list');
const stToolEmpty = document.querySelector('#st-tool-empty');
const stToolStatus = document.querySelector('#st-tool-status');
const stSkillDialog = document.querySelector('#st-skill-dialog');
const stDetailName = document.querySelector('#st-detail-name');
const stDetailDesc = document.querySelector('#st-detail-desc');
const stDetailTools = document.querySelector('#st-detail-tools');
const stDetailBody = document.querySelector('#st-detail-body');

// 后端错误体：{error_code, message, retryable, request_id}（见 routes_kb._document_error）。
async function stJson(response) {
  let data = {};
  try { data = await response.json(); } catch (_) {}
  if (!response.ok) {
    const err = new Error(typeof data?.message === 'string' && data.message ? data.message : '请求失败');
    err.code = typeof data?.error_code === 'string' ? data.error_code : '';
    throw err;
  }
  return data;
}

// spec-023.1 F2：发送请求并归一化错误。
// - 网络层失败（断网/后端未启动/CORS）→ 中文可读提示 + network: true；
// - 请求被主动取消（切换视图/连点详情）→ network: false，由调用处静默忽略；
// - 业务错误（4xx/5xx）→ 沿用 stJson 的后端 message 与 error_code。
async function stFetchJson(input, init) {
  let response;
  try {
    response = await fetch(input, init);
  } catch (error) {
    if (error?.name === 'AbortError') {
      const aborted = new Error('请求已取消');
      aborted.network = false;
      aborted.aborted = true;
      throw aborted;
    }
    const networkError = new Error('无法连接本地服务，请确认后端已启动');
    networkError.network = true;
    throw networkError;
  }
  return stJson(response);
}

// 模型库/知识库视图：导航切换 + 列表渲染（spec 006 / spec 011）
function showView(view) {
  const nextView = view === 'papers' && !paperState.enabled ? 'chat' : view;
  if (nextView !== 'papers' && !paperView?.hidden) cancelPaperSearchPolling();
  const isChat = nextView === 'chat';
  document.querySelector('#chat').hidden = !isChat;
  document.querySelector('#models-view').hidden = nextView !== 'models';
  if (memoryView) memoryView.hidden = nextView !== 'memory';
  document.querySelector('#kb-view').hidden = nextView !== 'kb';
  if (paperView) paperView.hidden = nextView !== 'papers' || !paperState.enabled;
  if (stView) stView.hidden = nextView !== 'skill-tool';
  document.querySelectorAll('.nav-item').forEach((item) => {
    const isCurrent = item.dataset.view === nextView;
    item.classList.toggle('active', isCurrent);
    item.setAttribute('aria-current', isCurrent ? 'page' : 'false');
    if (item.dataset.view === 'papers') item.hidden = !paperState.enabled;
  });
  if (nextView === 'kb') {
    loadKbPapers();
    loadKbHealth();
  }
  if (nextView === 'memory') {
    const isProject = memoryScopeSelect?.value === 'project';
    if (memoryProjectLabel) memoryProjectLabel.hidden = !isProject;
    restoreMemoryViewState();
    loadSystemRule();
    if (memoryNavigationSnapshot.scope === null) loadMemories();
  }
  if (nextView === 'papers' && paperState.enabled && !paperState.conferencesLoaded) loadPaperConferences();
  if (nextView === 'skill-tool') {
    loadSkills();
    loadTools();
  }
}

document.querySelectorAll('.nav-item').forEach((item) => {
  item.addEventListener('click', (event) => {
    event.preventDefault();
    if (memoryView && !memoryView.hidden && item.dataset.view !== 'memory') captureMemoryViewState();
    if (item.dataset.view === 'chat') {
      conversationState.projectId = null;
      conversationState.draftProjectId = null;
      renderProjectList(projectState.items);
      loadConversationList();
    }
    showView(item.dataset.view);
  });
  item.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    item.click();
  });
});

showView('chat');

// ===== Skill / Tool 管理视图（spec-023 Task08） =====
let stSkills = [];
let stTools = [];
// spec-023.1 F1：详情请求序号，保证只有最后一次请求的结果被渲染（丢弃慢到的旧响应）。
const stState = { detailSeq: 0, detailController: null };

async function loadSkills() {
  if (stSkillStatus) stSkillStatus.textContent = '正在加载 Skill…';
  try {
    const data = await stFetchJson('/api/skills');
    stSkills = Array.isArray(data.skills) ? data.skills : [];
    renderSkillList();
    if (stSkillStatus) stSkillStatus.textContent = '';
  } catch (error) {
    if (stSkillStatus) stSkillStatus.textContent = `Skill 加载失败：${error.message}`;
    if (stSkillList) stSkillList.replaceChildren();
    if (stSkillEmpty) { stSkillEmpty.hidden = false; stSkillEmpty.textContent = 'Skill 列表加载失败，请稍后重试。'; }
  }
}

// spec-032.1 Task05：Skill 遗留（待迁移）标记。
// 仅当后端返回 legacy === true 时构造标记；false / 缺失（undefined/null）一律不渲染。
// 标记纯展示，用 DOM API + textContent 构造，绝不拼 innerHTML。
function buildLegacyBadge(legacy) {
  if (legacy === true) {
    const badge = document.createElement('span');
    badge.classList.add('st-legacy-badge');
    badge.textContent = '遗留（待迁移）';
    return badge;
  }
  return null;
}

function renderSkillList() {
  if (!stSkillList) return;
  stSkillList.replaceChildren();
  if (stSkillEmpty) {
    stSkillEmpty.hidden = stSkills.length > 0;
    if (stSkills.length === 0) stSkillEmpty.textContent = '还没有可用的 Skill。';
  }
  for (const skill of stSkills) {
    const li = document.createElement('li');
    li.className = 'st-item';

    const textWrap = document.createElement('div');
    textWrap.className = 'st-text';
    const name = document.createElement('span');
    name.className = 'st-name';
    name.textContent = skill.name || '未命名 Skill';
    const legacyBadge = buildLegacyBadge(skill.legacy);
    if (legacyBadge) name.appendChild(legacyBadge);
    const desc = document.createElement('p');
    desc.className = 'st-desc';
    desc.textContent = skill.description || '';
    const tools = document.createElement('p');
    tools.className = 'st-tools';
    const toolNames = Array.isArray(skill.tools) ? skill.tools : [];
    tools.textContent = toolNames.length ? `工具：${toolNames.join('、')}` : '未声明工具';
    textWrap.append(name, desc, tools);

    const actions = document.createElement('div');
    actions.className = 'st-actions';
    const detailBtn = document.createElement('button');
    detailBtn.type = 'button';
    detailBtn.className = 'secondary-button';
    detailBtn.textContent = '详情';
    detailBtn.disabled = !skill.name;
    // spec-023.1 F1：点击即禁用并显示 loading，避免连点并发；请求结束后恢复。
    detailBtn.addEventListener('click', (event) => {
      event.stopPropagation();
      if (detailBtn.disabled) return;
      detailBtn.disabled = true;
      detailBtn.textContent = '加载中…';
      openSkillDetail(skill.name, detailBtn);
    });
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'secondary-button';
    toggle.textContent = skill.enabled ? '停用' : '启用';
    toggle.disabled = !skill.name;
    toggle.addEventListener('click', (event) => { event.stopPropagation(); toggleSkill(skill, toggle); });
    actions.append(detailBtn, toggle);

    li.append(textWrap, actions);
    stSkillList.appendChild(li);
  }
}

async function toggleSkill(skill, button) {
  if (!button || !skill.name) return;
  button.disabled = true;
  try {
    const data = await stFetchJson(`/api/skills/${encodeURIComponent(skill.name)}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: !skill.enabled }),
    });
    skill.enabled = Boolean(data.enabled);
    button.textContent = skill.enabled ? '停用' : '启用';
    if (stSkillStatus) stSkillStatus.textContent = '';
  } catch (error) {
    if (stSkillStatus) stSkillStatus.textContent = `Skill「${skill.name}」状态更新失败：${error.message}`;
  } finally {
    button.disabled = false;
  }
}

async function openSkillDetail(name, button) {
  if (!stSkillDialog) return;
  // spec-023.1 F1：每次打开自增序号并中止上一次请求，慢响应后到时因令牌不符被丢弃。
  const seq = ++stState.detailSeq;
  if (stState.detailController) stState.detailController.abort();
  const controller = new AbortController();
  stState.detailController = controller;
  if (stDetailName) {
    stDetailName.textContent = name || '';
    // 每次打开先清掉上一次的遗留标记，等响应返回后按 legacy 决定是否重建。
    stDetailName.querySelectorAll('.st-legacy-badge').forEach((node) => node.remove());
  }
  if (stDetailDesc) stDetailDesc.textContent = '';
  if (stDetailTools) stDetailTools.textContent = '';
  if (stDetailBody) stDetailBody.textContent = '加载中…';
  stSkillDialog.showModal();
  try {
    const data = await stFetchJson(`/api/skills/${encodeURIComponent(name)}`, { signal: controller.signal });
    if (stState.detailSeq !== seq || controller.signal.aborted) return;
    // spec-032.1 Task05：详情同样按 legacy === true 展示遗留标记（纯展示，不影响开关）。
    const legacyBadge = buildLegacyBadge(data.legacy);
    if (legacyBadge && stDetailName) stDetailName.appendChild(legacyBadge);
    if (stDetailDesc) stDetailDesc.textContent = data.description || '（无描述）';
    const toolNames = Array.isArray(data.tools) ? data.tools : [];
    if (stDetailTools) stDetailTools.textContent = toolNames.length ? `工具：${toolNames.join('、')}` : '未声明工具';
    if (stDetailBody) stDetailBody.textContent = data.body || '（正文为空）';
  } catch (error) {
    if (stState.detailSeq !== seq || controller.signal.aborted) return;
    // spec-023.1 F3：失败时 body/desc/tools 统一展示同一失败文案，避免「名称有值 + 描述/工具空白 + 正文报错」的割裂展示。
    const failure = `加载失败：${error.message}`;
    if (stDetailDesc) stDetailDesc.textContent = failure;
    if (stDetailTools) stDetailTools.textContent = failure;
    if (stDetailBody) stDetailBody.textContent = failure;
  } finally {
    if (stState.detailSeq === seq && stState.detailController === controller) stState.detailController = null;
    if (button) { button.disabled = false; button.textContent = '详情'; }
  }
}

async function loadTools() {
  if (stToolStatus) stToolStatus.textContent = '正在加载 Tool…';
  try {
    const data = await stFetchJson('/api/tools');
    stTools = Array.isArray(data.tools) ? data.tools : [];
    renderToolList();
    if (stToolStatus) stToolStatus.textContent = '';
  } catch (error) {
    if (stToolStatus) stToolStatus.textContent = `Tool 加载失败：${error.message}`;
    if (stToolList) stToolList.replaceChildren();
    if (stToolEmpty) { stToolEmpty.hidden = false; stToolEmpty.textContent = 'Tool 列表加载失败，请稍后重试。'; }
  }
}

function renderToolList() {
  if (!stToolList) return;
  stToolList.replaceChildren();
  if (stToolEmpty) {
    stToolEmpty.hidden = stTools.length > 0;
    if (stTools.length === 0) stToolEmpty.textContent = '还没有可用的 Tool。';
  }
  for (const tool of stTools) {
    const li = document.createElement('li');
    li.className = 'st-item';

    const textWrap = document.createElement('div');
    textWrap.className = 'st-text';
    const name = document.createElement('span');
    name.className = 'st-name';
    name.textContent = tool.name || '未命名 Tool';
    const desc = document.createElement('p');
    desc.className = 'st-desc';
    desc.textContent = tool.description || '';
    textWrap.append(name, desc);

    const actions = document.createElement('div');
    actions.className = 'st-actions';
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'secondary-button';
    toggle.textContent = tool.enabled ? '停用' : '启用';
    toggle.disabled = !tool.name;
    toggle.addEventListener('click', () => toggleTool(tool, toggle));
    actions.append(toggle);

    li.append(textWrap, actions);
    stToolList.appendChild(li);
  }
}

async function toggleTool(tool, button) {
  if (!button || !tool.name) return;
  button.disabled = true;
  try {
    const data = await stFetchJson(`/api/tools/${encodeURIComponent(tool.name)}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: !tool.enabled }),
    });
    tool.enabled = Boolean(data.enabled);
    button.textContent = tool.enabled ? '停用' : '启用';
    if (stToolStatus) stToolStatus.textContent = '';
  } catch (error) {
    if (stToolStatus) stToolStatus.textContent = `Tool「${tool.name}」状态更新失败：${error.message}`;
  } finally {
    button.disabled = false;
  }
}

function refreshModelOptions() {
  if (!modelSelect) return;
  const selected = modelSelect.value;
  while (modelSelect.firstChild) modelSelect.removeChild(modelSelect.firstChild);
  if (currentModels.length) {
    for (const m of currentModels) {
      const opt = document.createElement('option');
      opt.value = m;
      opt.textContent = displayName(m);
      modelSelect.appendChild(opt);
    }
  } else {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = '没有发现模型';
    modelSelect.appendChild(opt);
  }
  modelSelect.value = selected;
  modelSelect.disabled = currentModels.length === 0;
}

function setAlias(model, alias) {
  const aliases = loadAliases();
  const value = (alias || '').trim();
  if (value) aliases[model] = value; else delete aliases[model];
  saveAliases(aliases);
}

// 重名检测：除当前 model 外，是否已有其它模型使用同一别名（R4）
function findAliasConflict(model, alias) {
  const v = (alias || '').trim();
  if (!v) return null;
  const aliases = loadAliases();
  for (const key of Object.keys(aliases)) {
    if (key === model) continue;
    if (aliases[key] === v) return key;
  }
  return null;
}

function renderModelText(textWrap, model) {
  const alias = loadAliases()[model];
  const nameSpan = document.createElement('span');
  nameSpan.className = 'model-name';
  nameSpan.textContent = alias || model;
  const realSpan = document.createElement('span');
  realSpan.className = 'model-real';
  realSpan.textContent = model;
  realSpan.hidden = !alias;
  textWrap.replaceChildren(nameSpan, realSpan);
}

// 行内编辑：卡片内名字原地变输入框（Enter/失焦保存，Esc 取消）
function enterAliasEdit(textWrap, model) {
  if (textWrap.querySelector('.alias-input')) return;
  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'alias-input';
  input.maxLength = 40;
  input.value = loadAliases()[model] || '';
  input.placeholder = '别名（留空用原名）';
  let saved = false;
  // 重名提示节点（R4）：作为 input 的兄弟节点，用 textContent 保证 XSS 安全
  const warning = document.createElement('span');
  warning.className = 'alias-warn';
  warning.textContent = '已有其它模型使用此别名';
  warning.hidden = true;
  // 点到提示文字时不让事件冒泡到卡片，且把焦点拉回输入框（保持编辑态）
  warning.addEventListener('click', (event) => {
    event.stopPropagation();
    input.focus();
  });
  warning.addEventListener('blur', () => input.focus());
  const showWarning = (show) => {
    warning.hidden = !show;
    if (show) input.focus();
  };
  const finish = (commit) => {
    if (saved) return;
    if (commit) {
      // R4：提交前检测是否与其它模型重名
      const conflict = findAliasConflict(model, input.value);
      if (conflict) {
        showWarning(true);
        return; // 保留编辑态：不置 saved、不渲染，等待用户改掉或 Esc 取消
      }
    }
    saved = true;
    if (commit) setAlias(model, input.value);
    renderModelText(textWrap, model);
    refreshModelOptions();
    if (modelLabel) modelLabel.textContent = displayName(activeModel);
  };
  input.addEventListener('click', (event) => event.stopPropagation());
  input.addEventListener('keydown', (event) => {
    event.stopPropagation();
    if (event.key === 'Escape') { event.preventDefault(); finish(false); }
  });
  onEnterKey(input, (event) => { event.preventDefault(); finish(true); });
  // 输入变化时清掉旧提示，让提示始终反映当前输入
  input.addEventListener('input', () => { if (!warning.hidden) warning.hidden = true; });
  input.addEventListener('blur', () => finish(true));
  textWrap.replaceChildren(input, warning);
  input.focus();
  input.select();
}

function renderModelList(models, current) {
  const list = document.querySelector('#model-list');
  const empty = document.querySelector('#model-empty');
  if (!list) return;
  list.replaceChildren();
  currentModels = models;
  if (models.length === 0 && empty) empty.textContent = '暂无可用模型';
  empty.hidden = models.length > 0;
  for (const name of models) {
    const li = document.createElement('li');
    li.className = `model-item${name === current ? ' current' : ''}`;
    li.dataset.model = name;

    const textWrap = document.createElement('div');
    textWrap.className = 'model-text';
    renderModelText(textWrap, name);

    const editBtn = document.createElement('button');
    editBtn.type = 'button';
    editBtn.className = 'model-edit';
    editBtn.title = '编辑别名';
    editBtn.setAttribute('aria-label', '编辑别名');
    editBtn.textContent = '✎';
    editBtn.addEventListener('click', (event) => {
      event.stopPropagation();
      enterAliasEdit(textWrap, name);
    });

    const badge = document.createElement('span');
    badge.className = `model-badge${name === current ? ' current' : ''}`;
    badge.textContent = name === current ? '当前' : '可用';

    li.appendChild(textWrap);
    li.appendChild(editBtn);
    li.appendChild(badge);

    li.addEventListener('click', () => {
      activeModel = name;
      if (modelSelect) {
        modelSelect.value = name;
        modelSelect.disabled = false;
      }
      if (modelLabel) modelLabel.textContent = displayName(name);
      list.querySelectorAll('.model-item').forEach((node) => {
        node.classList.remove('current');
        const b = node.querySelector('.model-badge');
        if (b) { b.classList.remove('current'); b.textContent = '可用'; }
      });
      li.classList.add('current');
      badge.classList.add('current');
      badge.textContent = '当前';
    });
    list.appendChild(li);
  }
}

// ===== 知识库视图（spec-011）：本地论文 RAG =====
const kbFileInput = document.querySelector('#kb-file');
const kbDrop = document.querySelector('#kb-drop');
const kbStatus = document.querySelector('#kb-status');
const kbList = document.querySelector('#kb-list');
const kbEmpty = document.querySelector('#kb-empty');
const kbCount = document.querySelector('#kb-count');
const kbNavCount = document.querySelector('#kb-nav-count');
const kbHealth = document.querySelector('#kb-health');
const kbAnswers = document.querySelector('#kb-answers');
const kbForm = document.querySelector('#kb-ask-form');
const kbQuestion = document.querySelector('#kb-question');
const kbSend = document.querySelector('#kb-send');
const kbModelSelect = document.querySelector('#kb-model-select');
const kbChunkerSelect = document.querySelector('#kb-chunker-select');

const KB_STATUS_TEXT = {
  pending: '待索引',
  indexing: '索引中',
  indexed: '已索引',
  indexed_partial: '部分索引',
  failed: '索引失败',
};

// ===== Markdown 渲染（spec-011）：把模型输出渲染为富文本 =====
// XSS 底线：模型/论文内容一律「先净化、后 innerHTML」；vendor 缺失时降级为转义纯文本，绝不裸奔。
function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[char]));
}

function renderMarkdown(source) {
  const text = String(source || '');
  if (!window.marked || !window.DOMPurify) {
    return escapeHtml(text).replace(/\n/g, '<br>'); // 降级：库未加载时按纯文本展示
  }
  const html = window.marked.parse(text, { gfm: true, breaks: true });
  return window.DOMPurify.sanitize(html, {
    FORBID_TAGS: ['script', 'style', 'iframe', 'img', 'form', 'input', 'object', 'embed'],
    FORBID_ATTR: ['style', 'onerror', 'onload', 'onclick', 'onmouseover'],
  });
}

// 外链新窗口打开并阻断 tabnabbing（注册一次即可）
if (window.DOMPurify) {
  window.DOMPurify.addHook('afterSanitizeAttributes', (node) => {
    if (node.tagName === 'A' && node.getAttribute('href')) {
      node.setAttribute('target', '_blank');
      node.setAttribute('rel', 'noopener noreferrer nofollow');
    }
  });
}

// 流式写入器：逐 token 追加时按帧节流，避免每收到一个字就重解析整段 Markdown
// scrollTarget 显式传入（知识库传 #kb-answers，聊天传 #messages），不写死容器
function createMarkdownWriter(element, scrollTarget) {
  let raw = '';
  let frame = 0;
  let cancelled = false;

  function paint() {
    frame = 0;
    if (cancelled) return;
    element.innerHTML = renderMarkdown(raw);
    if (scrollTarget) scrollTarget.scrollTop = scrollTarget.scrollHeight;
  }

  return {
    write(chunk) {
      if (cancelled) return;
      raw += chunk || '';
      if (frame) return;
      frame = requestAnimationFrame(paint);
    },
    flush() {
      if (cancelled) return;
      if (frame) {
        cancelAnimationFrame(frame);
        frame = 0;
      }
      paint();
    },
    cancel() {
      cancelled = true;
      if (frame) {
        cancelAnimationFrame(frame);
        frame = 0;
      }
    },
  };
}

function refreshKbModelOptions() {
  if (!kbModelSelect) return;
  const selected = kbModelSelect.value || modelSelect?.value || activeModel;
  while (kbModelSelect.firstChild) kbModelSelect.removeChild(kbModelSelect.firstChild);
  if (currentModels.length) {
    for (const name of currentModels) {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = displayName(name);
      kbModelSelect.appendChild(opt);
    }
  } else {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = '没有发现模型';
    kbModelSelect.appendChild(opt);
  }
  kbModelSelect.value = selected;
  kbModelSelect.disabled = currentModels.length === 0;
}

// 顶部 modelSelect 与知识库下拉双向同步，二者共用同一份模型清单与别名
if (kbModelSelect) {
  kbModelSelect.addEventListener('change', () => {
    activeModel = kbModelSelect.value;
    if (modelSelect) modelSelect.value = activeModel;
    if (modelLabel) modelLabel.textContent = displayName(activeModel);
  });
}
if (modelSelect) {
  modelSelect.addEventListener('change', () => {
    if (kbModelSelect) kbModelSelect.value = modelSelect.value;
  });
}

// 轮询：仅在存在「索引中」的版本时按 2.5s 刷新，全部完成后自动停止（spec-012）
let kbPollTimer = null;

function stopKbPoll() {
  if (kbPollTimer) {
    window.clearInterval(kbPollTimer);
    kbPollTimer = null;
  }
}

function scheduleKbPoll() {
  if (kbPollTimer) return;
  kbPollTimer = window.setInterval(() => {
    loadKbPapers();
  }, 2500);
}

async function loadKbPapers() {
  if (!kbList) return false;
  try {
    const response = await fetch('/api/kb/papers');
    const data = await response.json();
    return renderKbPapers(data.papers || []);
  } catch (error) {
    if (kbStatus) kbStatus.textContent = `列表加载失败：${error.message}`;
    return false;
  }
}

function chunkerBadgeText(name, state) {
  const label = KB_STATUS_TEXT[state.status] || state.status || '未知';
  if (state.status === 'indexing') return `${name} ${label} ${state.progress || 0}%`;
  if (state.chunk_count) return `${name} ${label} · ${state.chunk_count} 片段`;
  return `${name} ${label}`;
}

async function rebuildKbPaper(paper, button) {
  if (button) button.disabled = true;
  try {
    const response = await fetch(`/api/kb/papers/${encodeURIComponent(paper.paper_id)}/reindex`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chunker: 'all' }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || '重建失败');
    if (kbStatus) kbStatus.textContent = `已提交重建：${paper.file_name || '未命名论文'}（v1 + v2）`;
  } catch (error) {
    if (kbStatus) kbStatus.textContent = `重建失败：${error.message}`;
  }
  await loadKbPapers();
}

function renderKbPapers(papers) {
  kbList.replaceChildren();
  if (kbCount) kbCount.textContent = String(papers.length);
  if (kbNavCount) kbNavCount.textContent = String(papers.length);
  kbEmpty.hidden = papers.length > 0;

  let hasRunning = false;
  for (const paper of papers) {
    const item = document.createElement('li');
    item.className = `kb-item status-${paper.status || 'unknown'}`;
    if (paper.paper_id) item.dataset.paperId = paper.paper_id;
    item.tabIndex = -1;
    if (paper.error) item.title = paper.error;

    const head = document.createElement('div');
    head.className = 'kb-item-head';

    const name = document.createElement('span');
    name.className = 'kb-item-name';
    name.textContent = paper.file_name || '未命名论文';
    head.appendChild(name);

    const meta = document.createElement('span');
    meta.className = 'kb-item-meta';
    meta.textContent = `${KB_STATUS_TEXT[paper.status] || paper.status || '未知'} · ${paper.page_count || 0} 页`;

    // 双版本状态与百分比进度（spec-012）
    const versions = document.createElement('div');
    versions.className = 'kb-item-versions';
    const chunkers = paper.chunkers || {};
    const bars = [];
    for (const key of ['v1', 'v2']) {
      const state = chunkers[key] || { status: 'pending', progress: 0, chunk_count: 0 };
      if (state.status === 'indexing') hasRunning = true;
      const badge = document.createElement('span');
      badge.className = `kb-chunker-badge status-${state.status}`;
      badge.textContent = chunkerBadgeText(key, state);
      versions.appendChild(badge);
      if (state.status === 'indexing') {
        const bar = document.createElement('div');
        bar.className = 'kb-progress';
        bar.setAttribute('role', 'progressbar');
        bar.setAttribute('aria-valuenow', String(state.progress || 0));
        bar.setAttribute('aria-valuemin', '0');
        bar.setAttribute('aria-valuemax', '100');
        const fill = document.createElement('div');
        fill.className = 'kb-progress-fill';
        fill.style.width = `${Math.max(0, Math.min(100, state.progress || 0))}%`;
        bar.appendChild(fill);
        bars.push(bar);
      }
    }

    const actions = document.createElement('div');
    actions.className = 'kb-item-actions';

    const rebuild = document.createElement('button');
    rebuild.type = 'button';
    rebuild.className = 'kb-item-rebuild';
    rebuild.textContent = '重建索引';
    rebuild.setAttribute('aria-label', `重建索引 ${paper.file_name || '论文'}`);
    rebuild.addEventListener('click', () => rebuildKbPaper(paper, rebuild));

    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'kb-item-remove';
    remove.textContent = '删除';
    remove.setAttribute('aria-label', `删除 ${paper.file_name || '论文'}`);
    remove.addEventListener('click', async () => {
      // 删除不可恢复，先二次确认（spec-011 产品裁决 ④）
      if (!window.confirm(`确定删除《${paper.file_name || '未命名论文'}》？该论文的原件与索引将一并清除，且不可恢复。`)) return;
      remove.disabled = true;
      try {
        const response = await fetch(`/api/kb/papers/${encodeURIComponent(paper.paper_id)}`, { method: 'DELETE' });
        if (!response.ok && response.status !== 404) throw new Error('服务端删除失败');
        if (kbStatus) kbStatus.textContent = '已删除';
      } catch (error) {
        remove.disabled = false;
        if (kbStatus) kbStatus.textContent = `删除失败：${error.message}`;
      }
      loadKbPapers();
      loadKbHealth();
    });

    actions.append(rebuild, remove);
    versions.appendChild(actions);
    item.append(head, meta, versions, ...bars);
    kbList.appendChild(item);
  }

  if (hasRunning) scheduleKbPoll();
  else stopKbPoll();
  return hasRunning;
}

async function loadKbHealth() {
  if (!kbHealth) return;
  try {
    const response = await fetch('/api/kb/health');
    const data = await response.json();
    const v2llm = data.v2_llm || {};
    const detail = data.reranker_detail;
    let rerankerStatus = data.reranker ? '启用' : '未启用（RRF 直出）';
    if (detail && typeof detail === 'object') {
      if (detail.enabled === false) {
        rerankerStatus = '未启用（RRF 直出）';
      } else if (detail.enabled === true && detail.available === true) {
        rerankerStatus = '启用';
      } else if (detail.enabled === true && detail.available === false) {
        const reason = typeof detail.reason === 'string' ? detail.reason.trim() : '';
        const safeReason = /^[a-z][a-z0-9_]{0,39}$/.test(reason) ? reason : 'unavailable';
        rerankerStatus = `不可用：${safeReason}`;
      }
    }
    kbHealth.textContent = `Qdrant ${data.qdrant ? '就绪' : '不可用'} · Embedding ${data.embedding ? '就绪' : '不可用'} · 重排 ${rerankerStatus} · ${data.chunks ?? 0} 个片段 · v2 结构分析 ${v2llm.available ? '就绪' : '不可用（将降级为规则切分）'}`;
  } catch (error) {
    kbHealth.textContent = `组件状态读取失败：${error.message}`;
  }
}

function kbUploadErrorMessage(data) {
  const message = typeof data?.message === 'string' ? data.message.trim() : '';
  const code = typeof data?.error_code === 'string' ? data.error_code.trim() : '';
  if (message && code) return `${message}（${code}）`;
  return message || code || (typeof data?.detail === 'string' ? data.detail : '') || '上传失败';
}

if (kbDrop && kbFileInput) {
  kbDrop.addEventListener('click', () => kbFileInput.click());
  kbFileInput.addEventListener('change', async () => {
    const file = kbFileInput.files && kbFileInput.files[0];
    if (!file) return;
    if (kbStatus) kbStatus.textContent = `正在上传并索引：${file.name}`;
    const body = new FormData();
    body.append('file', file);
    try {
      const response = await fetch('/api/kb/upload', { method: 'POST', body });
      let data = {};
      try { data = await response.json(); } catch (_) {}
      if (!response.ok) {
        const error = new Error(kbUploadErrorMessage(data));
        error.code = data?.error_code || '';
        throw error;
      }
      if (kbStatus) {
        kbStatus.textContent = `${data.file_name}：${KB_STATUS_TEXT[data.status] || data.status}${data.error ? `（${data.error}）` : ''}`;
      }
    } catch (error) {
      if (kbStatus) kbStatus.textContent = `上传失败：${error.message}`;
    } finally {
      kbFileInput.value = '';
      loadKbPapers();
      loadKbHealth();
    }
  });
}

function appendKbMessage(role) {
  const wrap = document.createElement('div');
  wrap.className = `kb-message ${role}`;
  const bubble = document.createElement('div');
  bubble.className = 'kb-bubble';
  wrap.appendChild(bubble);
  kbAnswers.appendChild(wrap);
  kbAnswers.scrollTop = kbAnswers.scrollHeight;
  return bubble;
}

function renderKbCitations(container, citations) {
  container.replaceChildren();
  if (!citations || citations.length === 0) return;
  const title = document.createElement('span');
  title.className = 'kb-cite-title';
  title.textContent = '引用来源：';
  container.appendChild(title);
  // 编号与提示词里上下文的 [1]/[2] 一一对应（citations 顺序 == build_context 的枚举顺序）
  citations.forEach((cite, position) => {
    // spec-012：v2 跨页合并片段显示为 p.3-4，单页仍为 p.3
    const startPage = Number(cite.page);
    const endPage = Number(cite.page_end);
    const pageText = endPage > startPage ? `p.${startPage}-${endPage}` : `p.${startPage}`;
    const label = `[${position + 1}] ${cite.file_name} ${pageText}`;
    // 用 button 而非 span：可点击、可 Tab 聚焦、可用键盘展开（无障碍）
    const tag = document.createElement('button');
    tag.type = 'button';
    tag.className = 'kb-cite';
    tag.textContent = label;
    tag.title = '点击展开/收起该片段原文';
    tag.setAttribute('aria-expanded', 'false');

    const detail = document.createElement('div');
    detail.className = 'kb-cite-detail';
    detail.hidden = true;
    // 原文是不可信内容（来自 PDF 抽取），一律 textContent，不解析 Markdown
    detail.textContent = cite.text || '（该片段没有可显示的原文）';

    tag.addEventListener('click', () => {
      const shouldOpen = detail.hidden;
      detail.hidden = !shouldOpen;
      tag.setAttribute('aria-expanded', String(shouldOpen));
      tag.classList.toggle('expanded', shouldOpen);
      if (shouldOpen && kbAnswers) kbAnswers.scrollTop = kbAnswers.scrollHeight;
    });

    const wrap = document.createElement('div');
    wrap.className = 'kb-cite-wrap';
    wrap.append(tag, detail);
    container.appendChild(wrap);
  });
}

if (kbForm) {
  kbForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const question = (kbQuestion.value || '').trim();
    if (!question || kbSend.disabled) return;
    // 先清空再开流，避免 await 之前的异常路径里残留文字
    kbQuestion.value = '';
    const userBubble = appendKbMessage('user');
    userBubble.textContent = question;
    kbSend.disabled = true;
    kbSend.textContent = '检索中…';

    const answer = appendKbMessage('assistant');
    // 用 div 承载：渲染后可能包含 p/pre/table 等块级元素
    const text = document.createElement('div');
    text.className = 'kb-answer';
    const citations = document.createElement('div');
    citations.className = 'kb-citations';
    answer.append(text, citations);
    const writer = createMarkdownWriter(text, kbAnswers);

    try {
      const response = await fetch('/api/kb/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question,
          model: kbModelSelect ? kbModelSelect.value : activeModel,
          top_k: 5,
          // spec-012：切分版本每次提问时选择，默认 v1
          chunker: kbChunkerSelect ? kbChunkerSelect.value : 'v1',
        }),
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || '请求失败');
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split('\n\n');
        buffer = events.pop();
        for (const event of events) {
          const line = event.split('\n').find((item) => item.startsWith('data: '));
          if (!line) continue;
          const payload = JSON.parse(line.slice(6));
          if (payload.type === 'token') {
            writer.write(payload.content);
          } else if (payload.type === 'citations') {
            renderKbCitations(citations, payload.citations);
          } else if (payload.type === 'error') {
            throw new Error(payload.message || payload.detail || '请求失败');
          }
        }
      }
    } catch (error) {
      writer.cancel(); // 出错后停止渲染，错误信息以纯文本覆盖
      text.textContent = `检索/生成失败：${error.message}`;
    } finally {
      writer.flush(); // 收尾补渲染最后一次节流遗漏的内容
      kbSend.disabled = false;
      kbSend.textContent = '发送';
      kbAnswers.scrollTop = kbAnswers.scrollHeight;
    }
  });
}

if (kbQuestion && kbForm) {
  onEnterKey(kbQuestion, (event) => {
    if (event.shiftKey) return;
    event.preventDefault();
    kbForm.requestSubmit();
  });
}
