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
  message.innerHTML = '<div class="avatar">O</div><div class="bubble"><span class="model-tag"></span><span class="answer"></span><span class="debug-tag"></span></div>';
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
          if (eventData.model) assistantMessage = createAssistantMessage(eventData.model);
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
        } else if (eventData.type === 'token' && assistantMessage) {
          assistantMessage.querySelector('.answer').textContent += eventData.content;
          messages.scrollTop = messages.scrollHeight;
        } else if (eventData.type === 'debug' && assistantMessage) {
          const debug = eventData.debug;
          assistantMessage.querySelector('.debug-tag').textContent = `· ${debug.elapsed_ms} ms · ${debug.input_length} chars · node: ${debug.graph_node}`;
        } else if (eventData.type === 'error') {
          throw new Error(eventData.message || eventData.detail || '请求失败');
        }
      }
    }
  } catch (error) {
    addMessage(`连接失败：${error.message}`, 'assistant');
  } finally {
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

input.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); form.requestSubmit(); }
});

// 模型库视图：导航切换 + 列表渲染（spec 006）
function showView(view) {
  const isChat = view === 'chat';
  document.querySelector('#chat').hidden = !isChat;
  document.querySelector('#models-view').hidden = isChat;
  document.querySelectorAll('.nav-item').forEach((item) => {
    item.classList.toggle('active', item.dataset.view === view);
  });
}

document.querySelectorAll('.nav-item').forEach((item) => {
  item.addEventListener('click', (event) => {
    event.preventDefault();
    showView(item.dataset.view);
  });
});

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
    if (event.key === 'Enter') { event.preventDefault(); finish(true); }
    else if (event.key === 'Escape') { event.preventDefault(); finish(false); }
  });
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

