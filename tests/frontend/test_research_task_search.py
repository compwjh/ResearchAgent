"""Static contracts for the research task search entry (D1-B direct lookup / D2 filter / D3 copy).

Pure filtering behaviour is exercised by ``test_research_task_search.js``; this
file locks the DOM ids, asset versions and safe-rendering boundaries that the
browser E2E (task-05) relies on.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
RESEARCH = (ROOT / "frontend/research-tasks.js").read_text(encoding="utf-8")


def test_search_dom_ids_are_stable_for_e2e() -> None:
    for element_id in (
        "research-task-search",
        "research-task-search-bar",
        "research-task-search-count",
        "research-task-search-status",
        "research-task-search-empty",
        "research-task-search-retry",
    ):
        assert f'id="{element_id}"' in INDEX
    assert 'type="search"' in INDEX
    assert 'maxlength="128"' in INDEX
    assert 'placeholder="按目标 / ID 搜索研究任务"' in INDEX


def test_no_innerhtml_and_safe_text_boundaries() -> None:
    assert "innerHTML" not in RESEARCH
    assert "textContent" in RESEARCH
    assert ".value" in RESEARCH
    assert "replaceChildren()" in RESEARCH


def test_live_tag_bumped_and_legacy_marker_retained() -> None:
    assert 'src="/assets/research-tasks.js?v=22"' in INDEX
    assert "/assets/research-tasks.js?v=21" in INDEX  # compatibility marker for the prior contract
    assert 'href="/assets/styles.css?v=70"' in INDEX  # untouched this round
    assert 'src="/assets/app.js?v=72"' in INDEX  # untouched this round


def test_session_list_literal_and_reverse_lookup_template_are_preserved() -> None:
    assert "requestJson('/api/research-sessions?limit=100')" in RESEARCH
    assert "requestJson('/api/research-tasks'" not in RESEARCH
    assert "/api/research-tasks/${encodeURIComponent(taskId)}" in RESEARCH


def test_filter_state_and_pure_function_are_wired() -> None:
    for marker in (
        "state.taskQuery",
        "state.taskIdLookup",
        "state.taskSearchCount",
        "filterSessionsByQuery",
        "taskQueryHaystack",
        "normalizeTaskQuery",
        "TASK_QUERY_MAX_LENGTH = 128",
        "/^[0-9a-f]{32}$/",
        "research_task_id",
        "research_session_id",
        "goal_excerpt",
        "created_at",
        ".includes(",
        "renderTaskSearchCount",
        "bindTaskSearch",
        "${matched}/${total}",
    ):
        assert marker in RESEARCH


def test_debounce_and_race_guard_are_present() -> None:
    assert "250" in RESEARCH
    for marker in (
        "taskSearchDebounceTimer",
        "requestSeq",
        "isCurrentLookupRequest",
        "applyTaskIdLookupResult",
        "startTaskIdLookup",
    ):
        assert marker in RESEARCH


def test_direct_lookup_layer_distinguishes_404_network_and_keeps_list() -> None:
    for marker in (
        "TASK_NOT_FOUND",
        "未找到该任务",
        "定位失败，请重试",
        "正在按 ID 定位任务",
        "已定位并选中历史任务",
        "无匹配结果",
        "research-task-search-retry",
    ):
        assert marker in RESEARCH
    start = RESEARCH.index("async function runTaskIdLookup")
    end = RESEARCH.index("function bindTaskSearch", start)
    lookup_layer = RESEARCH[start:end]
    assert "requestJson(`/api/research-tasks/${encodeURIComponent(taskId)}`)" in lookup_layer
    assert "404" in lookup_layer
    assert "TASK_NOT_FOUND" in lookup_layer
    assert "isCurrentLookupRequest" in lookup_layer
    assert "await selectTask(taskId, sid)" in lookup_layer
    assert "renderTaskList()" not in lookup_layer  # the list stays as-is during a direct lookup


def test_card_shows_and_copies_full_task_id() -> None:
    for marker in (
        "任务 ID：",
        "复制任务 ID",
        "dataset.copyTaskId",
        "navigator?.clipboard",
        "writeText",
        "复制失败，请手动复制",
        "createElement('button')",
    ):
        assert marker in RESEARCH
