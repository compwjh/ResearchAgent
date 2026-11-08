"""Task04 literature-map expansion/recovery contract checks.

The browser cases use the explicitly labelled mock component fixture.  They
exercise DOM/API wiring only; they are not production API acceptance evidence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
MODULE = (ROOT / "frontend/literature-maps.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/literature-maps.css").read_text(encoding="utf-8")
FIXTURE = ROOT / "tests/frontend/fixtures/literature_map_component.html"


def _open_browser_or_skip(playwright):
    try:
        return playwright.chromium.launch(headless=True)
    except Exception as exc:  # pragma: no cover - host dependent
        pytest.skip(f"真实浏览器阻塞，未将静态检查冒充组件通过: {type(exc).__name__}: {exc}")


def test_expansion_contract_uses_versioned_safe_dom_and_frozen_routes() -> None:
    assert "/assets/literature-maps.js?v=46" in INDEX
    assert "/assets/literature-maps.css?v=33" in INDEX
    assert "innerHTML" not in MODULE
    for marker in (
        "/previews",
        "/load-more",
        "pagination",
        "page_size",
        "max_candidates",
        "preview_revision",
        "identity_key",
        "MAX_EXPANSION_POLL_ATTEMPTS",
        "poll_attempts",
        "selected_candidate_ids",
        "expected_revision",
        "MAP_PREVIEW_EXPIRED",
        "重新读取并预览",
        "扩展关联论文",
        "自动读取已暂停",
        "手动刷新状态",
        "引用本文",
        "sortedExpansionCandidates",
        "来源范围待核实",
        "引用数",
        "摘要可用性待核实",
        "/previews/revalidate",
        "/previews/batch-apply",
        "MAX_EXPANSION_BATCH_POLL_ATTEMPTS",
        "analysis-queue/retry",
        "手动刷新批次状态",
        "继续搜索",
        "刷新预览",
        "打开上次预览",
        "/events?after_seq=",
        "next_cursor",
        "MAX_PREVIEW_DISCOVERY_PAGES",
        "游标未前进",
        "cursor?.preview_id",
        "参考文献",
        "引用它的论文",
        "已选择",
        "200",
        "jobs/",
        "stopCurrentJob",
        "retryCurrentJob",
        "removeNode",
        "restoreNode",
        "document_id",
        "已加入知识库",
        "在知识库中查看",
        "sessionStorage",
    ):
        assert marker in MODULE
    for selector in (
        ".literature-map-preview-panel",
        ".literature-map-expansion-tabs",
        ".literature-map-expansion-tab",
        ".literature-map-expansion-candidate",
        ".literature-map-expansion-sort-controls",
        ".literature-map-expansion-scope-note",
        ".literature-map-expansion-candidate-scope",
        ".literature-map-expansion-scope-tag",
        ".literature-map-expansion-batch",
        ".literature-map-preview-candidate",
        ".literature-map-preview-capacity",
        ".literature-map-job-actions",
        ".literature-map-document-link",
    ):
        assert selector in STYLES


def _open_expansion(page) -> None:
    page.locator('[data-map-id="map-fixture"]').click()
    page.locator('[data-node-id="node-a"] circle').click()
    page.get_by_role("button", name="扩展关联论文").click()
    page.wait_for_selector("#literature-map-preview-panel")


def test_component_fixture_shows_one_two_direction_expansion_panel_and_keeps_grouping() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?expansion&palette", wait_until="load")
        _open_expansion(page)

        page.wait_for_function("window.__expansionPreviewBodies?.length === 2")
        bodies = page.evaluate("window.__expansionPreviewBodies")
        assert {body["kind"] for body in bodies} == {"references", "citations"}
        assert {body["node_id"] for body in bodies} == {"node-a"}
        assert all(body["idempotency_key"] for body in bodies)
        assert all(body["pagination"] == {"version": 1, "page_size": 50, "max_candidates": 500} for body in bodies)
        assert len({body["idempotency_key"] for body in bodies}) == 2

        node = page.locator('[data-node-id="node-a"]')
        assert node.get_attribute("data-group-id") == "group-fixture"
        # 分组入口已搬到画布左下角 FAB 浮层；展开后该组行必须可见。
        page.locator('#literature-map-groups-fab').click()
        page.wait_for_selector('#literature-map-groups-popover:not([hidden])')
        assert page.locator(
            '#literature-map-groups-popover .literature-map-group-row[data-group-id="group-fixture"]'
        ).is_visible()
        assert page.locator('#literature-map-groups .literature-map-group-row[data-group-id="group-fixture"]').count() == 0, (
            '旧的左侧分组面板必须已删除'
        )

        refs_tab = page.locator('[role="tab"][data-expansion-kind="references"]')
        citations_tab = page.locator('[role="tab"][data-expansion-kind="citations"]')
        assert refs_tab.get_attribute("aria-selected") == "true"
        assert citations_tab.get_attribute("aria-selected") == "false"
        page.locator('[data-candidate-id="references-candidate-0"] input').check()
        citations_tab.click()
        page.locator('[data-candidate-id="citations-candidate-0"] input').check()
        assert "已选 1/20 个新身份" in page.locator(".literature-map-expansion-capacity").inner_text()
        page.locator('[data-candidate-id="citations-candidate-1"] input').click()
        refs_tab.click()
        page.locator('[data-candidate-id="references-candidate-1"] input').check()
        assert page.locator('[data-candidate-id="references-candidate-0"] input').is_checked()
        assert "已选 3/20 个新身份" in page.locator(".literature-map-expansion-capacity").inner_text()
        assert page.locator('[data-candidate-id="references-candidate-3"] input').is_disabled()
        removed = page.locator('[data-candidate-id="references-candidate-4"]')
        assert removed.locator("input").is_disabled()
        assert removed.get_by_role("button", name="显式恢复").count() == 1

        confirm = page.locator("#literature-map-expansion-apply")
        assert confirm.is_enabled()
        assert "批量确认所选论文" in confirm.inner_text()
        assert page.evaluate("window.__applyBody") is None
        assert page.evaluate("window.__batchApplyBodies") == []
        assert page.locator('[data-node-id="node-a"]').get_attribute("data-group-id") == "group-fixture"
        page.close()
        browser.close()


def test_combined_expansion_limits_twenty_unique_identities_across_tabs() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?expansion", wait_until="load")
        _open_expansion(page)
        page.wait_for_function("window.__expansionPreviewBodies?.length === 2")

        for index in [1, 2, *range(5, 22)]:
            page.locator(f'[data-candidate-id="references-candidate-{index}"] input').check()
        page.locator('[data-candidate-id="references-candidate-0"] input').check()
        assert "已选 20/20 个新身份" in page.locator(".literature-map-expansion-capacity").inner_text()

        page.locator('[role="tab"][data-expansion-kind="citations"]').click()
        page.locator('[data-candidate-id="citations-candidate-0"] input').check()
        assert "已选 20/20 个新身份" in page.locator(".literature-map-expansion-capacity").inner_text()
        page.locator('[data-candidate-id="citations-candidate-1"] input').click()
        assert not page.locator('[data-candidate-id="citations-candidate-1"] input').is_checked()
        assert "已选 20/20 个新身份" in page.locator(".literature-map-expansion-capacity").inner_text()
        page.close()
        browser.close()


def test_expansion_paginates_only_on_click_and_retries_failed_page_explicitly() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?expansion-failed-page", wait_until="load")
        _open_expansion(page)
        page.wait_for_function("window.__expansionPreviewBodies?.length === 2")
        assert page.locator(".literature-map-expansion-pagination").inner_text().count("总量未知") >= 1
        assert "已加载 50 篇" in page.locator(".literature-map-expansion-pagination").inner_text()
        assert page.evaluate("window.__loadMoreBodies") == []

        page.locator("#literature-map-expansion-load-more").click()
        page.wait_for_function("window.__loadMoreBodies?.length === 1")
        first_body = page.evaluate("window.__loadMoreBodies[0]")
        assert first_body["kind"] == "references"
        assert first_body["body"]["expected_preview_revision"] == 1
        assert first_body["body"]["retry_failed"] is False
        assert first_body["body"]["idempotency_key"]
        page.wait_for_function("document.querySelector('.literature-map-expansion-pagination')?.textContent.includes('已加载 100 篇')")

        page.locator('[role="tab"][data-expansion-kind="citations"]').click()
        page.locator("#literature-map-expansion-load-more").click()
        page.wait_for_function("window.__loadMoreBodies?.length === 2")
        assert page.locator(".literature-map-expansion-error").inner_text().strip()
        assert page.locator("#literature-map-expansion-retry-page").is_visible()
        page.wait_for_timeout(250)
        assert len(page.evaluate("window.__loadMoreBodies")) == 2

        page.locator("#literature-map-expansion-retry-page").click()
        page.wait_for_function("window.__loadMoreBodies?.length === 3")
        retry_body = page.evaluate("window.__loadMoreBodies[2]")
        assert retry_body["kind"] == "citations"
        assert retry_body["body"]["retry_failed"] is True
        assert retry_body["body"]["idempotency_key"]
        page.wait_for_function("document.querySelector('.literature-map-expansion-pagination')?.textContent.includes('已加载 100 篇')")
        page.close()
        browser.close()


def test_expansion_keeps_one_side_available_after_failure_and_stops_at_cap() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?expansion-create-citation-fail", wait_until="load")
        _open_expansion(page)
        page.wait_for_function("window.__expansionPreviewBodies?.length === 2")
        assert page.locator('[role="tab"][data-expansion-kind="references"]').is_visible()
        assert page.locator('[data-candidate-id="references-candidate-1"] input').is_enabled()
        page.locator('[data-candidate-id="references-candidate-1"] input').check()
        page.locator('[role="tab"][data-expansion-kind="citations"]').click()
        assert page.locator(".literature-map-expansion-error").is_visible()
        assert "暂时不可用" in page.locator(".literature-map-expansion-error").inner_text()
        page.locator("#literature-map-expansion-retry-create").click()
        page.wait_for_function("window.__expansionPreviewBodies?.length === 3")
        page.locator('[role="tab"][data-expansion-kind="references"]').click()
        assert page.locator('[data-candidate-id="references-candidate-1"] input').is_checked()
        page.close()

        capped = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        capped.goto(f"{FIXTURE.as_uri()}?expansion-capped", wait_until="load")
        _open_expansion(capped)
        capped.wait_for_function("window.__expansionPreviewBodies?.length === 2")
        assert "500" in capped.locator(".literature-map-expansion-pagination").inner_text()
        assert "未穷尽" in capped.locator(".literature-map-expansion-pagination").inner_text()
        assert capped.locator("#literature-map-expansion-load-more").count() == 0
        assert capped.evaluate("window.__loadMoreBodies") == []
        capped.close()
        browser.close()


def test_expansion_stops_stuck_polling_and_restores_the_poll_budget() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?expansion-stuck-loading", wait_until="load")
        _open_expansion(page)
        page.wait_for_function("window.__expansionPreviewBodies?.length === 2")
        page.wait_for_function("window.__expansionPreviewGetCounts.references >= 81 && window.__expansionPreviewGetCounts.citations >= 81", timeout=20000)

        assert page.locator("#literature-map-expansion-refresh-status").inner_text() == "手动刷新状态"
        saved = page.evaluate("""() => JSON.parse(sessionStorage.getItem(
          'literature-map-expansion:owner-fixture:map-fixture:node-a'
        ))""")
        assert saved["sides"]["references"]["poll_attempts"] == 80
        assert saved["sides"]["citations"]["poll_attempts"] == 80
        stopped_counts = page.evaluate("window.__expansionPreviewGetCounts")
        page.wait_for_timeout(30)
        assert page.evaluate("window.__expansionPreviewGetCounts") == stopped_counts

        page.locator("#literature-map-expansion-close").click()
        page.evaluate("window.__requestLog = []")
        page.get_by_role("button", name="扩展关联论文").click()
        page.wait_for_function(
            "counts => window.__expansionPreviewGetCounts.references === counts.references + 1 && window.__expansionPreviewGetCounts.citations === counts.citations + 1",
            arg=stopped_counts,
        )
        reopened_counts = page.evaluate("window.__expansionPreviewGetCounts")
        assert page.locator("#literature-map-expansion-refresh-status").is_visible()
        page.wait_for_timeout(30)
        assert page.evaluate("window.__expansionPreviewGetCounts") == reopened_counts

        page.evaluate("window.__requestLog = []")
        page.locator("#literature-map-expansion-refresh-status").click()
        page.wait_for_function("window.__requestLog.some(entry => entry.method === 'GET' && entry.path.includes('/previews/'))")
        assert len(page.evaluate("window.__expansionPreviewBodies")) == 2
        assert not [entry for entry in page.evaluate("window.__requestLog") if entry["method"] == "POST"]
        page.close()
        browser.close()


def test_expansion_stops_old_polling_when_seed_or_map_changes() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?expansion-stuck-loading", wait_until="load")
        _open_expansion(page)
        page.wait_for_function("window.__expansionPreviewGetCounts.references >= 4 && window.__expansionPreviewGetCounts.citations >= 4")

        get_ids = """() => window.__requestLog
          .filter(entry => entry.method === 'GET' && /\\/previews\\/[^/]+$/.test(entry.path))
          .map(entry => entry.path.split('/').pop())"""
        seed_a_ids = set(page.evaluate(get_ids))
        assert len(seed_a_ids) == 2
        page.locator('[data-node-id="node-b"] circle').click()
        page.get_by_role("button", name="扩展关联论文").click()
        page.wait_for_function("window.__expansionPreviewBodies?.length === 4")
        page.wait_for_function("window.__expansionPreviewGetCounts.references >= 5 && window.__expansionPreviewGetCounts.citations >= 5")
        seed_b_ids = set(page.evaluate(get_ids)) - seed_a_ids
        assert len(seed_b_ids) == 2
        before_seed_switch = page.evaluate("window.__requestLog")
        old_seed_counts = {preview_id: sum(preview_id in entry["path"] for entry in before_seed_switch) for preview_id in seed_a_ids}
        page.wait_for_timeout(30)
        after_seed_switch = page.evaluate("window.__requestLog")
        assert old_seed_counts == {preview_id: sum(preview_id in entry["path"] for entry in after_seed_switch) for preview_id in seed_a_ids}

        page.locator('[data-map-id="map-fixture-b"]').click()
        page.wait_for_function("window.__requestLog.some(entry => entry.path === '/api/literature-maps/map-fixture-b/graph')")
        before_map_switch = page.evaluate("window.__requestLog")
        old_map_counts = {preview_id: sum(preview_id in entry["path"] for entry in before_map_switch) for preview_id in seed_b_ids}
        page.wait_for_timeout(30)
        after_map_switch = page.evaluate("window.__requestLog")
        assert old_map_counts == {preview_id: sum(preview_id in entry["path"] for entry in after_map_switch) for preview_id in seed_b_ids}
        page.close()
        browser.close()


def test_expansion_draft_reopens_by_owner_map_seed_with_get_only() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?expansion", wait_until="load")
        _open_expansion(page)
        page.wait_for_function("window.__expansionPreviewBodies?.length === 2")
        page.locator('[data-candidate-id="references-candidate-1"] input').check()
        page.locator('[role="tab"][data-expansion-kind="citations"]').click()
        page.locator("#literature-map-expansion-close").click()

        stored = page.evaluate("""() => Object.fromEntries(
          Object.keys(sessionStorage).filter(key => key.startsWith('literature-map-expansion:'))
            .map(key => [key, JSON.parse(sessionStorage.getItem(key))])
        )""")
        assert len(stored) == 1
        saved_key, saved_draft = next(iter(stored.items()))
        assert all(scope in saved_key for scope in ("owner-fixture", "map-fixture", "node-a"))
        assert saved_draft["owner_id"] == "owner-fixture"
        assert saved_draft["map_id"] == "map-fixture"
        assert saved_draft["seed_node_id"] == "node-a"

        page.evaluate("window.__requestLog = []")
        page.get_by_role("button", name="扩展关联论文").click()
        page.wait_for_function("document.querySelector('[role=tab][data-expansion-kind=\"citations\"]')?.getAttribute('aria-selected') === 'true'")
        page.locator('[role="tab"][data-expansion-kind="references"]').click()
        assert page.locator('[data-candidate-id="references-candidate-1"] input').is_checked()
        assert len(page.evaluate("window.__expansionPreviewBodies")) == 2
        request_log = page.evaluate("window.__requestLog")
        assert not [entry for entry in request_log if entry["method"] == "POST" and "/previews" in entry["path"]]
        assert len([entry for entry in request_log if entry["method"] == "GET" and "/previews/" in entry["path"]]) >= 2
        assert page.evaluate("window.__loadMoreBodies") == []

        page.locator("#literature-map-expansion-close").click()
        page.locator('[data-node-id="node-b"] circle').click()
        page.get_by_role("button", name="扩展关联论文").click()
        page.wait_for_function("window.__expansionPreviewBodies?.length === 4")
        assert "已选 0/20 个新身份" in page.locator(".literature-map-expansion-capacity").inner_text()
        page.locator("#literature-map-expansion-close").click()

        page.locator('[data-map-id="map-fixture-b"]').click()
        page.wait_for_selector('[data-node-id="node-a"]')
        page.locator('[data-node-id="node-a"] circle').click()
        page.get_by_role("button", name="扩展关联论文").click()
        page.wait_for_function("window.__expansionPreviewBodies?.length === 6")
        assert "已选 0/20 个新身份" in page.locator(".literature-map-expansion-capacity").inner_text()
        stored = page.evaluate("""() => Object.fromEntries(
          Object.keys(sessionStorage).filter(key => key.startsWith('literature-map-expansion:'))
            .map(key => [key, JSON.parse(sessionStorage.getItem(key))])
        )""")
        assert len(stored) == 3
        assert any("owner-fixture-b" in key and "map-fixture-b" in key and draft["seed_node_id"] == "node-a" for key, draft in stored.items())
        page.close()
        browser.close()


def test_mobile_expansion_moves_from_detail_sheet_to_nested_map_panel() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 390, "height": 820}, has_touch=True, is_mobile=True)
        page.goto(f"{FIXTURE.as_uri()}?expansion", wait_until="load")
        page.locator("#literature-map-mobile-list-open").click()
        page.locator('[data-map-id="map-fixture"]').click()
        node = page.locator('[data-node-id="node-a"] circle')
        box = node.bounding_box()
        assert box is not None
        page.touchscreen.tap(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.wait_for_function("document.querySelector('.literature-map-detail-panel')?.classList.contains('is-open')")
        page.get_by_role("button", name="扩展关联论文").click()
        page.wait_for_selector("#literature-map-preview-panel")
        page.wait_for_function("window.__expansionPreviewBodies?.length === 2")

        assert page.locator("#literature-map-preview-panel").is_visible()
        assert page.locator(".literature-map-detail-panel").is_hidden()
        assert page.locator("#literature-map-mobile-backdrop").is_hidden()
        assert page.locator("#literature-map-preview-panel").evaluate("panel => Boolean(panel.closest('.literature-map-canvas-panel') && panel.closest('#literature-maps-view'))")
        assert page.locator("#literature-map-preview-panel [role=tabpanel]").get_attribute("aria-labelledby")
        assert page.locator("#literature-map-preview-panel [role=tab]").count() == 2
        page.close()
        browser.close()


@pytest.mark.parametrize("width", [375, 390])
def test_mobile_expansion_preview_keeps_readable_height_in_constrained_canvas(width: int) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": width, "height": 844}, has_touch=True, is_mobile=True)
        page.goto(f"{FIXTURE.as_uri()}?expansion", wait_until="load")
        page.locator("#literature-map-mobile-list-open").click()
        page.locator('[data-map-id="map-fixture"]').click()
        node = page.locator('[data-node-id="node-a"] circle')
        box = node.bounding_box()
        assert box is not None
        page.touchscreen.tap(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.wait_for_function("document.querySelector('.literature-map-detail-panel')?.classList.contains('is-open')")
        page.get_by_role("button", name="扩展关联论文").click()
        page.wait_for_selector("#literature-map-preview-panel")
        page.wait_for_function("window.__expansionPreviewBodies?.length === 2")

        geometry = page.locator("#literature-map-preview-panel").evaluate(
            """panel => {
              const parent = panel.closest('.literature-map-canvas-panel');
              const parentRect = parent.getBoundingClientRect();
              const panelRect = panel.getBoundingClientRect();
              const candidates = panel.querySelector('.literature-map-expansion-candidates');
              return {
                parentHeight: parentRect.height,
                panelHeight: panelRect.height,
                panelBottom: panelRect.bottom,
                parentBottom: parentRect.bottom,
                candidateClientHeight: candidates?.clientHeight || 0,
                candidateScrollHeight: candidates?.scrollHeight || 0,
              };
            }"""
        )
        assert geometry["parentHeight"] == pytest.approx(654, abs=1)
        assert geometry["panelHeight"] >= 240, geometry
        assert geometry["panelBottom"] <= geometry["parentBottom"] + 1, geometry
        assert geometry["candidateClientHeight"] > 0, geometry
        assert geometry["candidateScrollHeight"] > geometry["candidateClientHeight"], geometry

        refs_tab = page.locator('[role="tab"][data-expansion-kind="references"]')
        citations_tab = page.locator('[role="tab"][data-expansion-kind="citations"]')
        refs_tab.click()
        page.locator("#literature-map-expansion-sort-references").select_option("year")
        ref_choice = page.locator('[data-candidate-id="references-candidate-1"] input')
        ref_choice.check()
        citations_tab.click()
        citation_choice = page.locator('[data-candidate-id="citations-candidate-1"] input')
        citation_choice.check()
        refs_tab.click()
        assert ref_choice.is_checked()
        confirm = page.locator("#literature-map-expansion-apply")
        assert confirm.is_visible()
        confirm.scroll_into_view_if_needed()
        confirm_box = confirm.bounding_box()
        parent_box = page.locator(".literature-map-canvas-panel").bounding_box()
        assert confirm_box is not None and parent_box is not None
        assert confirm_box["y"] + confirm_box["height"] <= parent_box["y"] + parent_box["height"] + 1
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.close()
        browser.close()


def test_expansion_batch_applies_both_tabs_once_and_preserves_old_layout() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?expansion-batch", wait_until="load")
        _open_expansion(page)
        page.wait_for_function("window.__expansionPreviewBodies?.length === 2")
        before = page.evaluate("window.__mockNodes.map(node => ({ id: node.node_id, position: node.position && { ...node.position }, group: node.group_id || null }))")
        page.locator('[data-candidate-id="references-candidate-0"] input').check()
        page.locator('[role="tab"][data-expansion-kind="citations"]').click()
        page.locator('[data-candidate-id="citations-candidate-0"] input').check()
        page.locator('[data-candidate-id="citations-candidate-1"] input').check()
        assert "已选 2/20 个新身份" in page.locator(".literature-map-expansion-capacity").inner_text()
        confirm = page.locator("#literature-map-expansion-apply")
        assert confirm.is_enabled()
        confirm.click()

        page.wait_for_function("window.__batchApplyBodies?.length === 1")
        page.wait_for_function("document.querySelector('#literature-map-expansion-batch')?.textContent.includes('新增 2 篇')")
        body = page.evaluate("window.__batchApplyBodies[0]")
        assert body["expected_revision"] == 3
        assert body["idempotency_key"]
        assert {selection["preview_id"] for selection in body["selections"]} == {
            "preview-expansion-map-fixture-references-1",
            "preview-expansion-map-fixture-citations-2",
        }
        assert len(body["selections"]) == 2
        assert page.evaluate("window.__applyCount") == 0
        assert not [entry for entry in page.evaluate("window.__requestLog") if entry["method"] == "POST" and entry["path"].endswith("/apply")]

        page.wait_for_function("window.__viewBodies.some(body => body.positions?.some(position => position.node_id === 'node-expansion-1'))", timeout=3000)

        after = page.evaluate("window.__mockNodes.map(node => ({ id: node.node_id, position: node.position && { ...node.position }, group: node.group_id || null }))")
        for old in before:
            current = next(node for node in after if node["id"] == old["id"])
            assert current == old
        additions = [node for node in after if node["id"].startswith("node-expansion-")]
        assert len(additions) == 2
        for node in additions:
            assert node["position"]
            assert abs(node["position"]["x"] - 390) < 800
            assert abs(node["position"]["y"] - 300) < 800
            assert "is-expansion-highlighted" in page.locator(f'[data-node-id="{node["id"]}"]').get_attribute("class")

        spacing = page.evaluate("""() => {
          const radius = node => {
            const raw = node?.citation_count;
            const count = raw === null || raw === undefined || raw === '' ? null : Number(raw);
            return count === null || !Number.isFinite(count) || count < 0 ? 8 : Math.min(28, 8 + 2 * Math.log1p(count));
          };
          const required = (a, b) => radius(a) + radius(b) + 4 * Math.max(radius(a), radius(b)) + 4;
          const additions = window.__mockNodes.filter(node => node.node_id.startsWith('node-expansion-'));
          const occupied = window.__mockNodes.filter(node => !node.removed && !node.tombstone && !node.node_id.startsWith('node-expansion-'));
          return additions.every(node => occupied.every(other => Math.hypot(node.position.x - other.position.x, node.position.y - other.position.y) + 1e-6 >= required(node, other)))
            && additions.every((node, index) => additions.slice(index + 1).every(other => Math.hypot(node.position.x - other.position.x, node.position.y - other.position.y) + 1e-6 >= required(node, other)));
        }""")
        assert spacing

        view_before = page.evaluate("window.__mockMap.view_settings.viewport")
        page.get_by_role("button", name="查看新增论文").click()
        page.wait_for_selector(".literature-map-detail-title")
        assert page.evaluate("window.__mockMap.view_settings.viewport") == view_before
        assert page.locator("#literature-map-expansion-batch").is_visible()
        page.close()
        browser.close()


def test_expansion_batch_keeps_new_nodes_hidden_by_current_graph_filters() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?expansion-batch-hidden", wait_until="load")
        _open_expansion(page)
        page.wait_for_function("window.__expansionPreviewBodies?.length === 2")
        viewport = page.evaluate("({ ...window.__mockMap.view_settings.viewport })")
        layers = page.evaluate("window.__mockMap.view_settings.layers || null")
        page.locator('[data-candidate-id="references-candidate-1"] input').check()
        page.locator("#literature-map-expansion-apply").click()
        batch = page.locator("#literature-map-expansion-batch")
        page.wait_for_function("document.querySelector('#literature-map-expansion-batch')?.textContent.includes('当前筛选或图层可能将其隐藏')")
        assert "筛选与视图未自动更改" in batch.inner_text()
        page.get_by_role("button", name="查看新增论文").click()
        page.wait_for_function("document.querySelector('#literature-map-status')?.textContent.includes('当前图中未显示这些节点')")
        assert page.evaluate("window.__mockMap.view_settings.viewport") == viewport
        assert page.evaluate("window.__mockMap.view_settings.layers") == layers
        page.close()
        browser.close()


def test_expansion_batch_respects_two_hundred_active_node_capacity() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?expansion-batch-full", wait_until="load")
        _open_expansion(page)
        page.wait_for_function("window.__expansionPreviewBodies?.length === 2")
        assert "地图容量 200/200（还可加入 0）" in page.locator(".literature-map-expansion-capacity").inner_text()
        candidate = page.locator('[data-candidate-id="references-candidate-1"] input')
        candidate.evaluate("input => input.click()")
        assert not candidate.is_checked()
        assert page.locator("#literature-map-expansion-apply").is_disabled()
        assert page.evaluate("window.__batchApplyBodies") == []
        assert "最多选择 0 个不同论文身份" in page.locator("#literature-map-status").inner_text()
        page.close()
        browser.close()


def test_expansion_batch_capacity_ignores_removed_tombstones() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?expansion-batch-tombstone-capacity", wait_until="load")
        _open_expansion(page)
        page.wait_for_function("window.__expansionPreviewBodies?.length === 2")
        assert "地图容量 199/200（还可加入 1）" in page.locator(".literature-map-expansion-capacity").inner_text()
        page.locator('[data-candidate-id="references-candidate-1"] input').check()
        assert page.locator("#literature-map-expansion-apply").is_enabled()
        assert page.evaluate("window.__batchApplyBodies") == []
        page.close()
        browser.close()


def test_expansion_batch_history_preserves_two_inflight_batches_and_old_retry() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?expansion-batch-multiple", wait_until="load")
        _open_expansion(page)
        page.wait_for_function("window.__expansionPreviewBodies?.length === 2")
        page.evaluate("window.__holdExpansionBatchPolls = true")

        page.locator('[data-candidate-id="references-candidate-1"] input').check()
        page.locator("#literature-map-expansion-apply").click()
        page.wait_for_function("window.__batchJobIds?.length === 1 && window.__batchJobGetCounts[window.__batchJobIds[0]] >= 1")
        first_id = page.evaluate("window.__batchJobIds[0]")
        assert "批次处理中" in page.locator("#literature-map-expansion-batch").inner_text()

        page.locator('[data-candidate-id="references-candidate-2"] input').check()
        page.locator("#literature-map-expansion-apply").click()
        page.wait_for_function("window.__batchJobIds?.length === 2 && window.__batchJobGetCounts[window.__batchJobIds[1]] >= 1")
        second_id = page.evaluate("window.__batchJobIds[1]")
        assert first_id != second_id
        history = page.locator("#literature-map-expansion-batch-history")
        assert history.locator("[data-expansion-batch-job-id]").count() == 2
        assert "上次读取" in history.inner_text()
        draft_key = "literature-map-expansion:owner-fixture:map-fixture:node-a"
        draft = page.evaluate("(key) => JSON.parse(sessionStorage.getItem(key))", draft_key)
        records = {record["batch_job_id"]: record for record in draft["batch_records"]}
        assert records[first_id]["batch_result"]["added_count"] == 1
        assert records[first_id]["batch_result"]["node_ids"] == ["node-expansion-1"]
        assert records[second_id]["batch_result"]["added_count"] == 1
        assert records[second_id]["batch_result"]["node_ids"] == ["node-expansion-2"]

        old_record = history.locator(f'[data-expansion-batch-job-id="{first_id}"]')
        old_record.click()
        page.wait_for_function(f"window.__batchJobGetCounts['{first_id}'] >= 2")
        panel = page.locator("#literature-map-expansion-batch")
        assert "参考文献候选 2" in panel.inner_text()
        assert page.locator("#literature-map-expansion-retry-metadata").is_visible()
        page.locator("#literature-map-expansion-retry-metadata").click()
        page.wait_for_function("window.__metadataRetryJobIds?.length === 1")
        assert page.evaluate("window.__metadataRetryJobIds[0]") == first_id
        assert page.evaluate("window.__metadataRetryBodies[0].node_ids") == ["node-expansion-1"]

        post_count = page.evaluate("window.__requestLog.filter(entry => entry.method === 'POST').length")
        page.locator("#literature-map-expansion-close").click()
        page.get_by_role("button", name="扩展关联论文").click()
        page.wait_for_function(f"window.__batchJobGetCounts['{first_id}'] >= 4")
        assert page.locator("#literature-map-expansion-batch-history [data-expansion-batch-job-id]").count() == 2
        assert page.evaluate("window.__requestLog.filter(entry => entry.method === 'POST').length") == post_count
        reopened_draft = page.evaluate("(key) => JSON.parse(sessionStorage.getItem(key))", draft_key)
        reopened_records = {record["batch_job_id"]: record for record in reopened_draft["batch_records"]}
        assert reopened_records[first_id]["batch_result"]["node_ids"] == ["node-expansion-1"]
        assert reopened_records[second_id]["batch_result"]["node_ids"] == ["node-expansion-2"]
        page.locator("#literature-map-expansion-view-added").click()
        page.wait_for_function("document.querySelector('#literature-map-detail .literature-map-detail-title')?.textContent.includes('参考文献候选 2')")

        page.locator(f'#literature-map-expansion-batch-history [data-expansion-batch-job-id="{second_id}"]').click()
        page.wait_for_function(f"window.__batchJobGetCounts['{second_id}'] >= 2")
        assert "参考文献候选 3" in page.locator("#literature-map-expansion-batch").inner_text()
        assert page.evaluate("window.__requestLog.filter(entry => entry.method === 'POST').length") == post_count
        page.locator("#literature-map-expansion-view-added").click()
        page.wait_for_function("document.querySelector('#literature-map-detail .literature-map-detail-title')?.textContent.includes('参考文献候选 3')")
        page.close()
        browser.close()


def test_expansion_batch_without_job_preserves_previous_batch_and_layout() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?expansion-batch-no-job", wait_until="load")
        _open_expansion(page)
        page.wait_for_function("window.__expansionPreviewBodies?.length === 2")
        page.evaluate("window.__holdExpansionBatchPolls = true")

        page.locator('[data-candidate-id="references-candidate-1"] input').check()
        page.locator("#literature-map-expansion-apply").click()
        page.wait_for_function("window.__batchJobIds?.length === 1 && window.__batchJobGetCounts[window.__batchJobIds[0]] >= 1")
        first_id = page.evaluate("window.__batchJobIds[0]")
        read_positions = """() => Array.from(document.querySelectorAll('#literature-map-svg .literature-map-node'))
          .map((node) => [node.dataset.nodeId, node.querySelector('circle')?.getAttribute('cx'), node.querySelector('circle')?.getAttribute('cy')])
          .sort((left, right) => left[0].localeCompare(right[0]))"""
        positions_before = page.evaluate(read_positions)

        page.locator('[data-candidate-id="references-candidate-2"] input').check()
        page.locator("#literature-map-expansion-apply").click()
        page.wait_for_selector("#literature-map-expansion-batch-notice")

        draft_key = "literature-map-expansion:owner-fixture:map-fixture:node-a"
        draft = page.evaluate("(key) => JSON.parse(sessionStorage.getItem(key))", draft_key)
        assert draft["batch_job_id"] == first_id
        assert draft["selected_batch_job_id"] == first_id
        assert len(draft["batch_records"]) == 1
        assert draft["batch_records"][0]["batch_job_id"] == first_id
        assert draft["batch_records"][0]["batch_result"]["added_count"] == 1
        assert draft["batch_records"][0]["batch_result"]["node_ids"] == ["node-expansion-1"]
        assert page.evaluate("window.__batchJobIds") == [first_id]
        assert page.locator(".literature-map-expansion-batch-status").is_visible()
        assert "未创建新的批次任务" in page.locator("#literature-map-expansion-batch-notice").inner_text()
        assert "is-expansion-highlighted" in page.locator('[data-node-id="node-expansion-1"]').get_attribute("class")
        assert page.evaluate(read_positions) == positions_before

        post_count = page.evaluate("window.__requestLog.filter(entry => entry.method === 'POST').length")
        page.locator("#literature-map-expansion-close").click()
        page.get_by_role("button", name="扩展关联论文").click()
        page.wait_for_function(f"window.__batchJobGetCounts['{first_id}'] >= 2")
        reopened = page.evaluate("(key) => JSON.parse(sessionStorage.getItem(key))", draft_key)
        assert reopened["selected_batch_job_id"] == first_id
        assert reopened["batch_records"][0]["batch_result"]["node_ids"] == ["node-expansion-1"]
        assert "未创建新的批次任务" in page.locator("#literature-map-expansion-batch-notice").inner_text()
        assert page.evaluate("window.__requestLog.filter(entry => entry.method === 'POST').length") == post_count
        page.locator("#literature-map-expansion-view-added").click()
        page.wait_for_function("document.querySelector('#literature-map-detail .literature-map-detail-title')?.textContent.includes('参考文献候选 2')")
        page.close()
        browser.close()


def test_expansion_batch_history_isolated_when_owner_changes_on_same_map_and_seed() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?expansion-batch-multiple", wait_until="load")
        _open_expansion(page)
        page.wait_for_function("window.__expansionPreviewBodies?.length === 2")
        page.evaluate("window.__holdExpansionBatchPolls = true")
        page.locator('[data-candidate-id="references-candidate-1"] input').check()
        page.locator("#literature-map-expansion-apply").click()
        page.wait_for_function("window.__batchJobIds?.length === 1")
        first_id = page.evaluate("window.__batchJobIds[0]")
        owner_a_draft = page.evaluate("sessionStorage.getItem('literature-map-expansion:owner-fixture:map-fixture:node-a')")
        assert first_id in owner_a_draft

        page.goto(f"{FIXTURE.as_uri()}?expansion-batch-multiple&expansion-owner-b", wait_until="load")
        _open_expansion(page)
        page.wait_for_function("window.__expansionPreviewBodies?.length === 2")
        assert page.locator("#literature-map-expansion-batch-history").count() == 0
        owner_b_draft = page.evaluate("sessionStorage.getItem('literature-map-expansion:owner-fixture-b:map-fixture:node-a')")
        assert owner_b_draft is not None
        assert first_id not in owner_b_draft
        assert '"batch_records":[]' in owner_b_draft
        assert first_id in page.evaluate("sessionStorage.getItem('literature-map-expansion:owner-fixture:map-fixture:node-a')")
        page.close()
        browser.close()


def test_expansion_batch_old_generation_response_and_timer_cannot_write_new_scope_draft() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?expansion-batch-scope-race", wait_until="load")
        _open_expansion(page)
        page.wait_for_function("window.__expansionPreviewBodies?.length === 2")
        page.evaluate("window.__holdExpansionBatchPolls = true")

        page.locator('[data-candidate-id="references-candidate-1"] input').check()
        page.locator("#literature-map-expansion-apply").click()
        page.wait_for_function("window.__batchJobIds?.length === 1 && window.__batchJobGetCounts[window.__batchJobIds[0]] >= 1")
        first_id = page.evaluate("window.__batchJobIds[0]")
        page.wait_for_function("window.__expansionBatchPollCallbacks?.length === 1")

        page.evaluate("window.__expansionBatchPollCallbacks[0]()")
        page.wait_for_function("typeof window.__releaseExpansionBatchGet === 'function'")
        old_scope_key = "literature-map-expansion:owner-fixture:map-fixture:node-a"
        old_scope_before_response = page.evaluate("(key) => sessionStorage.getItem(key)", old_scope_key)

        page.locator("#literature-map-expansion-close").click()
        page.locator('[data-node-id="node-b"] circle').click()
        page.get_by_role("button", name="扩展关联论文").click()
        new_scope_key = "literature-map-expansion:owner-fixture:map-fixture:node-b"
        page.wait_for_function("(key) => sessionStorage.getItem(key) !== null", arg=new_scope_key)
        new_scope_draft = page.evaluate("(key) => sessionStorage.getItem(key)", new_scope_key)
        assert first_id not in new_scope_draft

        page.evaluate("window.__releaseExpansionBatchGet()")
        page.wait_for_timeout(50)
        assert page.evaluate("(key) => sessionStorage.getItem(key)", old_scope_key) == old_scope_before_response
        assert page.evaluate("(key) => sessionStorage.getItem(key)", new_scope_key) == new_scope_draft

        batch_get_count = page.evaluate("(jobId) => window.__batchJobGetCounts[jobId]", first_id)
        page.evaluate("window.__expansionBatchPollCallbacks[0]()")
        page.wait_for_timeout(20)
        assert page.evaluate("(jobId) => window.__batchJobGetCounts[jobId]", first_id) == batch_get_count
        assert page.evaluate("(key) => sessionStorage.getItem(key)", new_scope_key) == new_scope_draft
        page.close()
        browser.close()


def test_expansion_conflict_requires_get_then_explicit_revalidate_then_confirm() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?expansion-batch-conflict", wait_until="load")
        _open_expansion(page)
        page.wait_for_function("window.__expansionPreviewBodies?.length === 2")
        page.locator('[data-candidate-id="references-candidate-1"] input').check()
        page.locator('[role="tab"][data-expansion-kind="citations"]').click()
        page.locator('[data-candidate-id="citations-candidate-1"] input').check()
        page.locator("#literature-map-expansion-apply").click()

        page.wait_for_selector("#literature-map-expansion-revalidate")
        assert len(page.evaluate("window.__batchApplyBodies")) == 1
        assert page.evaluate("window.__revalidateBodies") == []
        page.wait_for_function("window.__requestLog.some(entry => entry.method === 'GET' && entry.path === '/api/literature-maps/map-fixture/graph')")
        for kind in ("references", "citations"):
            assert page.evaluate(f"window.__requestLog.filter(entry => entry.method === 'GET' && entry.path.includes('preview-expansion-map-fixture-{kind}')).length") >= 2

        assert page.evaluate("window.__batchApplyBodies.length") == 1
        page.locator("#literature-map-expansion-revalidate").click()
        page.wait_for_function("window.__revalidateBodies?.length === 1")
        page.wait_for_selector(".literature-map-expansion-revalidation")
        assert "无效" in page.locator(".literature-map-expansion-revalidation").inner_text()
        revalidate = page.evaluate("window.__revalidateBodies[0]")
        assert revalidate["expected_revision"] == 4
        assert revalidate["idempotency_key"]
        assert len(revalidate["selections"]) == 2
        assert page.evaluate("window.__batchApplyBodies.length") == 1

        invalid = page.locator('[data-candidate-id="citations-candidate-1"] input')
        assert invalid.is_checked()
        assert invalid.is_enabled()
        invalid.uncheck()
        page.locator("#literature-map-expansion-apply").click()
        page.wait_for_function("window.__batchApplyBodies?.length === 2")
        second = page.evaluate("window.__batchApplyBodies[1]")
        assert len(second["selections"]) == 1
        assert second["selections"][0]["selected_candidate_ids"] == ["references-candidate-1"]
        page.close()
        browser.close()


def test_expansion_batch_progress_has_scoped_retry_and_map_queue_controls() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?expansion-batch-progress", wait_until="load")
        _open_expansion(page)
        page.wait_for_function("window.__expansionPreviewBodies?.length === 2")
        for index in [1, 2, 5, 6, 7, 8, 9]:
            page.locator(f'[data-candidate-id="references-candidate-{index}"] input').check()
        page.locator("#literature-map-expansion-apply").click()
        page.wait_for_function("window.__batchApplyBodies?.length === 1")
        panel = page.locator("#literature-map-expansion-batch")
        page.wait_for_function("window.__batchJobGetCount >= 1")
        assert "正在补充摘要" in panel.inner_text()
        assert "无摘要，已跳过" in panel.inner_text()
        assert "分析排队中" in panel.inner_text()
        assert "分析进行中" in panel.inner_text()
        assert "分析完成" in panel.inner_text()
        assert "分析失败" in panel.inner_text()
        assert "影响同图其它待分析论文" in panel.inner_text()

        page.locator("#literature-map-expansion-pause-map-queue").click()
        page.wait_for_function("window.__queueMutationBodies?.some(body => body.action === 'pause')")
        page.locator("#literature-map-expansion-resume-map-queue").click()
        page.wait_for_function("window.__queueMutationBodies?.some(body => body.action === 'resume')")

        page.wait_for_function("window.__batchJobGetCount > 4")
        assert page.locator("#literature-map-expansion-retry-metadata").is_visible()
        page.locator("#literature-map-expansion-retry-metadata").click()
        page.wait_for_function("window.__metadataRetryBodies?.length === 1")
        metadata_retry = page.evaluate("window.__metadataRetryBodies[0]")
        assert metadata_retry["node_ids"] == ["node-expansion-2", "node-expansion-3"]
        assert metadata_retry["steps"] == ["metadata"]
        assert metadata_retry["idempotency_key"]

        page.locator("#literature-map-expansion-retry-analysis").click()
        page.wait_for_function("window.__queueMutationBodies?.some(body => body.analysis_ids?.includes('analysis-expansion-failed'))")
        analysis_retry = page.evaluate("window.__queueMutationBodies.find(body => body.analysis_ids?.includes('analysis-expansion-failed'))")
        assert analysis_retry["analysis_ids"] == ["analysis-expansion-failed"]
        assert analysis_retry["idempotency_key"]

        before = page.evaluate("window.__requestLog.filter(entry => entry.method === 'POST').length")
        page.locator("#literature-map-expansion-close").click()
        page.get_by_role("button", name="扩展关联论文").click()
        page.wait_for_function("window.__batchJobGetCount >= 2")
        assert page.evaluate("window.__requestLog.filter(entry => entry.method === 'POST').length") == before
        page.close()


def test_expansion_batch_unknown_status_is_explained_and_can_refresh() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 390, "height": 820}, device_scale_factor=1, is_mobile=True, has_touch=True)
        page.goto(f"{FIXTURE.as_uri()}?expansion-batch-unknown", wait_until="load")
        page.locator("#literature-map-mobile-list-open").click()
        page.locator('[data-map-id="map-fixture"]').click()
        node = page.locator('[data-node-id="node-a"] circle')
        box = node.bounding_box()
        assert box is not None
        page.touchscreen.tap(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.wait_for_function("document.querySelector('.literature-map-detail-panel')?.classList.contains('is-open')")
        page.get_by_role("button", name="扩展关联论文").click()
        page.wait_for_selector("#literature-map-preview-panel")
        page.wait_for_function("window.__expansionPreviewBodies?.length === 2")
        page.locator('[data-candidate-id="references-candidate-1"] input').check()
        page.locator("#literature-map-expansion-apply").click()
        page.wait_for_selector("#literature-map-expansion-batch-refresh")
        assert "无法识别" in page.locator("#literature-map-expansion-batch").inner_text()
        assert page.locator("#literature-map-expansion-batch-refresh").is_visible()
        assert page.evaluate("window.__batchJobGetCount") < 82
        assert page.evaluate("""() => {
          const batch = document.querySelector('#literature-map-expansion-batch');
          const preview = document.querySelector('#literature-map-preview-panel');
          return batch?.parentElement === preview
            && preview?.parentElement?.classList.contains('literature-map-canvas-panel')
            && getComputedStyle(preview).overflowY === 'auto'
            && Math.abs(parseFloat(getComputedStyle(batch.querySelector('.literature-map-expansion-batch-items')).maxHeight) - window.innerHeight * 0.15) < 2;
        }""")
        page.close()
        browser.close()


def test_expansion_batch_polling_stops_at_limit_and_manual_refresh_is_read_only() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?expansion-batch-stuck", wait_until="load")
        _open_expansion(page)
        page.wait_for_function("window.__expansionPreviewBodies?.length === 2")
        page.locator('[data-candidate-id="references-candidate-1"] input').check()
        page.locator("#literature-map-expansion-apply").click()
        page.wait_for_function("window.__batchJobGetCount >= 81", timeout=10000)
        refresh = page.locator("#literature-map-expansion-batch-refresh")
        assert refresh.is_visible()
        assert "自动读取已暂停" in page.locator("#literature-map-expansion-batch").inner_text()
        stopped_count = page.evaluate("window.__batchJobGetCount")
        page.wait_for_timeout(40)
        assert page.evaluate("window.__batchJobGetCount") == stopped_count

        post_count = page.evaluate("window.__requestLog.filter(entry => entry.method === 'POST').length")
        page.evaluate("window.__holdExpansionBatchPolls = true")
        refresh.click()
        page.wait_for_function(f"window.__batchJobGetCount >= {stopped_count + 1}")
        assert page.evaluate("window.__requestLog.filter(entry => entry.method === 'POST').length") == post_count

        page.locator("#literature-map-expansion-close").click()
        page.get_by_role("button", name="扩展关联论文").click()
        page.wait_for_function(f"window.__batchJobGetCount >= {stopped_count + 2}")
        assert page.evaluate("window.__requestLog.filter(entry => entry.method === 'POST').length") == post_count
        page.close()
        browser.close()


def test_component_fixture_recovers_server_preview_without_session_storage() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?server-preview&latest-restore", wait_until="load")
        page.evaluate("window.sessionStorage.clear()")
        page.locator('[data-map-id="map-fixture"]').click()
        page.locator("#literature-map-open-saved-preview").wait_for(state="visible")
        assert page.evaluate("window.__previewBodies") == []
        assert page.locator("#literature-map-preview-panel").is_hidden()
        page.get_by_role("button", name="打开上次预览").click()
        page.wait_for_selector("#literature-map-preview-panel")
        preview_text = page.locator("#literature-map-preview-panel").inner_text()
        assert "引用数：29000 → 29014" in preview_text
        assert "字段变更" in preview_text
        request_log = page.evaluate("window.__requestLog")
        ensure_posts = [
            entry
            for entry in request_log
            if entry["method"] == "POST"
            and entry["path"] == "/api/literature-maps/map-fixture/analysis-queue/ensure"
        ]
        assert len(ensure_posts) == 1
        assert [
            entry
            for entry in request_log
            if entry["method"] == "POST"
            and entry["path"] != "/api/literature-maps/map-fixture/analysis-queue/ensure"
        ] == []
        assert [
            entry
            for entry in request_log
            if entry["method"] == "POST"
            and ("/previews" in entry["path"] or entry["path"].endswith("/apply"))
        ] == []
        paths = [entry["path"] for entry in request_log]
        assert any("/events?after_seq=0" in path for path in paths)
        assert any("/jobs/job-server-preview" in path for path in paths)
        assert any("/previews/preview-server" in path for path in paths)
        page.get_by_role("button", name="关闭预览").click()
        assert page.locator("#literature-map-preview-panel").is_hidden()
        page.locator("#literature-map-open-saved-preview").wait_for(state="visible")
        page.close()

        delayed = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        delayed.goto(f"{FIXTURE.as_uri()}?server-preview-delay", wait_until="load")
        delayed.evaluate("window.sessionStorage.clear()")
        delayed.locator('[data-map-id="map-fixture"]').click()
        delayed.locator("#literature-map-open-saved-preview").wait_for(state="visible")
        delayed.get_by_role("button", name="打开上次预览").click()
        delayed.get_by_role("button", name="关闭预览").click()
        delayed.wait_for_timeout(500)
        assert delayed.locator("#literature-map-preview-panel").is_hidden()
        assert delayed.locator("#literature-map-open-saved-preview").is_visible()
        assert delayed.evaluate("window.__previewBodies") == []
        delayed.close()
        browser.close()


def test_component_fixture_paginates_persisted_preview_events_until_empty_page() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?paged-preview&latest-restore", wait_until="load")
        page.evaluate("window.sessionStorage.clear()")
        page.locator('[data-map-id="map-fixture"]').click()
        page.locator("#literature-map-open-saved-preview").wait_for(state="visible")
        paths = page.evaluate("window.__requestLog.map((entry) => entry.path)")
        assert any("/events?after_seq=0" in path for path in paths)
        assert any("/events?after_seq=200" in path for path in paths)
        assert any("/events?after_seq=203" in path for path in paths)
        assert any("/jobs/job-server-preview-paged" in path for path in paths)
        request_log = page.evaluate("window.__requestLog")
        ensure_posts = [
            entry
            for entry in request_log
            if entry["method"] == "POST"
            and entry["path"] == "/api/literature-maps/map-fixture/analysis-queue/ensure"
        ]
        assert len(ensure_posts) == 1
        assert [
            entry
            for entry in request_log
            if entry["method"] == "POST"
            and entry["path"] != "/api/literature-maps/map-fixture/analysis-queue/ensure"
        ] == []
        assert [
            entry
            for entry in request_log
            if entry["method"] == "POST"
            and ("/previews" in entry["path"] or entry["path"].endswith("/apply"))
        ] == []
        page.get_by_role("button", name="打开上次预览").click()
        page.wait_for_selector("#literature-map-preview-panel")
        assert "引用数：29000 → 29014" in page.locator("#literature-map-preview-panel").inner_text()
        assert any("/previews/preview-server-paged" in path for path in page.evaluate("window.__requestLog.map((entry) => entry.path)"))
        page.close()
        browser.close()


def test_component_fixture_stops_persisted_event_pagination_on_bad_cursor_or_inactive_view() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        stalled = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        stalled.goto(f"{FIXTURE.as_uri()}?paged-preview-stall", wait_until="load")
        stalled.evaluate("window.sessionStorage.clear()")
        stalled.locator('[data-map-id="map-fixture"]').click()
        stalled.wait_for_function("document.querySelector('#literature-map-status')?.textContent.includes('游标未前进')")
        stalled_paths = stalled.evaluate("window.__requestLog.map((entry) => entry.path)")
        assert len([path for path in stalled_paths if "/events?after_seq=" in path]) == 1
        assert stalled.locator("#literature-map-open-saved-preview").is_hidden()
        assert stalled.evaluate("window.__previewBodies") == []
        stalled.close()

        inactive = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        inactive.goto(f"{FIXTURE.as_uri()}?paged-preview-delay", wait_until="load")
        inactive.evaluate("window.sessionStorage.clear()")
        inactive.locator('[data-map-id="map-fixture"]').click()
        inactive.wait_for_function("window.__requestLog?.some((entry) => entry.path.includes('/events?after_seq=0'))")
        inactive.evaluate("window.LiteratureMaps.setActive(false)")
        inactive.wait_for_timeout(500)
        assert inactive.locator("#literature-map-open-saved-preview").is_hidden()
        assert inactive.locator("#literature-map-preview-panel").is_hidden()
        assert inactive.evaluate("window.__previewBodies") == []
        inactive.close()
        browser.close()


def test_component_fixture_ignores_stale_paginated_preview_after_map_switch() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?paged-preview-race", wait_until="load")
        page.evaluate("window.sessionStorage.clear()")
        page.locator('[data-map-id="map-fixture"]').click()
        page.wait_for_function("window.__requestLog?.some((entry) => entry.path.includes('/events?after_seq=0'))")
        page.locator('[data-map-id="map-fixture-b"]').click()
        page.wait_for_timeout(600)
        assert page.locator("#literature-map-current-title").inner_text() == "第二张地图"
        assert page.locator("#literature-map-open-saved-preview").is_hidden()
        assert page.locator("#literature-map-preview-panel").is_hidden()
        assert page.evaluate("window.__previewBodies") == []
        page.close()
        browser.close()


def test_component_fixture_ignores_stale_server_preview_discovery_after_map_switch() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?server-preview-race", wait_until="load")
        page.evaluate("window.sessionStorage.clear()")
        page.locator('[data-map-id="map-fixture"]').click()
        page.wait_for_timeout(20)
        page.locator('[data-map-id="map-fixture-b"]').click()
        page.wait_for_timeout(500)
        assert page.locator("#literature-map-current-title").inner_text() == "第二张地图"
        assert page.locator("#literature-map-open-saved-preview").is_hidden()
        assert page.locator("#literature-map-preview-panel").is_hidden()
        assert page.evaluate("window.__previewBodies") == []
        page.close()
        browser.close()


def test_component_fixture_handles_refresh_diff_cas_and_recovery_actions() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)

        refresh = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        refresh.goto(f"{FIXTURE.as_uri()}?refresh-diff", wait_until="load")
        refresh.locator('[data-map-id="map-fixture"]').click()
        refresh.get_by_role("button", name="刷新预览").click()
        refresh.wait_for_selector("#literature-map-preview-panel")
        assert refresh.evaluate("window.__previewBodies?.[0]?.kind") == "refresh"
        refresh_text = refresh.locator("#literature-map-preview-panel").inner_text()
        assert "字段变更" in refresh_text
        assert "引用数：29000 → 29014" in refresh_text
        assert "摘要：<img src=x onerror=alert(1)> → 摘要已更新" in refresh_text
        assert "新增关系：node-b；移除关系：空列表" in refresh_text
        assert "引用数：null → 605" in refresh_text
        assert "来源：空字符串 → 字段缺失" in refresh_text
        assert refresh.locator(".literature-map-preview-diff li").count() == 8
        assert refresh.locator("img[onerror]").count() == 0
        assert refresh.evaluate("window.__applyBody") is None
        refresh.get_by_role("button", name="确认刷新").click()
        refresh.wait_for_function("window.__applyBody?.selected_candidate_ids?.length === 0")
        assert refresh.evaluate("window.__applyBody[\"expected_revision\"]") == 3
        assert refresh.locator('[data-node-id="node-new"]').count() == 0
        refresh.close()

        empty = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        empty.goto(f"{FIXTURE.as_uri()}?refresh-empty", wait_until="load")
        empty.locator('[data-map-id="map-fixture"]').click()
        empty.get_by_role("button", name="刷新预览").click()
        empty.wait_for_selector("#literature-map-preview-panel")
        empty_text = empty.locator("#literature-map-preview-panel").inner_text()
        assert "没有字段或关系差异；地图无需更新。" in empty_text
        assert empty.get_by_role("button", name="确认刷新").count() == 0
        empty.close()

        conflict = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        conflict.goto(f"{FIXTURE.as_uri()}?preview-conflict", wait_until="load")
        conflict.locator('[data-map-id="map-fixture"]').click()
        conflict.get_by_role("button", name="继续搜索").click()
        conflict.wait_for_selector("#literature-map-preview-panel")
        topic_body = conflict.evaluate("window.__previewBodies?.[0]")
        assert topic_body["kind"] == "topic"
        assert topic_body["query"] == "联邦学习"
        assert topic_body["idempotency_key"]
        conflict.locator('[data-candidate-id="candidate-new"] input').check()
        conflict.get_by_role("button", name="确认加入").click()
        conflict.wait_for_function("document.querySelector('#literature-map-status')?.textContent.includes('版本已变化')")
        assert conflict.get_by_role("button", name="重新读取并预览").count() == 1
        assert conflict.evaluate("window.__applyCount") == 1
        conflict.get_by_role("button", name="重新读取并预览").click()
        conflict.wait_for_function("window.__previewBodies?.length === 2")
        assert conflict.evaluate("window.__applyCount") == 1
        conflict.close()

        partial = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        partial.goto(f"{FIXTURE.as_uri()}?recovery", wait_until="load")
        partial.locator('[data-map-id="map-fixture"]').click()
        partial.locator("#literature-map-retry-job").wait_for(state="visible")
        assert partial.locator("#literature-map-stop-job").is_hidden()
        partial.get_by_role("button", name="重试失败单元").click()
        partial.wait_for_function("window.__jobActionBodies?.some((body) => body.action === 'retry')")
        partial.close()

        running = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        running.goto(f"{FIXTURE.as_uri()}?running", wait_until="load")
        running.locator('[data-map-id="map-fixture"]').click()
        running.locator("#literature-map-stop-job").wait_for(state="visible")
        assert running.locator("#literature-map-retry-job").is_hidden()
        running.get_by_role("button", name="停止任务").click()
        running.wait_for_function("window.__jobActionBodies?.some((body) => body.action === 'stop')")
        assert running.locator("#literature-map-stop-job").is_hidden()
        running.get_by_role("button", name="重试失败单元").click()
        running.wait_for_function("window.__jobActionBodies?.some((body) => body.action === 'retry')")
        running.close()
        browser.close()


def test_component_fixture_handles_tombstone_restore_and_indexed_document_link() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?recovery", wait_until="load")
        page.locator('[data-map-id="map-fixture"]').click()
        page.locator('[data-node-id="node-a"] circle').click()
        page.get_by_role("button", name="移出地图").click()
        page.wait_for_function("window.__nodeActionBodies?.some((body) => body.action === 'remove')")
        assert page.get_by_role("button", name="扩展关联论文").count() == 0
        page.get_by_role("button", name="显式恢复").click()
        page.wait_for_function("window.__nodeActionBodies?.some((body) => body.action === 'restore')")
        page.get_by_role("button", name="扩展关联论文").click()
        page.wait_for_selector('[data-candidate-id="references-candidate-4"]')

        page.locator('[data-node-id="node-b"] circle').click()
        page.wait_for_selector(".literature-map-document-link")
        assert page.get_by_role("button", name="加入知识库").count() == 0
        assert "已加入知识库" in page.locator("#literature-map-detail").inner_text()
        assert "document-fixture" in page.locator("#literature-map-detail").inner_text()
        page.get_by_role("button", name="在知识库中查看").click()
        assert page.evaluate("window.__lastImportBody") is None
        assert page.evaluate("window.__viewBodies") == []
        page.close()

        indexed_tombstone = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        indexed_tombstone.goto(f"{FIXTURE.as_uri()}?indexed-tombstone", wait_until="load")
        indexed_tombstone.locator('[data-map-id="map-fixture"]').click()
        indexed_tombstone.locator('[data-node-id="node-b"] circle').click()
        indexed_tombstone.wait_for_selector(".literature-map-document-link")
        assert indexed_tombstone.get_by_role("button", name="加入知识库").count() == 0
        assert indexed_tombstone.get_by_role("button", name="在知识库中查看").count() == 1
        assert indexed_tombstone.get_by_role("button", name="显式恢复").count() == 1
        indexed_tombstone.get_by_role("button", name="在知识库中查看").click()
        assert indexed_tombstone.evaluate("window.__lastImportBody") is None
        indexed_tombstone.get_by_role("button", name="显式恢复").click()
        indexed_tombstone.wait_for_function("window.__nodeActionBodies?.some((body) => body.action === 'restore')")
        indexed_tombstone.get_by_role("button", name="扩展关联论文").click()
        indexed_tombstone.wait_for_selector("#literature-map-preview-panel")
        indexed_tombstone.close()
        browser.close()


def test_expansion_candidate_sort_only_reorders_loaded_rows_and_preserves_selection_cursor() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?expansion-candidate-metadata", wait_until="load")
        _open_expansion(page)
        page.wait_for_function("window.__expansionPreviewBodies?.length === 2")

        def candidate_ids(kind: str) -> list[str]:
            return page.locator(f"#literature-map-expansion-panel-{kind} .literature-map-expansion-candidate").evaluate_all(
                "rows => rows.map(row => row.dataset.candidateId)"
            )

        references = [
            "references-candidate-source-first",
            "references-candidate-source-second",
            "references-candidate-source-third",
            "references-candidate-source-fourth",
        ]
        citations = [
            "citations-candidate-source-first",
            "citations-candidate-source-second",
            "citations-candidate-source-third",
            "citations-candidate-source-fourth",
        ]
        assert candidate_ids("references") == references
        controls = page.locator("#literature-map-expansion-sort-references")
        assert controls.input_value() == "source"
        assert "排序只对已加载候选生效" in page.locator(".literature-map-expansion-scope-note").inner_text()
        assert "不是全来源排名" in page.locator(".literature-map-expansion-scope-note").inner_text()
        assert "未按地图主题“联邦学习”筛选" in page.locator(".literature-map-expansion-scope-note").inner_text()

        page.locator('[data-candidate-id="references-candidate-source-second"] input').check()
        page.locator('[role="tab"][data-expansion-kind="citations"]').click()
        page.locator('[data-candidate-id="citations-candidate-source-first"] input').check()
        pagination_before = page.locator("#literature-map-expansion-panel-citations .literature-map-expansion-pagination").inner_text()
        server_pagination_before = page.evaluate("window.__expansionPreviewPagination")
        request_count_before = page.evaluate("window.__requestLog.length")
        post_count_before = page.evaluate("window.__requestLog.filter(entry => entry.method === 'POST').length")
        load_more_before = page.evaluate("window.__loadMoreBodies.length")

        page.locator("#literature-map-expansion-sort-citations").select_option("year")
        assert candidate_ids("citations") == [citations[1], citations[3], citations[0], citations[2]]
        assert page.locator('[data-candidate-id="citations-candidate-source-first"] input').is_checked()
        page.locator("#literature-map-expansion-sort-citations").select_option("citation_count")
        assert candidate_ids("citations") == [citations[3], citations[0], citations[1], citations[2]]
        assert page.locator('[data-candidate-id="citations-candidate-source-first"] input').is_checked()

        assert page.locator("#literature-map-expansion-panel-citations .literature-map-expansion-pagination").inner_text() == pagination_before
        assert page.evaluate("window.__expansionPreviewPagination") == server_pagination_before
        assert page.evaluate("window.__loadMoreBodies.length") == load_more_before
        assert page.evaluate("window.__requestLog.length") == request_count_before
        assert page.evaluate("window.__requestLog.filter(entry => entry.method === 'POST').length") == post_count_before
        assert page.evaluate("window.__batchApplyBodies.length") == 0

        page.locator('[role="tab"][data-expansion-kind="references"]').click()
        assert page.locator('[data-candidate-id="references-candidate-source-second"] input').is_checked()
        assert "已选 2/20 个新身份" in page.locator(".literature-map-expansion-capacity").inner_text()
        page.close()
        browser.close()


def test_expansion_candidate_metadata_shows_availability_and_definite_scope_differences() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?expansion-candidate-metadata", wait_until="load")
        _open_expansion(page)
        page.wait_for_function("window.__expansionPreviewBodies?.length === 2")
        panel = page.locator("#literature-map-expansion-panel-references")
        first = page.locator('[data-candidate-id="references-candidate-source-first"]')
        second = page.locator('[data-candidate-id="references-candidate-source-second"]')
        missing = page.locator('[data-candidate-id="references-candidate-source-third"]')
        fourth = page.locator('[data-candidate-id="references-candidate-source-fourth"]')

        assert "来源 IEEE S&P" in first.inner_text()
        assert "检索来源 IEEE S&P" in first.inner_text()
        assert "引用数 6" in first.inner_text()
        assert "摘要可用" in first.inner_text()
        assert first.locator(".literature-map-expansion-scope-tag[data-scope='year-out-of-range']").inner_text() == "超出年份范围"
        assert first.locator(".literature-map-expansion-scope-tag[data-scope='source-out-of-range']").inner_text() == "超出来源范围"
        assert first.locator(".literature-map-expansion-scope-tag[data-scope='conference-out-of-range']").inner_text() == "超出会议范围"

        assert "来源未提供" in second.inner_text()
        assert "检索来源 Semantic Scholar" in second.inner_text()
        assert "引用数 6" in second.inner_text()
        assert "摘要可用" in second.inner_text()
        assert second.locator(".literature-map-expansion-scope-tag[data-scope='source-unverified']").inner_text() == "来源范围待核实"
        assert second.locator(".literature-map-expansion-scope-tag[data-scope='conference-unverified']").inner_text() == "会议范围待核实"

        assert "作者未提供" in missing.inner_text()
        assert "年份未提供" in missing.inner_text()
        assert "来源未提供" in missing.inner_text()
        assert "引用数 未知" in missing.inner_text()
        assert "摘要可用性待核实" in missing.inner_text()
        assert missing.locator(".literature-map-expansion-scope-tag[data-scope='year-unverified']").inner_text() == "年份范围待核实"

        assert "来源 USENIX Security" in fourth.inner_text()
        assert "引用数 11" in fourth.inner_text()
        assert "缺少摘要" in fourth.inner_text()
        assert panel.locator(".literature-map-expansion-sort-controls").count() == 1
        assert page.evaluate("window.__loadMoreBodies") == []
        page.close()
        browser.close()
