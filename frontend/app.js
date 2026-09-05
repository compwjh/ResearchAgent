const form = document.querySelector('#chat-form');
const input = document.querySelector('#question');
const messages = document.querySelector('#messages');
const sendButton = document.querySelector('#send-button');
const modelLabel = document.querySelector('#model-label');
const statusDot = document.querySelector('.status-dot');
const modeSelect = document.querySelector('#mode-select');
const modelSelect = document.querySelector('#model-select');
const modeHint = document.querySelector('#mode-hint');
const sendLabel = sendButton.innerHTML;
const workspace = document.querySelector('.workspace');
const newChatButton = document.querySelector('.new-chat');
const settingsButton = document.querySelector('#settings-button');
const settingsDialog = document.querySelector('#settings-dialog');
const settingsForm = document.querySelector('#settings-form');
const searchUrls = document.querySelector('#search-urls');
const downloadUrls = document.querySelector('#download-urls');
const downloadDir = document.querySelector('#download-dir');
const settingsStatus = document.querySelector('#settings-status');
let activeModel = 'Ollama';
let currentModels = [];

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
  messages.appendChild(message);
  messages.scrollTop = messages.scrollHeight;
}

function createAssistantMessage(model) {
  const message = document.createElement('div');
  message.className = 'message assistant';
  message.innerHTML = '<div class="avatar">O</div><div class="bubble"><span class="model-tag"></span><div class="answer md-body"></div><span class="debug-tag"></span></div>';
  message.querySelector('.model-tag').textContent = `${model || activeModel}${modeSelect.value === 'developer' ? ' · Developer' : ''}`;
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
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const question = input.value.trim();
  if (!question || sendButton.disabled) return;
  workspace.classList.add('has-started');
  window.currentAgentTaskId = null;
  recommendedCount = 0;
  clearSkillHint();
  addMessage(question, 'user');
  input.value = '';
  sendButton.disabled = true;
  sendButton.innerHTML = '<span class="sending-indicator">•••</span>';
  try {
    const response = await fetch('/api/agent/run', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, mode: modeSelect.value, model: modelSelect.value }),
    });
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.detail || '请求失败');
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let assistantMessage = null;
    let writer = null;
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split('\n\n');
      buffer = events.pop();
      for (const event of events) {
        const line = event.split('\n').find((item) => item.startsWith('data: '));
        if (!line) continue;
        const eventData = JSON.parse(line.slice(6));
        if (eventData.type === 'meta') {
          if (eventData.model) {
            assistantMessage = createAssistantMessage(eventData.model);
            writer = createMarkdownWriter(assistantMessage.querySelector('.answer'), messages);
          }
          window.currentAgentTaskId = eventData.task_id || window.currentAgentTaskId;
        } else if (eventData.type === 'candidate') {
          const confidence = (eventData.candidate.confidence ?? 0);
          if (confidence > 0.5 && recommendedCount < 3) {
            addCandidate(eventData.candidate, window.currentAgentTaskId);
            recommendedCount += 1;
          }
        } else if (eventData.type === 'normalized') {
          modeHint.textContent = `问题已规范化：${eventData.normalized_query}`;
        } else if (eventData.type === 'intent') {
          modeHint.textContent = `识别意图：${eventData.intent} · ${(eventData.confidence * 100).toFixed(0)}%`;
          if (eventData.skill) showSkillHint(eventData.skill);
        } else if (eventData.type === 'result' && eventData.message) {
          addMessage(eventData.message, 'assistant');
        } else if (eventData.type === 'token' && assistantMessage && writer) {
          writer.write(eventData.content);
        } else if (eventData.type === 'debug' && assistantMessage) {
          const debug = eventData.debug;
          assistantMessage.querySelector('.debug-tag').textContent = `· ${debug.elapsed_ms} ms · ${debug.input_length} chars · node: ${debug.graph_node}`;
        } else if (eventData.type === 'error') {
          throw new Error(eventData.message || eventData.detail || '请求失败');
        }
      }
    }
  } catch (error) {
    if (writer) writer.cancel();
    addMessage(`连接失败：${error.message}`, 'assistant');
  } finally {
    if (writer) writer.flush();
    sendButton.disabled = false;
    sendButton.innerHTML = sendLabel;
    input.focus();
  }
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

