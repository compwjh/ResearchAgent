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

// 模型库/知识库视图：导航切换 + 列表渲染（spec 006 / spec 011）
function showView(view) {
  const isChat = view === 'chat';
  document.querySelector('#chat').hidden = !isChat;
  document.querySelector('#models-view').hidden = view !== 'models';
  document.querySelector('#kb-view').hidden = view !== 'kb';
  document.querySelectorAll('.nav-item').forEach((item) => {
    item.classList.toggle('active', item.dataset.view === view);
  });
  if (view === 'kb') {
    loadKbPapers();
    loadKbHealth();
  }
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
    kbHealth.textContent = `Qdrant ${data.qdrant ? '就绪' : '不可用'} · Embedding ${data.embedding ? '就绪' : '不可用'} · 重排 ${data.reranker ? '启用' : '未启用（RRF 直出）'} · ${data.chunks ?? 0} 个片段 · v2 结构分析 ${v2llm.available ? '就绪' : '不可用（将降级为规则切分）'}`;
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

