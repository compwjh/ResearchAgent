"""Static contracts for post-approval guidance in the conversation UI."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def test_approve_plan_explains_queue_and_follow_up_stages() -> None:
    assert "showConversationResearchNextStep" in APP
    assert "计划已批准，研究任务已创建并进入队列" in APP
    assert "自动检索论文、评估候选并生成报告" in APP
    assert "查看研究进度" in APP
    assert "panel.dataset.status = result?.status || 'queued'" in APP


def test_approval_success_disables_the_other_decision() -> None:
    assert "controls.querySelectorAll('button').forEach" in APP
    assert "status.textContent = approveCommand === 'approve_plan' ? '已批准'" in APP
    assert "if (pending) card.appendChild(controls)" in APP
    assert "approved: '已批准'" in APP
    assert "approved: '已批准'" in (ROOT / "frontend/research-tasks.js").read_text(encoding="utf-8")


def test_approval_guidance_uses_accessible_scoped_dom_and_cache_bump() -> None:
    assert "conversation-research-next-step" in STYLES
    assert "role', 'status" in APP
    assert 'href="/assets/styles.css?v=53"' in INDEX
    assert 'src="/assets/app.js?v=53"' in INDEX
