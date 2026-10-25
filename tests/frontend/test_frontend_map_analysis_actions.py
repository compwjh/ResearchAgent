"""Browser contracts for unavailable and busy map analysis actions."""

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
    page.wait_for_selector(".literature-map-analysis")


def test_unavailable_full_analysis_click_shows_reason_without_post() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _open_node(page, "analysis")
        panel = page.locator(".literature-map-analysis")
        full = panel.get_by_role("button", name="基于全文分析")
        assert full.is_enabled()
        full.click()
        feedback = panel.locator("[data-analysis-action-feedback]")
        assert feedback.is_visible()
        assert "全文索引尚未就绪" in feedback.inner_text()
        assert "请先切换到“全文”页签" in feedback.inner_text()
        assert "获取并加入知识库" in feedback.inner_text()
        assert page.evaluate("window.__analysisBodies") == []
        browser.close()


def test_unavailable_abstract_analysis_click_shows_reason_without_post() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _open_node(page, "analysis-no-evidence")
        panel = page.locator(".literature-map-analysis")
        abstract = panel.get_by_role("button", name="基于摘要分析")
        assert abstract.is_enabled()
        abstract.click()
        feedback = panel.locator("[data-analysis-action-feedback]")
        assert feedback.is_visible()
        assert "没有可引用的有效证据片段" in feedback.inner_text()
        assert "下一步" in feedback.inner_text()
        assert page.evaluate("window.__analysisBodies") == []
        browser.close()


def test_unavailable_conversation_click_shows_reason_without_post() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _open_node(page, "analysis-no-evidence")
        panel = page.locator(".literature-map-analysis")
        conversation = panel.get_by_role("button", name="关于本篇提问")
        assert conversation.is_enabled()
        conversation.click()
        feedback = panel.locator("[data-analysis-action-feedback]")
        assert feedback.is_visible()
        assert "没有可引用的有效证据片段" in feedback.inner_text()
        assert "下一步" in feedback.inner_text()
        assert page.evaluate("window.__conversationBodies") == []
        browser.close()


def test_conversation_busy_label_and_lock_prevent_duplicate_posts() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _open_node(page, "analysis")
        panel = page.locator(".literature-map-analysis")
        conversation = panel.get_by_role("button", name="关于本篇提问")
        page.evaluate("""
            const button = Array.from(document.querySelectorAll('.literature-map-analysis button'))
                .find((node) => node.textContent.includes('关于本篇提问'));
            button?.dispatchEvent(new MouseEvent('click', {bubbles: true}));
            button?.dispatchEvent(new MouseEvent('click', {bubbles: true}));
        """)
        page.wait_for_function("window.__conversationBodies.length === 1")
        assert "打开中" in conversation.inner_text()
        assert page.evaluate("window.__conversationBodies.length") == 1
        browser.close()


def test_pending_analysis_labels_busy_action_and_ignores_duplicate_click() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _open_node(page, "analysis-pending")
        panel = page.locator(".literature-map-analysis")
        abstract = panel.get_by_role("button", name="基于摘要分析")
        abstract.click()
        page.wait_for_function("document.querySelector('.literature-map-analysis button[disabled]') !== null")
        assert "摘要分析进行中" in panel.inner_text()
        assert "请等待当前请求完成" in panel.locator("[data-analysis-action-feedback]").inner_text()
        page.evaluate("""
            document.querySelector('.literature-map-analysis button[disabled][aria-describedby="literature-map-analysis-action-feedback"]')
                ?.dispatchEvent(new MouseEvent('click', {bubbles: true}))
        """)
        page.wait_for_timeout(40)
        assert page.evaluate("window.__analysisBodies.length") == 1
        browser.close()


def test_ready_full_analysis_still_posts_existing_request() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _open_node(page, "full-ready")
        panel = page.locator(".literature-map-analysis")
        full = panel.get_by_role("button", name="基于全文分析")
        assert full.is_enabled()
        full.click()
        page.wait_for_function("window.__analysisBodies.length === 1")
        assert page.evaluate("window.__analysisBodies[0].evidence_level") == "full"
        browser.close()


def test_blocked_full_recovery_action_shows_diagnostic_without_import_post() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _open_node(page, "analysis&import-blocked")
        panel = page.locator(".literature-map-analysis")
        panel.get_by_role("tab", name="全文").click()
        recovery = panel.get_by_role("button", name="获取并加入知识库")
        assert recovery.count() == 1, panel.inner_text()
        recovery.click()
        feedback = panel.locator("[data-analysis-action-feedback]")
        assert feedback.is_visible()
        assert "下载被来源策略阻止" in feedback.inner_text()
        assert "人工处理入口" in feedback.inner_text()
        assert page.evaluate("window.__importCount") == 0
        browser.close()
