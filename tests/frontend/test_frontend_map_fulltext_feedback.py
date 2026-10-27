"""Chromium journeys for the map's fulltext analysis status and recovery card."""

from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/frontend/fixtures/literature_map_component.html"


def _launch(playwright):
    try:
        return playwright.chromium.launch(headless=True)
    except Exception as exc:  # pragma: no cover - host dependent
        pytest.skip(f"真实浏览器阻塞，未将组件检查冒充通过: {type(exc).__name__}: {exc}")


def _open_full_tab(page, state: str = ""):
    page.set_default_timeout(5000)
    suffix = f"&{state}" if state else ""
    page.goto(f"{FIXTURE.as_uri()}?analysis{suffix}", wait_until="load")
    page.locator('[data-map-id="map-fixture"]').click()
    page.locator('[data-node-id="node-a"] circle').click()
    page.wait_for_selector(".literature-map-analysis-tabs")
    panel = page.locator(".literature-map-analysis")
    panel.get_by_role("tab", name="全文分析").click()
    card = panel.locator(".literature-map-fulltext-feedback")
    assert card.is_visible()
    return panel, card


def test_full_tab_immediately_shows_unimported_state_and_manual_import_action():
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        panel, card = _open_full_tab(page)

        assert panel.get_by_role("tab", name="摘要分析").is_visible()
        assert panel.get_by_role("tab", name="全文分析").get_attribute("aria-selected") == "true"
        assert card.get_by_text("未入库", exact=False).is_visible()
        assert card.get_by_role("button", name="获取并加入知识库").is_enabled()
        assert page.evaluate("window.__analysisBodies") == []
        assert page.evaluate("window.__importCount") == 0

        card.get_by_role("button", name="获取并加入知识库").click()
        page.wait_for_function("window.__importCount === 1")
        assert page.evaluate("window.__analysisBodies") == []
        browser.close()


def test_login_failure_navigates_to_existing_import_recovery_without_new_batch():
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _panel, card = _open_full_tab(page, "full-login-required")

        assert "需要登录" in card.inner_text()
        assert "现有等待登录批次" in card.inner_text()
        recovery = card.get_by_role("button", name="查看导入处理/登录处理")
        assert recovery.is_enabled()
        page.evaluate("window.__paperRecoveryClicks = 0; document.querySelector('[data-view=\"papers\"]')?.addEventListener('click', () => window.__paperRecoveryClicks += 1)")
        assert page.evaluate("window.__importCount") == 0
        recovery.click()
        assert page.evaluate("window.__paperRecoveryClicks") == 1
        assert "返回地图刷新全文状态" in card.inner_text()
        assert page.evaluate("window.__importCount") == 0
        assert page.evaluate("window.__analysisBodies") == []
        browser.close()


def test_import_processing_offers_refresh_and_does_not_submit_analysis():
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _panel, card = _open_full_tab(page, "full-importing")

        assert "正在入库或建立索引" in card.inner_text()
        refresh = card.get_by_role("button", name="刷新全文状态")
        assert refresh.is_enabled()
        before = page.evaluate("window.__analysisNodeResponses")
        refresh.click()
        page.wait_for_function("arg => window.__analysisNodeResponses > arg", arg=before)
        assert page.evaluate("window.__analysisBodies") == []
        assert page.evaluate("window.__importCount") == 0
        browser.close()


def test_indexed_but_not_ready_is_unknown_and_links_to_kb_check():
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _panel, card = _open_full_tab(page, "full-indexed-unknown")

        assert "全文依据暂不可用" in card.inner_text()
        assert "原因未确定" in card.inner_text()
        assert "全文依据已就绪" not in card.inner_text()
        assert "MYSTERY" not in card.inner_text()
        assert card.get_by_role("button", name="前往知识库检查或修复索引").is_enabled()
        card.get_by_role("button", name="前往知识库检查或修复索引").click()
        assert page.evaluate("window.__knowledgeBaseIds") == ["document-indexed-unknown"]
        assert page.evaluate("window.__analysisBodies") == []
        browser.close()


def test_permission_and_source_mismatch_reasons_are_chinese_and_actionable():
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _panel, permission = _open_full_tab(page, "full-permission-denied")
        assert "权限" in permission.inner_text()
        assert "KB_PERMISSION_DENIED" not in permission.inner_text()
        permission.get_by_role("button", name="检查知识库权限").click()
        assert page.evaluate("window.__knowledgeBaseIds") == ["document-permission-denied"]

        _panel, mismatch = _open_full_tab(page, "full-source-mismatch")
        assert "来源版本不匹配" in mismatch.inner_text()
        assert "SOURCE_VERSION_MISMATCH" not in mismatch.inner_text()
        assert mismatch.get_by_role("button", name="前往知识库检查或修复索引").is_enabled()
        assert page.evaluate("window.__analysisBodies") == []
        browser.close()


def test_ready_without_full_result_can_start_only_after_user_click():
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _panel, card = _open_full_tab(page, "full-ready-no-result")

        assert "全文依据已就绪" in card.inner_text()
        start = card.get_by_role("button", name="基于全文分析")
        assert start.is_enabled()
        assert page.evaluate("window.__analysisBodies") == []
        start.click()
        page.wait_for_function("window.__analysisBodies.length === 1")
        assert page.evaluate("window.__analysisBodies[0].evidence_level") == "full"
        browser.close()


