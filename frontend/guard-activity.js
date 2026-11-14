/* Spec050 Task04：防护活动与单动作确认界面。
 * 自包含模块，不依赖 app.js 的视图路由；重复调用 mount() 幂等。
 * 所有服务端文本一律用 textContent 写入，不做 innerHTML 拼接。
 */
(function (global) {
  'use strict';

  var ROOT_ID = 'guard-activity-root';
  var STATUS_URL = '/api/guard/status';
  var STREAM_URL = '/api/guard/stream';
  var ACTIONS_URL = '/api/guard/actions';
  var EVENTS_URL = '/api/guard/events';
  var DECISION_URL = '/api/guard/actions/';
  var POLL_MS = 5000;

  // 仅用于 SSE 通道内按 event_id 去重；刷新/轮询仍由服务端权威重建完整列表，不因本地缓存丢事件。
  var streamEventIds = Object.create(null);
  var activeStream = null;
  var activeTimer = null;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function safeText(value, fallback) {
    if (typeof value === 'string' && value.trim()) return value;
    if (typeof value === 'number') return String(value);
    return fallback || '';
  }

  function labelForStatus(status) {
    var known = {
      executed: '已执行', blocked: '已拦截', failed: '失败', skipped: '跳过'
    };
    return known[status] || '未知状态';
  }

  function labelForReason(code) {
    var known = {
      CONFIRMATION_REQUIRED: '需确认',
      TARGET_NOT_ALLOWED: '目标越权',
      CAPABILITY_NOT_ALLOWED: '能力不允许',
      SCOPE_MISSING: '缺少任务范围',
      GUARD_CHECK_UNAVAILABLE: '检测不可用',
      INJECTION_RISK_DETECTED: '检测到注入风险',
      DETECTOR_UNAVAILABLE: '检测器不可用',
      RESULT_UNKNOWN: '结果未知',
      ACTION_CONSUMED: '已执行',
      ACTION_REJECTED: '已拒绝',
      ACTION_CANCELLED: '已取消'
    };
    return known[code] || safeText(code, '未知原因');
  }

  function buildRoot() {
    var existing = document.getElementById(ROOT_ID);
    if (existing) return existing;
    var root = el('section', 'guard-activity');
    root.id = ROOT_ID;
    root.setAttribute('aria-label', '执行防护活动');
    root.hidden = true;

    var toggle = el('button', 'guard-activity-toggle', '防护活动');
    toggle.type = 'button';
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-controls', 'guard-activity-panel');

    var panel = el('div', 'guard-activity-panel');
    panel.id = 'guard-activity-panel';
    panel.hidden = true;

    var header = el('div', 'guard-activity-header');
    header.appendChild(el('h2', 'guard-activity-title', '执行防护活动'));
    var refresh = el('button', 'guard-activity-refresh', '刷新');
    refresh.type = 'button';
    refresh.setAttribute('aria-label', '刷新防护活动');
    header.appendChild(refresh);
    panel.appendChild(header);

    var actions = el('div', 'guard-activity-actions');
    actions.setAttribute('aria-live', 'polite');
    actions.setAttribute('aria-label', '待确认动作');
    panel.appendChild(actions);

    var events = el('div', 'guard-activity-events');
    events.setAttribute('aria-label', '防护事件');
    panel.appendChild(events);

    var toast = el('div', 'guard-activity-toast');
    toast.setAttribute('role', 'status');
    toast.setAttribute('aria-live', 'polite');
    toast.hidden = true;

    var disabled = el('details', 'guard-activity-disabled');
    disabled.appendChild(el('summary', 'guard-activity-disabled-summary', '执行防护未启用'));
    disabled.appendChild(el('p', 'guard-activity-disabled-hint', '执行防护当前未启用，开启后可在此确认动作并查看实时事件。'));
    disabled.hidden = true;

    root.appendChild(toast);
    root.appendChild(toggle);
    root.appendChild(panel);
    root.appendChild(disabled);
    (document.body || document.documentElement).appendChild(root);

    toggle.addEventListener('click', function () {
      panel.hidden = !panel.hidden;
      toggle.setAttribute('aria-expanded', panel.hidden ? 'false' : 'true');
      if (!panel.hidden) refreshAll();
    });
    refresh.addEventListener('click', function () { refreshAll(); });
    return root;
  }

  function actionCard(action) {
    var card = el('article', 'guard-action-card');
    card.setAttribute('data-action-ref', safeText(action.action_ref, ''));
    card.appendChild(el('h3', 'guard-action-title', safeText(action.tool_name, '未知动作')));
    card.appendChild(el('p', 'guard-action-target', safeText(action.target_summary, '目标未提供')));

    var risk = action.risk || {};
    if (risk.requires_hold) {
      var hold = el('p', 'guard-action-risk guard-action-risk-hold', '注入检测不可用，该动作已暂停');
      card.appendChild(hold);
    } else if (Number(risk.label) === 1) {
      card.appendChild(el('p', 'guard-action-risk guard-action-risk-alert', '来源含注入风险，请核对目标后再确认'));
    }
    if (risk.evidence_ref) {
      card.appendChild(el('p', 'guard-action-evidence', '证据定位：' + safeText(risk.evidence_ref, '')));
    }

    var controls = el('div', 'guard-action-controls');
    ['allow', 'reject', 'cancel'].forEach(function (choice) {
      var button = el('button', 'guard-action-' + choice,
        choice === 'allow' ? '允许' : choice === 'reject' ? '拒绝' : '取消');
      button.type = 'button';
      button.setAttribute('data-choice', choice);
      button.addEventListener('click', function () {
        decide(action, choice, button);
      });
      controls.appendChild(button);
    });
    card.appendChild(controls);

    var status = el('p', 'guard-action-status', '');
    status.setAttribute('role', 'status');
    card.appendChild(status);
    return card;
  }

  function decide(action, choice, button) {
    var ref = safeText(action.action_ref, '');
    if (!ref) return;
    button.disabled = true;
    var url = DECISION_URL + encodeURIComponent(ref) + '/decision';
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ choice: choice, args_hash: safeText(action.args_hash, '') })
    }).then(function (response) {
      return response.json().then(function (payload) {
        return { ok: response.ok, payload: payload };
      });
    }).then(function (result) {
      var card = button.closest('.guard-action-card');
      var status = card && card.querySelector('.guard-action-status');
      if (!result.ok) {
        var code = result.payload && result.payload.detail && result.payload.detail.code;
        if (status) status.textContent = '操作未完成：' + labelForReason(code || 'UNKNOWN');
        button.disabled = false;
        return;
      }
      if (status) status.textContent = labelForReason(result.payload.reason_code);
      // 不立即重渲染：否则状态文案会被冲掉、按钮重新可用，用户可能重复确认。
      // 后续轮询/刷新会从服务端重建终态，不从终态倒退。
      Array.prototype.forEach.call(card.querySelectorAll('button'), function (item) {
        item.disabled = true;
      });
    }).catch(function () {
      var card = button.closest('.guard-action-card');
      var status = card && card.querySelector('.guard-action-status');
      if (status) status.textContent = '网络异常，请刷新后重试';
      button.disabled = false;
    });
  }

  function renderActions(actions) {
    var container = document.querySelector('#' + ROOT_ID + ' .guard-activity-actions');
    if (!container) return;
    container.textContent = '';
    if (!Array.isArray(actions) || !actions.length) {
      container.appendChild(el('p', 'guard-activity-empty', '当前没有待确认的动作'));
      return;
    }
    actions.forEach(function (action) {
      container.appendChild(actionCard(action));
    });
  }

  function eventItem(record) {
    var item = el('li', 'guard-activity-event');
    item.setAttribute('data-event-status', labelForStatus(record.status));
    item.appendChild(el('span', 'guard-event-status', labelForStatus(record.status)));
    item.appendChild(el('span', 'guard-event-reason', labelForReason(record.reason_code)));
    item.appendChild(el('span', 'guard-event-module', safeText(record.module, '未知模块')));
    return item;
  }

  function renderEvents(records) {
    var container = document.querySelector('#' + ROOT_ID + ' .guard-activity-events');
    if (!container) return;
    container.textContent = '';
    var title = el('h3', 'guard-activity-subtitle', '最近事件');
    container.appendChild(title);
    if (!Array.isArray(records) || !records.length) {
      container.appendChild(el('p', 'guard-activity-empty', '暂无事件'));
      return;
    }
    var list = el('ul', 'guard-activity-event-list');
    // 仅在本次响应内去重；刷新后从服务端重建完整列表，不因本地缓存而丢失事件。
    var batchIds = Object.create(null);
    records.forEach(function (record) {
      var id = safeText(record.event_id, '');
      if (id) {
        if (batchIds[id]) return;
        batchIds[id] = true;
      }
      list.appendChild(eventItem(record));
    });
    container.appendChild(list);
  }

  // SSE 增量：按 event_id 去重后追加一条 li，不整体重渲染轮询已渲染的列表。
  function appendStreamEvent(record) {
    var container = document.querySelector('#' + ROOT_ID + ' .guard-activity-events');
    if (!container) return;
    var id = safeText(record && record.event_id, '');
    if (id) {
      if (streamEventIds[id]) return;
      streamEventIds[id] = true;
    }
    var list = container.querySelector('.guard-activity-event-list');
    if (!list) {
      // 列表尚未建立（如「暂无事件」占位）：只重建容器骨架，随后继续追加，不覆盖已有数据。
      container.textContent = '';
      container.appendChild(el('h3', 'guard-activity-subtitle', '最近事件'));
      list = el('ul', 'guard-activity-event-list');
      container.appendChild(list);
    }
    list.appendChild(eventItem(record || {}));
  }

  function updateToast(record) {
    var toast = document.querySelector('#' + ROOT_ID + ' .guard-activity-toast');
    if (!toast) return;
    toast.hidden = false;
    toast.textContent = labelForStatus(record.status) + ' · ' + labelForReason(record.reason_code);
  }

  function onGuardEvent(event) {
    var record = null;
    try {
      var payload = JSON.parse(event && event.data);
      record = payload && payload.record;
    } catch (e) { return; }
    if (!record || typeof record !== 'object') return;
    appendStreamEvent(record);
    updateToast(record);
    var root = document.getElementById(ROOT_ID);
    var panel = root && root.querySelector('.guard-activity-panel');
    var actionsBox = root && root.querySelector('.guard-activity-actions');
    var hasPending = actionsBox && actionsBox.querySelector('.guard-action-card');
    if (panel && hasPending) {
      panel.hidden = false;
      var toggle = root.querySelector('.guard-activity-toggle');
      if (toggle) toggle.setAttribute('aria-expanded', 'true');
      refreshAll();
    }
  }

  function fetchJson(url) {
    return fetch(url, { headers: { Accept: 'application/json' } }).then(function (response) {
      if (!response.ok) throw new Error('HTTP ' + response.status);
      return response.json();
    });
  }

  function refreshAll() {
    var root = document.getElementById(ROOT_ID);
    if (!root) return Promise.resolve();
    var actionsBox = root.querySelector('.guard-activity-actions');
    var eventsBox = root.querySelector('.guard-activity-events');
    return Promise.all([
      fetchJson(ACTIONS_URL).catch(function () { return { records: [] }; }),
      fetchJson(EVENTS_URL).catch(function () { return { records: [] }; })
    ]).then(function (results) {
      renderActions(results[0] && results[0].records);
      renderEvents(results[1] && results[1].records);
      if (actionsBox) actionsBox.setAttribute('data-refreshed', 'true');
      if (eventsBox) eventsBox.setAttribute('data-refreshed', 'true');
    });
  }

  function openStream() {
    if (activeStream) return;
    var ES = global.EventSource;
    if (typeof ES !== 'function') return;  // 无 EventSource（旧浏览器/测试假 DOM）安全跳过
    try {
      var source = new ES(STREAM_URL);
      activeStream = source;
      source.addEventListener('guard', onGuardEvent);
      source.onerror = function () {
        // 连接异常：保留 5s 轮询回退，不刷屏报错；EventSource 重连自动携带 Last-Event-ID 增量。
        startPolling();
      };
    } catch (e) {
      activeStream = null;
      startPolling();
    }
  }

  function startPolling() {
    if (activeTimer) return;
    activeTimer = global.setInterval(refreshAll, POLL_MS);
  }

  function stopPolling() {
    if (activeTimer) {
      global.clearInterval(activeTimer);
      activeTimer = null;
    }
  }

  function showDisabled() {
    var root = document.getElementById(ROOT_ID);
    if (!root) return;
    root.hidden = false;  // 可见，让用户能发现功能
    var toggle = root.querySelector('.guard-activity-toggle');
    var panel = root.querySelector('.guard-activity-panel');
    var disabled = root.querySelector('.guard-activity-disabled');
    if (toggle) toggle.hidden = true;
    if (panel) panel.hidden = true;
    if (disabled) disabled.hidden = false;
    // 明确 enabled=false：折叠状态入口，零 SSE / 零轮询 / 零数据请求。
  }

  function activate() {
    var root = document.getElementById(ROOT_ID);
    if (!root) return;
    root.hidden = false;  // P0：真正启用时面板可见
    var toggle = root.querySelector('.guard-activity-toggle');
    var disabled = root.querySelector('.guard-activity-disabled');
    if (toggle) toggle.hidden = false;
    if (disabled) disabled.hidden = true;
    openStream();
    startPolling();
    refreshAll();
  }

  function legacyFallback() {
    // status 失败/字段缺失（旧后端或测试桩）：保持 root 隐藏，退回 5s 轮询，兼容旧行为且不抛异常。
    startPolling();
    refreshAll();
  }

  function mount() {
    var root = buildRoot();
    fetchJson(STATUS_URL).then(function (payload) {
      if (payload && payload.enabled === true) {
        activate();
      } else if (payload && payload.enabled === false) {
        showDisabled();
      } else {
        legacyFallback();
      }
    }).catch(function () {
      legacyFallback();
    });
    return root;
  }

  function resetForTests() {
    stopPolling();
    if (activeStream) {
      activeStream.close();
      activeStream = null;
    }
    streamEventIds = Object.create(null);
  }

  global.GuardActivity = {
    mount: mount,
    refresh: refreshAll,
    renderActions: renderActions,
    renderEvents: renderEvents,
    actionCard: actionCard,
    labelForStatus: labelForStatus,
    labelForReason: labelForReason,
    resetForTests: resetForTests
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount);
  } else {
    mount();
  }
})(typeof window !== 'undefined' ? window : this);
