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
    assert "/assets/literature-maps.js?v=33" in INDEX
    assert "/assets/literature-maps.css?v=20" in INDEX
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
        "批量确认待接入",
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
        assert page.locator('#literature-map-groups .literature-map-group-row[data-group-id="group-fixture"]').is_visible()

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
        assert confirm.is_disabled()
        assert "批量确认待接入" in confirm.inner_text()
        assert page.evaluate("window.__applyBody") is None
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