def test_available_evidence_summary_follows_authoritative_source_fields():
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        not_ready_page = browser.new_page(viewport={"width": 1280, "height": 900})
        panel, card = _open_full_tab(not_ready_page, "full-availability-mismatch")

        assert panel.locator(".literature-map-analysis-source").inner_text() == "可用依据：摘要级"
        assert "全文依据已就绪" not in card.inner_text()
        full_action = card.get_by_role("button", name="基于全文分析")
        assert full_action.is_enabled()
        full_action.click()
        assert panel.locator(".literature-map-analysis-action-feedback").is_visible()
        assert not_ready_page.evaluate("window.__analysisBodies") == []
        assert "未入库" in card.inner_text()

        ready_page = browser.new_page(viewport={"width": 1280, "height": 900})
        ready_panel, ready_card = _open_full_tab(ready_page, "full-ready-list-mismatch")
        assert ready_panel.locator(".literature-map-analysis-source").inner_text() == "可用依据：全文索引片段依据"
        assert "全文分析已完成" in ready_card.inner_text()
        assert ready_card.get_by_role("button", name="基于全文分析").is_enabled()
        abstract_action = ready_panel.get_by_role("button", name="基于摘要分析")
        assert abstract_action.is_enabled()
        abstract_action.click()
        assert ready_panel.locator(".literature-map-analysis-action-feedback").is_visible()
        assert ready_page.evaluate("window.__analysisBodies") == []
        browser.close()


def test_full_analysis_progress_and_completed_markdown_history_stay_in_full_tab():
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _panel, card = _open_full_tab(page, "full-ready&analysis-pending")

        card.get_by_role("button", name="基于全文分析").click()
        assert "全文分析正在排队" in card.inner_text() or "全文分析正在提交" in card.inner_text()
        page.wait_for_function("window.__analysisBodies.length === 1")
        assert page.evaluate("window.__analysisBodies[0].evidence_level") == "full"
        assert "全文分析结果（全文索引片段依据）" in page.locator(".literature-map-analysis-result").inner_text() or page.locator(".literature-map-analysis-state").is_visible()

        _panel, completed = _open_full_tab(page, "full-ready")
        assert "全文分析已完成" in completed.inner_text()
        assert "全文索引片段分析结果" in page.locator(".literature-map-analysis-result").inner_text()
        assert page.locator(".literature-map-analysis-history").inner_text().count("全文索引片段依据") >= 1
        assert "PDF 阅读器" not in page.locator(".literature-map-analysis").inner_text()
        browser.close()


def test_completed_full_analysis_renders_markdown_and_history_inside_full_tab():
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _panel, card = _open_full_tab(page, "analysis-markdown&full-ready")

        assert "全文分析已完成" in card.inner_text()
        summary = page.locator(".literature-map-analysis-summary")
        assert summary.locator("h3").inner_text() == "全文分析"
        assert summary.locator("strong").inner_text() == "全文结论"
        assert summary.locator("ul li").inner_text() == "全文证据"
        assert summary.locator("code").inner_text() == "full-code"
        history = page.locator(".literature-map-analysis-history")
        assert "全文索引片段依据" in history.inner_text()
        assert page.locator(".literature-map-analysis-result").is_visible()
        browser.close()


def test_retryable_download_failure_uses_existing_manual_retry_action():
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _panel, card = _open_full_tab(page, "analysis&import-failure")

        assert "入库失败" in card.inner_text()
        retry = card.get_by_role("button", name="人工重试入库")
        assert retry.is_enabled()
        assert page.evaluate("window.__importCount") == 0
        assert page.evaluate("window.__analysisBodies") == []
        retry.click()
        page.wait_for_function("window.__importCount === 1")
        assert page.evaluate("window.__analysisBodies") == []
        assert page.evaluate("window.__requestLog.filter(item => item.path.endsWith('/imports')).length") == 1
        browser.close()


def test_unknown_import_status_is_not_exposed_as_machine_code():
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _panel, card = _open_full_tab(page, "full-unknown-import-status")

        assert "状态待确认" in page.locator(".literature-map-detail-status").inner_text()
        assert "RARE_IMPORT_STATE" not in page.locator("#literature-map-detail").inner_text()
        assert "原因未确定" in card.inner_text()
        browser.close()


def test_late_fulltext_status_from_previous_node_cannot_replace_current_card():
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"{FIXTURE.as_uri()}?analysis-race-full-ready", wait_until="load")
        page.locator('[data-map-id="map-fixture"]').click()
        page.locator('[data-node-id="node-a"] circle').click()
        page.wait_for_selector(".literature-map-analysis-tabs")
        page.locator(".literature-map-analysis").get_by_role("tab", name="全文分析").click()
        page.locator('[data-node-id="node-b"] circle').click()
        page.wait_for_function("document.querySelector('.literature-map-detail-title')?.textContent.includes('Private aggregation paper')")
        page.wait_for_function("window.__analysisNodeResponses >= 2")
        page.locator(".literature-map-analysis").get_by_role("tab", name="全文分析").click()
        card = page.locator(".literature-map-fulltext-feedback")
        assert card.is_visible()
        assert "原因未确定" in card.inner_text()
        assert "全文依据已就绪" not in card.inner_text()
        assert "document-fixture" not in card.inner_text()
        assert "全文分析结果" not in card.inner_text()
        assert page.evaluate("window.__analysisBodies") == []
        browser.close()
