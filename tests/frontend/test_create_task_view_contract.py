"""任务 P：创建研究会话成功后必须「留在深度研究视图」契约（TDD / RED → GREEN）。

覆盖：
  - createTask 成功路径不再调用会切到聊天视图 / 隐藏 #research-view 的
    openConversationFromResearch，改为后台关联会话；
  - 创建成功后仍切回「研究任务」tab、渲染列表并选中新任务；
  - 后台关联保留 `#research-view` hash 与会话 URL，且显式 showView() 保证可见；
  - 真实行为探针（test_create_task_view_contract.js）在 fake DOM 上断言
    `#research-view` 未被隐藏且新任务被选中。
"""
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = (ROOT / "frontend/research-tasks.js").read_text(encoding="utf-8")
HARNESS = Path(__file__).resolve().parent / "test_create_task_view_contract.js"


def _create_fn() -> str:
    return RESEARCH[RESEARCH.index("async function createTask"):RESEARCH.index("function cancelTask")]


def _association_helper() -> str:
    return RESEARCH[
        RESEARCH.index("function associateConversationInBackground"):
        RESEARCH.index("function bindModeGuard")
    ]


def test_create_task_does_not_navigate_into_chat_view():
    """创建成功不得再走 openConversationFromResearch（它会 showView('chat') + 隐藏研究视图）。"""
    fn = _create_fn()
    assert "openConversationFromResearch(conversationId)" not in fn, (
        "创建成功后不得调用 openConversationFromResearch：它会切到聊天视图并隐藏 #research-view"
    )
    assert "associateConversationInBackground(conversationId)" in fn, (
        "创建成功后须改为后台关联会话语义"
    )


def test_create_task_keeps_task_tab_list_and_new_selection():
    """创建成功后仍在深度研究视图：切回 tasks tab、渲染列表、选中新任务。"""
    fn = _create_fn()
    assert "activateResearchTab('tasks')" in fn, "必须切回「研究任务」tab"
    assert "renderTaskList()" in fn, "必须渲染任务列表使新卡片可见"
    assert "selectTask(projected.research_task_id, projected.research_session_id)" in fn, (
        "必须选中新任务使详情可见"
    )


def test_background_association_keeps_research_view_visible():
    """后台关联须保留 #research-view hash（history guard 不隐藏）并显式 showView()。"""
    helper = _association_helper()
    assert "#research-view" in helper, "会话 URL 必须带 #research-view hash，避免 guardedHistoryMethod 隐藏视图"
    assert "state.conversationId = conversationId" in helper, "须保留会话关联语义"
    assert "showView()" in helper, "须显式重新显示研究视图"
    assert "root.openConversation" not in helper, "后台关联不得切到 app.js 的聊天视图"
    assert ".innerHTML" not in helper, "新增代码零 innerHTML"


def test_background_association_refreshes_current_conversation():
    """任务 V / M1：创建后「当前会话」指示须刷新，复用既有 conversationFromUrl()。"""
    helper = _association_helper()
    assert "conversationFromUrl()" in helper, (
        "后台关联须复用既有 conversationFromUrl() 刷新 #research-current-conversation"
    )
    assert "setText('research-current-conversation'" not in helper, (
        "不得在后台关联里重复实现「当前会话」文案渲染（DRY）"
    )


def test_open_conversation_from_research_still_exists_for_explicit_button():
    """「打开对应会话」按钮的用户主动跳转语义不得丢失。"""
    assert "function openConversationFromResearch" in RESEARCH
    assert "openConversationFromResearch(open.dataset.conversationId)" in RESEARCH


def test_create_task_behavior_harness_passes():
    node = shutil.which("node")
    if not node:
        import pytest
        pytest.skip("node executable not found on PATH")
    assert HARNESS.exists()
    env = dict(os.environ)
    env.setdefault("NODE_OPTIONS", "")
    result = subprocess.run(
        [node, str(HARNESS)], cwd=str(ROOT), capture_output=True, text=True, timeout=120, env=env,
    )
    assert result.returncode == 0, (
        "create task view harness 失败：\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    assert "ok - create task stays in research view contract" in result.stdout, result.stdout
