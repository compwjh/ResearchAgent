"""Browser contracts for safe map import-failure diagnostics and recovery."""

from __future__ import annotations

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


def _open_node(page, query: str) -> None:
    page.goto(f"{FIXTURE.as_uri()}?{query}", wait_until="load")
    page.locator('[data-map-id="map-fixture"]').click()
    page.locator('[data-node-id="node-a"] circle').click()
    page.wait_for_selector(".literature-map-detail-title")


def test_import_failure_projects_safe_diagnostics_and_survives_reopen() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_node(page, "import-post-failure")
        assert page.locator(".literature-map-import-diagnostics").count() == 0

        page.get_by_role("button", name="加入知识库").click()
        page.wait_for_function("window.__importCount === 1")
        page.wait_for_function("document.querySelector('.literature-map-import-diagnostics')?.textContent.includes('提供方暂时限流')")
        assert page.locator(".literature-map-import-diagnostics").count() == 1, page.locator("#literature-map-detail").inner_html()
        detail_text = page.locator("#literature-map-detail").inner_text()
        assert "提供方暂时限流" in detail_text
        assert "arXiv 身份冲突" in page.locator(".literature-map-import-diagnostics").inner_text()
        assert "可人工重试" in detail_text
        assert "SEMANTIC_SCHOLAR_RATE_LIMITED" not in detail_text
        assert "https://www.semanticscholar.org" not in detail_text
        retry = page.get_by_role("button", name="人工重试入库")
        assert retry.is_enabled()
        assert page.evaluate("window.__requestLog.filter(item => item.path.endsWith('/imports')).length") == 1

        page.locator('[data-node-id="node-b"] circle').click()
        page.wait_for_selector('.literature-map-detail-title')
        page.locator('[data-node-id="node-a"] circle').click()
        page.wait_for_function("document.querySelector('.literature-map-import-diagnostics')?.textContent.includes('arXiv 身份冲突')")
        assert "失败原因未记录" not in page.locator("#literature-map-detail").inner_text()
        assert page.evaluate("window.__importCount") == 1
        page.close()
        browser.close()


def test_legacy_import_failure_shows_unknown_reason_without_pdf_guess() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_node(page, "import-legacy-failure")
        detail_text = page.locator("#literature-map-detail").inner_text()
        assert "入库状态：失败" in detail_text
        assert "失败原因未记录" in detail_text
        assert "PDF_NOT_FOUND" not in detail_text
        assert page.get_by_role("button", name="人工重新提交入库").is_enabled()
        assert page.evaluate("window.__importCount") == 0
        page.close()
        browser.close()


def test_blocked_import_stays_disabled_with_visible_next_step() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_node(page, "import-blocked")
        diagnostics = page.locator(".literature-map-import-diagnostics")
        detail_text = page.locator("#literature-map-detail").inner_text()
        assert "下载被来源策略阻止" in detail_text
        assert "当前未标记为可重试" in diagnostics.inner_text()
        assert "人工处理入口" in diagnostics.inner_text()
        blocked = page.get_by_role("button", name="人工重新提交入库")
        assert blocked.is_disabled()
        assert blocked.get_attribute("aria-describedby") == "literature-map-import-diagnostics"
        assert page.evaluate("window.__importCount") == 0
        page.close()
        browser.close()


def test_successful_import_clears_diagnostics_and_exposes_document_entry() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_node(page, "import-success")
        assert "失败原因" in page.locator("#literature-map-detail").inner_text()
        page.get_by_role("button", name="人工重试入库").click()
        page.wait_for_function("window.__importCount === 1")
        page.wait_for_function("document.querySelector('.literature-map-document-link')?.textContent.includes('document-import-success')")
        detail_text = page.locator("#literature-map-detail").inner_text()
        assert "已加入知识库" in detail_text
        assert "document-import-success" in detail_text
        assert "失败原因" not in detail_text
        assert page.locator(".literature-map-import-diagnostics").count() == 0
        page.close()
        browser.close()


def test_import_transport_failure_is_distinct_from_business_failure() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_node(page, "import-transport-failure")
        page.get_by_role("button", name="加入知识库").click()
        page.wait_for_function("document.querySelector('#literature-map-import-status')?.textContent.includes('传输错误')")
        status = page.locator("#literature-map-import-status").inner_text()
        assert "HTTP 503" in status
        assert page.locator(".literature-map-import-diagnostics").count() == 0
        assert page.evaluate("window.__importCount") == 1
        page.close()
        browser.close()
