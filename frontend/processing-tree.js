/* Spec034 Task07: shared, safe ProcessingStep v1/v2 tree renderer. */
(function exposeProcessingTree(root, factory) {
  const api = factory(root);
  if (root) root.ProcessingTree = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function processingTreeFactory(root) {
  const NODE_TYPES = new Set(['phase', 'agent', 'work_item', 'skill', 'tool', 'operation']);
  const TERMINAL = new Set(['completed', 'failed', 'partial', 'cancelled', 'canceled', 'skipped', 'interrupted']);
  const TYPE_LABELS = { phase: '阶段', agent: 'Agent', work_item: 'WorkItem', skill: 'Skill', tool: 'Tool', operation: '步骤' };
  const STATUS_LABELS = { running: '进行中', completed: '已完成', failed: '失败', partial: '部分完成', cancelled: '已取消', canceled: '已取消', skipped: '已跳过', interrupted: '已中断' };

  function scalar(value, fallback = '') {
    if (value === null || value === undefined) return fallback;
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
    return fallback;
  }

  function normalizeStep(value) {
    const input = value && typeof value === 'object' && value.step && typeof value.step === 'object' ? value.step : value;
    if (!input || typeof input !== 'object') return null;
    const nodeType = scalar(input.node_type || input.kind, 'operation').toLowerCase();
    const rawStatus = scalar(input.status, 'running').toLowerCase();
    const status = { done: 'completed', success: 'completed', error: 'failed', canceled: 'cancelled' }[rawStatus] || rawStatus;
    const stepId = scalar(input.step_id || input.id);
    const nodeKey = scalar(input.node_key);
    const sourceEventId = scalar(input.source_event_id || input.sourceEventId);
    const identity = sourceEventId || nodeKey || stepId;
    if (!identity) return null;
    return {
      ...input,
      schema_version: Number.isFinite(Number(input.schema_version)) ? Number(input.schema_version) : 1,
      step_id: stepId,
      node_type: NODE_TYPES.has(nodeType) ? nodeType : 'operation',
      node_key: nodeKey || identity,
      source_event_id: sourceEventId,
      parent_step_id: scalar(input.parent_step_id || input.parentStepId),
      label: scalar(input.label || input.name || input.kind, TYPE_LABELS[nodeType] || '处理步骤'),
      summary: scalar(input.summary || input.detail || input.message),
      status: STATUS_LABELS[status] ? status : 'running',
      display_order: Number.isFinite(Number(input.display_order ?? input.logical_sequence)) ? Number(input.display_order ?? input.logical_sequence) : null,
      duration_ms: Number.isFinite(Number(input.duration_ms)) ? Number(input.duration_ms) : null,
      started_at: scalar(input.started_at),
      completed_at: scalar(input.completed_at),
      _identity: identity,
    };
  }

  function durationText(node) {
    let duration = node.duration_ms;
    if (!Number.isFinite(duration) && node.started_at && node.completed_at) {
      const start = Date.parse(node.started_at); const end = Date.parse(node.completed_at);
      if (Number.isFinite(start) && Number.isFinite(end) && end >= start) duration = end - start;
    }
    if (!Number.isFinite(duration) || duration < 0) return '';
    return `${(duration / 1000).toFixed(duration >= 10000 ? 0 : 1)} 秒`;
  }

  function safeStore(storage) {
    if (storage && typeof storage.getItem === 'function') return storage;
    try { return root?.localStorage || null; } catch (_) { return null; }
  }

  function createProcessingTree({ document, container, storageKey = 'conversation', storage = null, onChange = null } = {}) {
    if (!document || !container) return null;
    const store = safeStore(storage);
    const key = `processing-tree:${scalar(storageKey, 'conversation')}`;
    const state = { nodes: new Map(), aliases: new Map(), expanded: new Map(), syncing: false, status: 'running', userScrolled: false, nextOrdinal: 0 };
    try {
      const saved = JSON.parse(store?.getItem(key) || '{}');
      if (saved && typeof saved === 'object') Object.entries(saved).forEach(([id, value]) => { if (typeof value === 'boolean') state.expanded.set(id, value); });
    } catch (_) { /* private browsing/localStorage corruption: use memory state */ }

    function persist() {
      try { store?.setItem(key, JSON.stringify(Object.fromEntries(state.expanded))); } catch (_) { /* storage is optional */ }
    }
    function identityFor(node) { return node.source_event_id || node.node_key || node.step_id || node._identity; }
    function findNode(node) {
      const ids = [node.source_event_id, node.node_key, node.step_id].filter(Boolean);
      for (const id of ids) { const mapped = state.aliases.get(id); if (mapped && state.nodes.has(mapped)) return state.nodes.get(mapped); }
      return null;
    }
    function scrollContainer() {
      let node = container;
      while (node) {
        if (node.id === 'messages' || node.id === 'research-events-content' || node.classList?.contains?.('research-column-body') || node.classList?.contains?.('research-timeline')) return node;
        node = node.parentNode;
      }
      return container.closest?.('.conversation-processing, .research-timeline') || container;
    }
    function atBottom() {
      const scroll = scrollContainer();
      return scroll.scrollHeight <= scroll.clientHeight + scroll.scrollTop + 24;
    }
    function saveScroll() {
      const scroll = scrollContainer();
      return { node: scroll, top: scroll.scrollTop, bottom: atBottom() };
    }
    function childMap() {
      const children = new Map();
      const sortNodes = (a, b) => {
        const aOrder = Number.isFinite(a.display_order) ? a.display_order : Number.POSITIVE_INFINITY;
        const bOrder = Number.isFinite(b.display_order) ? b.display_order : Number.POSITIVE_INFINITY;
        return (aOrder - bOrder) || ((a._ordinal || 0) - (b._ordinal || 0));
      };
      state.nodes.forEach((node) => {
        const parent = node.parent_step_id;
        if (!parent || !state.nodes.has(parent) && !state.aliases.has(parent)) return;
        const parentId = state.aliases.get(parent) || parent;
        const list = children.get(parentId) || []; list.push(node); children.set(parentId, list);
      });
      children.forEach((list) => list.sort(sortNodes));
      return children;
    }
    function roots() {
      // Keep an out-of-order child in the in-memory adjacency cache.  It is
      // intentionally not rendered as a fake root before its parent arrives.
      return [...state.nodes.values()].filter((node) => !node.parent_step_id).sort((a, b) => {
        const aOrder = Number.isFinite(a.display_order) ? a.display_order : Number.POSITIVE_INFINITY;
        const bOrder = Number.isFinite(b.display_order) ? b.display_order : Number.POSITIVE_INFINITY;
        return (aOrder - bOrder) || ((a._ordinal || 0) - (b._ordinal || 0));
      });
    }
    function nodeDepth(node, parentById) {
      let depth = 0; let current = node; const seen = new Set();
      while (current?.parent_step_id && !seen.has(current._identity)) {
        seen.add(current._identity); const parentId = state.aliases.get(current.parent_step_id) || current.parent_step_id;
        current = parentById.get(parentId); if (current) depth += 1; else break;
      }
      return depth;
    }
    function hasRunningPath(node, children, depth = 0) {
      if (node.status === 'running') return true;
      if (depth >= 3) return false;
      return (children.get(node._identity) || []).some((child) => hasRunningPath(child, children, depth + 1));
    }
    function shouldExpand(node, depth, children) {
      const childrenForNode = children.get(node._identity) || [];
      if (!childrenForNode.length) return false;
      if (node.status === 'failed' || hasRunningPath(node, children)) return true;
      if (state.expanded.has(node._identity)) return state.expanded.get(node._identity);
      // A completed phase remains open to level two; third-level leaves are collapsed.
      if (node.node_type === 'phase' && TERMINAL.has(node.status)) return true;
      return depth < 2 && node.status === 'running';
    }
    function makeNode(node, children, parentById, depth, ancestorExpanded = true, path = new Set()) {
      if (path.has(node._identity)) return null;
      const nextPath = new Set(path); nextPath.add(node._identity);
      const item = document.createElement('div'); item.className = 'conversation-processing-node';
      item.dataset.nodeKey = node.node_key; item.dataset.stepId = node.step_id; item.dataset.nodeType = node.node_type; item.dataset.status = node.status;
      item.dataset.depth = String(depth);
      // The backend rejects depth four; keep the UI defensive if an old or
      // malformed stream still contains one (Phase is depth 0).
      const descendants = depth >= 2 ? [] : (children.get(node._identity) || []);
      const expanded = shouldExpand(node, depth, children);
      const head = document.createElement('div'); head.className = 'conversation-processing-node-head';
      const button = document.createElement('button'); button.type = 'button'; button.className = 'conversation-processing-node-toggle';
      button.setAttribute('aria-expanded', expanded ? 'true' : 'false'); button.setAttribute('aria-label', `${expanded ? '折叠' : '展开'}${node.label}`);
      if (!descendants.length) button.setAttribute('aria-disabled', 'true');
      button.dataset.userToggled = state.expanded.has(node._identity) ? 'true' : 'false';
      const title = document.createElement('span'); title.className = 'conversation-processing-node-label'; title.textContent = node.label;
      const type = document.createElement('span'); type.className = 'conversation-processing-node-type'; type.textContent = TYPE_LABELS[node.node_type] || TYPE_LABELS.operation;
      button.append(title, type); head.appendChild(button);
      const status = document.createElement('span'); status.className = 'conversation-processing-node-status'; status.textContent = STATUS_LABELS[node.status] || STATUS_LABELS.running; head.appendChild(status);
      const detail = document.createElement('span'); detail.className = 'conversation-processing-node-summary'; detail.textContent = [node.summary, durationText(node)].filter(Boolean).join(' · ');
      const body = document.createElement('div'); body.className = 'conversation-processing-node-children'; body.hidden = !expanded || !ancestorExpanded;
      button.addEventListener('click', () => {
        if (!descendants.length) return;
        const next = button.getAttribute('aria-expanded') !== 'true'; button.setAttribute('aria-expanded', next ? 'true' : 'false');
        button.setAttribute('aria-label', `${next ? '折叠' : '展开'}${node.label}`); button.dataset.userToggled = 'true'; state.expanded.set(node._identity, next); persist(); render(); onChange?.('toggle', node);
      });
      item.append(head, detail);
      if (descendants.length) {
        item.appendChild(body);
        descendants.forEach((child) => { const childNode = makeNode(child, children, parentById, depth + 1, ancestorExpanded && expanded, nextPath); if (childNode) body.appendChild(childNode); });
      }
      return item;
    }
    function render() {
      const scroll = saveScroll(); const children = childMap(); const byId = new Map([...state.nodes.values()].map((node) => [node._identity, node]));
      const tree = document.createElement('div'); tree.className = 'conversation-processing-tree'; tree.dataset.status = state.syncing ? 'trace_syncing' : state.status;
      roots().forEach((node) => tree.appendChild(makeNode(node, children, byId, nodeDepth(node, byId), true)));
      if (state.syncing) { const notice = document.createElement('p'); notice.className = 'conversation-processing-syncing'; notice.textContent = '轨迹同步中，研究结果已保留。'; tree.appendChild(notice); }
      if (!state.nodes.size && !state.syncing) { const empty = document.createElement('p'); empty.className = 'conversation-processing-empty'; empty.textContent = '暂无处理步骤'; tree.appendChild(empty); }
      container.replaceChildren(tree);
      if (scroll.node) { if (scroll.bottom) scroll.node.scrollTop = scroll.node.scrollHeight; else scroll.node.scrollTop = scroll.top; }
    }
    function upsert(value) {
      const incoming = normalizeStep(value); if (!incoming) return false;
      const current = findNode(incoming); const identity = current?._identity || identityFor(incoming);
      const currentTerminal = current && TERMINAL.has(current.status);
      const incomingTerminal = TERMINAL.has(incoming.status);
      const terminalBarrier = currentTerminal && current.status !== incoming.status;
      const merged = current
        ? { ...current, ...incoming, ...(terminalBarrier ? { status: current.status, summary: current.summary || incoming.summary } : {}), _identity: identity }
        : { ...incoming, _ordinal: state.nextOrdinal++, _identity: identity };
      state.nodes.set(identity, merged);
      [merged.source_event_id, merged.node_key, merged.step_id].filter(Boolean).forEach((id) => state.aliases.set(id, identity));
      if (merged.status === 'failed') state.expanded.set(identity, true);
      state.syncing = false; if (state.status === 'trace_syncing') state.status = 'running'; render(); onChange?.('upsert', merged); return true;
    }
    function upsertMany(values) { (Array.isArray(values) ? values : []).forEach(upsert); return state.nodes.size; }
    function setSyncing(value = true) { state.syncing = Boolean(value); if (state.syncing && !TERMINAL.has(state.status)) state.status = 'trace_syncing'; if (!state.syncing && state.status === 'trace_syncing') state.status = 'running'; render(); onChange?.('syncing'); }
    function finalize(status = 'completed', summary = '') {
      const nextStatus = TERMINAL.has(status) ? status : 'completed';
      if (TERMINAL.has(state.status) && state.status !== nextStatus) return;
      state.status = nextStatus; state.syncing = false;
      state.nodes.forEach((node, identity) => { if (node.status === 'running') state.nodes.set(identity, { ...node, status, summary: summary || node.summary }); });
      render();
    }
    function isRunning() { return [...state.nodes.values()].some((node) => node.status === 'running'); }
    function snapshot() { return [...state.nodes.values()].map(({ _identity, _ordinal, ...node }) => node); }
    render();
    return { upsert, upsertMany, setSyncing, finalize, render, isRunning, snapshot, state };
  }
  return { createProcessingTree, normalizeStep, durationText, NODE_TYPES };
}));
