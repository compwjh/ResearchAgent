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
    assert "/assets/literature-maps.js?v=6" in INDEX
    assert "/assets/literature-maps.css?v=4" in INDEX
    assert "innerHTML" not in MODULE
    for marker in (
        "/previews",
        "selected_candidate_ids",
        "expected_revision",
        "MAP_PREVIEW_EXPIRED",
        "重新读取并预览",
        "继续搜索",
        "刷新预览",
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
        ".literature-map-preview-candidate",
        ".literature-map-preview-capacity",
        ".literature-map-job-actions",
        ".literature-map-document-link",
    ):
        assert selector in STYLES


def test_component_fixture_supports_preview_apply_cas_and_persistent_reopen() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(FIXTURE.as_uri(), wait_until="load")
        page.locator('[data-map-id="map-fixture"]').click()
        page.locator('[data-node-id="node-a"] circle').click()
        page.get_by_role("button", name="参考文献").click()
        page.wait_for_selector("#literature-map-preview-panel")
        preview_body = page.evaluate("window.__previewBodies?.[0]")
        assert preview_body["kind"] == "references"
        assert preview_body["node_id"] == "node-a"
        assert preview_body["idempotency_key"]
        assert page.locator('[data-candidate-id="candidate-existing"] input').is_disabled()
        assert page.locator('[data-candidate-id="candidate-removed"] input').is_disabled()
        assert "已选择 0/20" in page.locator(".literature-map-preview-capacity").inner_text()
        page.locator('[data-candidate-id="candidate-new"] input').check()
        assert "已选择 1/20" in page.locator(".literature-map-preview-capacity").inner_text()
        page.get_by_role("button", name="确认加入").click()
        page.wait_for_function("window.__applyBody?.selected_candidate_ids?.includes('candidate-new')")
        apply_body = page.evaluate("window.__applyBody")
        assert apply_body["expected_revision"] == 3
        assert apply_body["idempotency_key"]
        assert page.locator('[data-node-id="node-new"]').count() == 1

        # A persisted preview is reloaded after the public lifecycle toggle.
        page.evaluate("window.LiteratureMaps.setActive(false)")
        page.wait_for_timeout(20)
        page.evaluate("window.LiteratureMaps.setActive(true)")
        page.locator('[data-map-id="map-fixture"]').click()
        page.wait_for_selector("#literature-map-preview-panel")
        assert page.locator("#literature-map-preview-panel").is_visible()
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
        assert page.get_by_role("button", name="参考文献").count() == 0
        page.get_by_role("button", name="显式恢复").click()
        page.wait_for_function("window.__nodeActionBodies?.some((body) => body.action === 'restore')")
        page.get_by_role("button", name="参考文献").click()
        page.wait_for_selector('[data-candidate-id="candidate-removed"]')

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
        indexed_tombstone.get_by_role("button", name="参考文献").click()
        indexed_tombstone.wait_for_selector("#literature-map-preview-panel")
        indexed_tombstone.close()
        browser.close()
