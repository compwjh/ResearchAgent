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
    activeModel = models.includes(data.model) ? data.model : models[0] || data.model;
    modelSelect.innerHTML = models.length
      ? models.map((model) => `<option value="${model}">${model}</option>`).join('')
      : '<option value="">没有发现模型</option>';
    modelSelect.value = activeModel;
    modelSelect.disabled = models.length === 0;
    document.querySelector('#model-count').textContent = models.length;
    modelLabel.textContent = activeModel;
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
  modelLabel.textContent = activeModel;
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

function renderModelList(models, current) {
  const list = document.querySelector('#model-list');
  const empty = document.querySelector('#model-empty');
  if (!list) return;
  list.innerHTML = '';
  if (models.length === 0 && empty) empty.textContent = '暂无可用模型';
  empty.hidden = models.length > 0;
  for (const name of models) {
    const li = document.createElement('li');
    li.className = `model-item${name === current ? ' current' : ''}`;
    li.innerHTML = '';
    const nameSpan = document.createElement('span');
    nameSpan.className = 'model-name';
    nameSpan.textContent = name;
    const badge = document.createElement('span');
    badge.className = `model-badge${name === current ? ' current' : ''}`;
    badge.textContent = name === current ? '当前' : '可用';
    li.appendChild(nameSpan);
    li.appendChild(badge);
    li.addEventListener('click', () => {
      activeModel = name;
      if (modelSelect) {
        modelSelect.value =  name;
        modelSelect.disabled = false;
      }
      if (modelLabel) modelLabel.textContent = name;
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