newChatButton.addEventListener('click', () => {
  workspace.classList.remove('has-started');
  window.currentAgentTaskId = null;
  clearSkillHint();
  messages.innerHTML = '<div class="message assistant"><div class="avatar">O</div><div class="bubble"><span class="model-tag">模型信息加载中</span><span class="answer">你好，我已经准备好了。问我任何问题。</span></div></div>';
  input.value = '';
  input.focus();
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
const paperResultCount = document.querySelector('#paper-result-count');
const paperResults = document.querySelector('#paper-results');
const paperResultsEmpty = document.querySelector('#paper-results-empty');
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
  searchSerial: 0,
  searchController: null,
  conferencesLoaded: false,
  batches: new Map(),
  candidateById: new Map(),
  inFlightImports: new Set(),
  batchPollTimer: null,
  batchPollSerial: 0,
  pendingKbPaperId: null,
};

const PAPER_STATUS_TEXT = {
  queued: '排队中', downloading: '下载中', waiting_login: '等待登录', validating: '校验中',
  indexing: '索引中', completed: '已完成', failed: '失败', cancelled: '已取消',
  partial_success: '部分完成', running: '处理中', completed_count: '已完成',
};
const PAPER_ERROR_TEXT = {
  PAPER_DISCOVERY_DISABLED: '论文检索功能当前已关闭', PAPER_DISCOVERY_UNAVAILABLE: '检索服务暂时不可用',
  PAPER_DISCOVERY_STORE_UNAVAILABLE: '检索配置暂时不可用', SEARCH_EXPIRED: '搜索会话已过期，请重新检索',
  SEARCH_NOT_FOUND: '搜索会话不存在，请重新检索', CANDIDATE_NOT_FOUND: '候选论文不存在，请重新检索',
  INVALID_QUERY: '研究方向不能为空且最多 500 个字符', INVALID_YEARS: '发表年份范围无效',
  INVALID_CONFERENCE: '请选择已启用的会议', CONFERENCE_DISABLED: '所选会议已停用',
  CONFERENCE_NOT_CONFIGURED: '会议配置不存在', BATCH_LIMIT_EXCEEDED: '单批最多导入 20 篇',
  BROWSER_SESSION_REQUIRED: '请先完成受控登录后再续传', BROWSER_UNAVAILABLE: '浏览器当前不可用',
  BROWSER_ORIGIN_NOT_ALLOWED: '该论文不支持受控登录', IMPORT_BATCH_UNAVAILABLE: '导入服务暂时不可用',
  IMPORT_BATCH_ERROR: '导入批次失败', PAPER_ALREADY_EXISTS: '论文已在知识库中', LOGIN_REQUIRED: '需要登录后才能下载',
};

class PaperApiError extends Error {
  constructor(code, retryable = false) {
    super(PAPER_ERROR_TEXT[code] || '论文服务暂时不可用');
    this.code = code || 'PAPER_API_ERROR';
    this.retryable = Boolean(retryable);
  }
}

async function paperJson(response) {
  let data = {};
  try { data = await response.json(); } catch (_) {}
  if (!response.ok) {
    const detail = data && typeof data.detail === 'object' ? data.detail : data;
    throw new PaperApiError(detail?.code || data?.code, detail?.retryable || data?.retryable);
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
  if (!Number.isInteger(from) || !Number.isInteger(to) || from > to || to >= new Date().getFullYear()) return null;
  const years = [];
  for (let year = to; year >= from; year -= 1) years.push(year);
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
    input.checked = selected.size ? selected.has(conference.conference_id) : true;
    input.addEventListener('change', syncPaperConferenceSearchSelection);
    const text = document.createElement('span');
    text.textContent = `${conference.short_name || conference.name || '未命名会议'} · ${conference.name || ''}`;
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

function renderPaperResults(candidates) {
  if (!paperResults) return;
  paperResults.replaceChildren();
  paperState.candidates = candidates.slice();
  paperResultsEmpty.hidden = candidates.length > 0;
  paperResultsEmpty.textContent = candidates.length ? '' : '没有找到符合条件的论文。';
  if (paperResultCount) paperResultCount.textContent = candidates.length ? `${candidates.length} 篇` : '';
  if (paperResultsToolbar) paperResultsToolbar.hidden = candidates.length === 0;
  candidates.forEach((candidate) => {
    const item = document.createElement('li'); item.className = 'paper-result-item';
    const head = document.createElement('div'); head.className = 'paper-result-head';
    const select = document.createElement('input'); select.type = 'checkbox'; select.className = 'paper-result-select';
    select.dataset.candidateId = paperText(candidate.candidate_id, '');
    select.disabled = Boolean(candidate.existing_paper_id);
    select.setAttribute('aria-label', `选择论文：${paperText(candidate.title, '未命名论文')}`);
    select.addEventListener('change', updatePaperSelection);
    const title = document.createElement('h3'); title.className = 'paper-result-title'; title.textContent = paperText(candidate.title, '未命名论文');
    head.append(select, title); item.appendChild(head);
    const meta = document.createElement('p'); meta.className = 'paper-result-meta';
    meta.textContent = [candidate.authors?.join?.(', '), candidate.year, candidate.conference_name, `相关度 ${paperCandidateScore(candidate)}`].filter(Boolean).join(' · ');
    item.appendChild(meta);
    const abstract = document.createElement('p'); abstract.className = 'paper-result-abstract';
    abstract.textContent = candidate.abstract ? candidate.abstract : '摘要暂不可用'; item.appendChild(abstract);
    const status = document.createElement('span'); status.className = 'paper-result-status';
    status.textContent = `PDF：${PAPER_STATUS_TEXT[candidate.pdf_access] || paperText(candidate.pdf_access, '未知')}`; item.appendChild(status);
    const action = document.createElement('button'); action.type = 'button'; action.className = 'secondary-button paper-import-one';
    action.dataset.candidateId = paperText(candidate.candidate_id, '');
    action.disabled = Boolean(candidate.existing_paper_id); action.textContent = candidate.existing_paper_id ? '已在知识库' : '添加到知识库';
    action.addEventListener('click', () => importPaperCandidates([candidate])); item.appendChild(action);
    paperResults.appendChild(item);
  });
  updatePaperSelection();
}

async function searchPapers(event) {
  event?.preventDefault();
  if (!paperState.enabled || paperSearchButton?.disabled) return;
  const query = (paperQuery?.value || '').trim();
  const conferenceIds = paperConferenceList ? [...paperConferenceList.querySelectorAll('input:checked')].map((input) => input.value) : [];
  const years = paperYearList();
  if (!query) { showPaperError('INVALID_QUERY'); return; }
  if (!conferenceIds.length) { showPaperError('INVALID_CONFERENCE'); return; }
  if (!years) { showPaperError('INVALID_YEARS'); return; }
  if (paperState.searchController) paperState.searchController.abort();
  const serial = ++paperState.searchSerial;
  const controller = new AbortController(); paperState.searchController = controller;
  if (paperSearchButton) paperSearchButton.disabled = true;
  if (paperResults) paperResults.setAttribute('aria-busy', 'true');
  if (paperSearchError) paperSearchError.hidden = true;
  if (paperSearchStatus) paperSearchStatus.textContent = '正在检索…';
  try {
    const responses = await Promise.all(conferenceIds.map(async (conference_id) => {
      try {
        const response = await fetch('/api/papers/search', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
          body: JSON.stringify({ query, conference_id, years, limit: 20 }),
        });
        return { data: await paperJson(response), error: null };
      } catch (error) {
        if (error.name === 'AbortError') throw error;
        return { data: null, error };
      }
    }));
    if (serial !== paperState.searchSerial) return;
    paperState.candidateSearchIds.clear(); paperState.searchIds = [];
    const deduplicated = new Set();
    const successful = responses.filter((result) => result.data).map((result) => result.data);
    responses.forEach(({ data }, responseIndex) => {
      if (!data) return;
      if (data.search_id) paperState.searchIds.push(data.search_id);
      (data.candidates || []).forEach((candidate, candidateIndex) => {
        if (!candidate.candidate_id || !data.search_id) return;
        const record = { candidate, responseIndex, candidateIndex, searchId: data.search_id };
        const existingRecords = [...deduplicated].filter((owner) => paperCandidateIdentityMatches(candidate, owner.candidate));
        if (!existingRecords.length) {
          deduplicated.add(record);
          return;
        }
        const winner = [record, ...existingRecords].sort(comparePaperCandidateRecords)[0];
        existingRecords.forEach((owner) => deduplicated.delete(owner));
        deduplicated.add(winner);
      });
    });
    if (!successful.length) throw responses[0]?.error || new PaperApiError('PAPER_DISCOVERY_UNAVAILABLE');
    const rankedRecords = [...deduplicated.values()].sort(comparePaperCandidateRecords);
    const rankedCandidates = rankedRecords.map(({ candidate, searchId }) => {
      paperState.candidateSearchIds.set(candidate.candidate_id, searchId);
      paperState.candidateById.set(candidate.candidate_id, candidate);
      return candidate;
    });
    renderPaperResults(rankedCandidates);
    const degraded = responses.some(({ data, error }) => error || data?.degraded || (data?.warnings || []).length);
    if (paperSearchStatus) paperSearchStatus.textContent = degraded ? '检索完成（部分来源降级）' : '检索完成';
  } catch (error) {
    if (error.name === 'AbortError' || serial !== paperState.searchSerial) return;
    showPaperError(error.code);
  } finally {
    if (serial === paperState.searchSerial) {
      if (paperSearchButton) paperSearchButton.disabled = false;
      if (paperResults) paperResults.setAttribute('aria-busy', 'false');
    }
  }
}

function showPaperError(code) {
  if (paperSearchStatus) paperSearchStatus.textContent = '';
  if (paperSearchError) { paperSearchError.textContent = PAPER_ERROR_TEXT[code] || '论文服务暂时不可用，请稍后重试'; paperSearchError.hidden = false; }
}

async function importPaperCandidates(candidates) {
  if (!paperState.enabled) return;
  const groups = new Map();
  candidates.filter((candidate) => candidate && !candidate.existing_paper_id).forEach((candidate) => {
    const searchId = paperState.candidateSearchIds.get(candidate.candidate_id) || candidate.search_id;
    if (!searchId) return;
    if (!groups.has(searchId)) groups.set(searchId, []);
    groups.get(searchId).push(candidate.candidate_id);
  });
  if (!groups.size) return;
  const created = [];
  try {
    for (const [search_id, candidate_ids] of groups) {
      const importKey = `${search_id}:${candidate_ids.join('|')}`;
      if (paperState.inFlightImports.has(importKey)) continue;
      paperState.inFlightImports.add(importKey);
      try {
        const response = await fetch('/api/papers/imports', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(groups.size === 1 && candidate_ids.length === 1
            ? { search_id, candidate_id: candidate_ids[0] }
            : { search_id, candidate_ids, idempotency_key: paperIdempotencyKey(search_id, candidate_ids) }),
        });
        const data = await paperJson(response);
        if (data.batch_id) {
          paperState.batches.set(data.batch_id, data); created.push(data.batch_id); renderPaperBatch(data);
        } else if (paperImportPanel) {
          paperImportPanel.hidden = false;
          if (paperImportStatus) paperImportStatus.textContent = data.existing ? '论文已在知识库中' : (PAPER_STATUS_TEXT[data.status] || '导入已提交');
          if (data.paper_id) jumpToKnowledgeBase(data.paper_id);
        }
      } finally {
        paperState.inFlightImports.delete(importKey);
      }
    }
    if (created.length) { if (paperImportPanel) paperImportPanel.hidden = false; schedulePaperBatchPoll(); }
  } catch (error) {
    if (paperImportStatus) paperImportStatus.textContent = PAPER_ERROR_TEXT[error.code] || '导入服务暂时不可用';
  }
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
      window.clearInterval(paperState.batchPollTimer); paperState.batchPollTimer = null; return;
    }
    await Promise.all(ids.map(async (batchId) => {
      if (!isCurrentPoll() || paperBatchTerminal(paperState.batches.get(batchId))) return;
      try {
        const response = await fetch(`/api/papers/imports/${encodeURIComponent(batchId)}`);
        const data = await paperJson(response);
        if (!isCurrentPoll()) return;
        paperState.batches.set(batchId, data); renderPaperBatch(data);
      } catch (error) {
        if (isCurrentPoll() && paperImportStatus) paperImportStatus.textContent = PAPER_ERROR_TEXT[error.code] || '导入状态暂时不可用';
      }
    }));
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
  batchContainer.replaceChildren();
  const label = PAPER_STATUS_TEXT[batch.status || batch.state] || '处理中';
  const batchHeader = document.createElement('div'); batchHeader.className = 'paper-import-batch-header';
  const batchTitle = document.createElement('h3'); batchTitle.textContent = `批次 ${batchId} · ${label}`;
  const batchSummary = document.createElement('span'); batchSummary.textContent = `${batch.completed_count || 0}/${batch.total_count || batch.items?.length || 0} 已完成`;
  batchHeader.append(batchTitle, batchSummary); batchContainer.appendChild(batchHeader);
  const batchItems = document.createElement('ul'); batchItems.className = 'paper-import-items'; batchContainer.appendChild(batchItems);
  if (paperImportStatus) paperImportStatus.textContent = `批次 ${label}`;
  if (paperImportSummary) paperImportSummary.textContent = `${paperState.batches.size} 个批次`;
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
    batchItems.appendChild(row);
  });
  const failedItems = (batch.items || []).filter((item) => (item.status || item.state) === 'failed');
  if (failedItems.length) {
    const retry = document.createElement('button'); retry.type = 'button'; retry.className = 'secondary-button'; retry.textContent = '重试失败项';
    retry.addEventListener('click', async () => {
      if (!paperState.enabled) return;
      retry.disabled = true;
      try {
        const response = await fetch(`/api/papers/imports/${encodeURIComponent(batch.batch_id)}/retry`, { method: 'POST' });
        const data = await paperJson(response); paperState.batches.set(data.batch_id, data); renderPaperBatch(data); schedulePaperBatchPoll();
      } catch (error) { if (paperImportStatus) paperImportStatus.textContent = PAPER_ERROR_TEXT[error.code] || '重试暂时不可用'; retry.disabled = false; }
    });
    batchItems.appendChild(retry);
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
if (paperConferenceSearchButton) paperConferenceSearchButton.addEventListener('click', searchPaperConferences);
if (paperManageButton) paperManageButton.addEventListener('click', () => {
  if (!paperState.enabled) return;
  renderManagedConferences(); paperConferenceDialog?.showModal();
});
if (paperConferenceSearch) onEnterKey(paperConferenceSearch, (event) => { event.preventDefault(); searchPaperConferences(); });
// 模型库/知识库视图：导航切换 + 列表渲染（spec 006 / spec 011）
function showView(view) {
  const nextView = view === 'papers' && !paperState.enabled ? 'chat' : view;
  const isChat = nextView === 'chat';
  document.querySelector('#chat').hidden = !isChat;
  document.querySelector('#models-view').hidden = nextView !== 'models';
  document.querySelector('#kb-view').hidden = nextView !== 'kb';
  if (paperView) paperView.hidden = nextView !== 'papers' || !paperState.enabled;
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
  if (nextView === 'papers' && paperState.enabled && !paperState.conferencesLoaded) loadPaperConferences();
}

document.querySelectorAll('.nav-item').forEach((item) => {
  item.addEventListener('click', (event) => {
    event.preventDefault();
    showView(item.dataset.view);
  });
});

showView('chat');

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
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || '上传失败');
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
