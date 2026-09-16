/* Spec034 Task09: canonical, read-only Session projection shared by chat and
 * Research Tab.  It contains no transport or mutable UI state. */
(function exposeResearchSessionUI(root, factory) {
  const api = factory();
  if (root) root.ResearchSessionUI = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function researchSessionUIFactory() {
  const TERMINAL = new Set(['partial', 'completed', 'failed', 'cancelled', 'interrupted']);
  const PHASES = {
    intake_pending: 'Intake', plan_generating: 'Plan', plan_pending_approval: 'Plan/Approval',
    queued: 'Queued', running: 'Research execution', waiting_approval: 'Approval',
    partial: 'Report', completed: 'Report', failed: 'Report', cancelled: 'Cancelled', interrupted: 'Interrupted',
  };
  const scalar = (value, fallback = '') => value === null || value === undefined || value === '' ? fallback : String(value);
  const finiteNumber = (value) => Number.isFinite(Number(value)) ? Number(value) : null;
  function jsonList(value) {
    if (Array.isArray(value)) return value;
    if (typeof value !== 'string') return [];
    try { const parsed = JSON.parse(value); return Array.isArray(parsed) ? parsed : []; } catch (_) { return []; }
  }
  function uniqueNamedValues(values) {
    const names = values.map((item) => {
      if (typeof item === 'string' || typeof item === 'number') return String(item).trim();
      if (!item || typeof item !== 'object' || Array.isArray(item)) return '';
      return String(item.name || item.tool_name || item.agent || item.role || item.id || '').trim();
    }).filter(Boolean);
    return new Set(names).size;
  }
  function projectSession(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
    const task = [value.task, value.research_task, value.task_summary].find((item) => item && typeof item === 'object' && !Array.isArray(item)) || {};
    const id = scalar(value.research_session_id || value.session_id || task.research_session_id);
    const taskId = scalar(value.research_task_id || task.research_task_id);
    if (!id && !taskId) return null;
    // The Task is the execution source of truth. A worker can finish between
    // the Task and Session commits, so a terminal Task must win over a stale
    // queued Session projection.
    const sessionStatus = scalar(value.status, '');
    const taskStatus = scalar(task.status, '');
    const status = scalar(TERMINAL.has(taskStatus) ? taskStatus : (sessionStatus || taskStatus), 'intake_pending');
    const approvals = Array.isArray(value.approvals) ? value.approvals : Array.isArray(task.approvals) ? task.approvals : [];
    const pending = approvals.find((item) => item?.status === 'pending');
    const approval = value.approval_status || value.waiting_approval || value.pending_approval || pending || task.approval_status || '';
    const conversation = value.conversation && typeof value.conversation === 'object' ? value.conversation : {};
    const plan = [value.plan, value.session_plan, task.plan, task.session_plan]
      .find((item) => item && typeof item === 'object' && !Array.isArray(item)) || {};
    const progress = value.progress_percent ?? value.progress ?? task.progress_percent ?? task.progress ?? (TERMINAL.has(status) ? 100 : status === 'queued' ? 0 : null);
    const phase = value.current_phase || value.phase || value.stage || task.current_phase || task.phase || task.stage || PHASES[status] || status;
    const conversationTitle = scalar(conversation.title);
    const title = conversationTitle || value.title || value.topic || task.topic || task.goal_excerpt || '深度研究';
    let summary = value.agent_tool_summary || value.execution_summary || task.agent_tool_summary || task.execution_summary || '';
    if (!summary) {
      const workItems = jsonList(value.work_items || value.work_items_json || task.work_items || task.work_items_json || plan.work_items || plan.work_items_json);
      const capabilities = jsonList(value.capabilities || value.capabilities_json || task.capabilities || task.capabilities_json || plan.capabilities || plan.capabilities_json);
      const agents = uniqueNamedValues(workItems.map((item) => item && (item.role || item.agent || item.agent_name)));
      const tools = uniqueNamedValues(capabilities.flatMap((item) => Array.isArray(item?.tools) ? item.tools : []));
      if (agents || tools) summary = { agents, tools };
    }
    return {
      ...task, ...value,
      research_session_id: id || null, research_task_id: taskId || null,
      session_id: id || null, conversation_id: value.conversation_id || conversation.conversation_id || task.conversation_id || null,
      project_id: value.project_id ?? conversation.project_id ?? task.project_id ?? null,
      title, topic: value.topic || task.topic || title, goal_excerpt: conversationTitle || value.goal_excerpt || title,
      status, current_phase: phase, progress, progress_percent: finiteNumber(progress),
      approval_status: approval, approvals, agent_tool_summary: summary,
      plan: value.plan || value.session_plan || task.plan || task.session_plan || null,
      session_approvals: approvals, research_session: value,
      created_at: value.created_at || task.created_at || '', updated_at: value.updated_at || task.updated_at || '',
      started_at: value.started_at || task.started_at || '', completed_at: value.completed_at || task.completed_at || '',
      duration_ms: value.duration_ms ?? task.duration_ms,
    };
  }
  function planField(plan, key) {
    if (!plan || typeof plan !== 'object') return null;
    if (key === 'safety_summary' && plan.safe_summary !== undefined) return plan.safe_summary;
    if (plan[key] !== undefined) return plan[key];
    const raw = plan[`${key}_json`];
    if (typeof raw !== 'string') return raw;
    try { return JSON.parse(raw); } catch (_) { return null; }
  }
  function durationText(item) {
    const duration = Number(item?.duration_ms);
    if (Number.isFinite(duration) && duration >= 0) return `${(duration / 1000).toFixed(duration >= 10000 ? 0 : 1)} 秒`;
    const start = Date.parse(item?.started_at || item?.created_at || '');
    const end = Date.parse(item?.completed_at || item?.updated_at || '');
    if (Number.isFinite(start) && Number.isFinite(end) && end >= start) return `${((end - start) / 1000).toFixed((end - start) >= 10000 ? 0 : 1)} 秒`;
    return '—';
  }
  function progressText(item) {
    const raw = finiteNumber(item?.progress_percent ?? item?.progress);
    if (raw === null) return '进度：—';
    return `进度：${Math.max(0, Math.min(100, Math.round(raw <= 1 ? raw * 100 : raw)))}%`;
  }
  function approvalText(item) {
    const approval = item?.approval_status;
    if (!approval) return '审批：—';
    const value = typeof approval === 'object' ? scalar(approval.status || approval.kind, '待处理') : scalar(approval);
    const labels = { pending: '待处理', approved: '已批准', rejected: '已拒绝', declined: '已拒绝' };
    return `审批：${typeof approval === 'object' ? (labels[value] || value) : value}`;
  }
  function agentToolText(item) {
    const value = item?.agent_tool_summary;
    if (typeof value === 'string' && value.trim()) return value.length > 180 ? `${value.slice(0, 180)}…` : value;
    if (value && typeof value === 'object') {
      const parts = [];
      const agents = finiteNumber(value.agents ?? value.agent_count); const tools = finiteNumber(value.tools ?? value.tool_count);
      if (agents !== null) parts.push(`Agent ${agents}`); if (tools !== null) parts.push(`Tool ${tools}`);
      if (parts.length) return parts.join(' · ');
    }
    return 'Agent/Tool：—';
  }
  return { TERMINAL, PHASES, projectSession, planField, durationText, progressText, approvalText, agentToolText };
}));
