"""Queue and evidence-tab browser contracts for the literature map component."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/frontend/fixtures/literature_map_component.html"


def _open_node(page, query: str) -> None:
    page.goto(f"{FIXTURE.as_uri()}?{query}", wait_until="load")
    page.locator('[data-map-id="map-fixture"]').click()
    page.wait_for_selector('[data-node-id="node-a"]')
    page.locator('[data-node-id="node-a"] circle').click()
    page.wait_for_selector(".literature-map-analysis")


def test_analysis_queue_is_idempotent_visible_and_actionable() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"{FIXTURE.as_uri()}?queue", wait_until="load")
        page.locator('[data-map-id="map-fixture"]').click()
        page.wait_for_selector("#literature-map-analysis-queue:not([hidden])")
        page.wait_for_function("window.__queueEnsureCount === 1")
        assert page.evaluate("window.__queueBodies[0]") == {"idempotency_key": page.evaluate("window.__queueBodies[0].idempotency_key")}
        queue = page.locator("#literature-map-analysis-queue")
        assert "运行中" in queue.inner_text()
        assert "完成 1/4" in queue.inner_text()
        assert "失败 1" in queue.inner_text()
        assert "USER_PAUSED" not in queue.inner_text()

        queue.get_by_role("button", name="暂停队列").click()
        page.wait_for_function("document.querySelector('#literature-map-analysis-queue')?.innerText.includes('已暂停')")
        assert page.evaluate("window.__queueMutationBodies.at(-1).action") == "pause"
        queue.get_by_role("button", name="继续队列").click()
        page.wait_for_function("document.querySelector('#literature-map-analysis-queue')?.innerText.includes('运行中')")
        assert page.evaluate("window.__queueMutationBodies.at(-1).action") == "resume"
        queue.get_by_role("button", name="重试失败项").click()
        page.wait_for_function("window.__queueMutationBodies.at(-1).action === 'retry'")
        assert "失败项" not in queue.inner_text()
        assert page.evaluate("window.__queueEnsureCount") == 1
        browser.close()


def test_analysis_tabs_keep_histories_separate_and_full_result_selects_full_tab() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _open_node(page, "full-ready")
        panel = page.locator(".literature-map-analysis")
        assert "摘要级分析结果" in panel.inner_text()
        panel.get_by_role("tab", name="全文").click()
        page.wait_for_function("document.querySelector('.literature-map-analysis-result')?.innerText.includes('全文索引片段分析结果')")
        assert "摘要级分析结果" not in panel.inner_text()
        assert "全文索引尚未就绪" not in panel.inner_text()
        assert panel.locator(".literature-map-analysis-history-button").count() == 1
        panel.get_by_role("tab", name="摘要").click()
        assert panel.locator(".literature-map-analysis-history-button").count() == 2
        panel.locator(".literature-map-analysis-history-button").filter(has_text="v0").click()
        assert "旧版本摘要结果" in panel.inner_text()
        browser.close()


def test_full_unavailable_tab_exposes_existing_recovery_entry_without_machine_code() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _open_node(page, "analysis")
        panel = page.locator(".literature-map-analysis")
        panel.get_by_role("tab", name="全文").click()
        assert "全文索引尚未就绪" in panel.inner_text()
        assert panel.get_by_role("button", name="获取并加入知识库").is_visible()
        assert "MAP_FULLTEXT_UNAVAILABLE" not in panel.inner_text()
        browser.close()


def test_manual_regeneration_warns_model_call_and_blocks_duplicate_submission() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _open_node(page, "analysis-first-regeneration&analysis-manual-delay")
        panel = page.locator(".literature-map-analysis")
        panel.get_by_role("button", name="基于摘要分析").click()
        page.wait_for_selector(".literature-map-analysis-result")
        assert "首次显式分析结果" in panel.inner_text()
        manual = panel.get_by_role("button", name="重新生成摘要（会调用模型）")
        assert manual.is_visible()
        manual.click()
        page.wait_for_function("document.querySelector('.literature-map-analysis button[disabled]') !== null")
        assert "会调用模型" in panel.inner_text()
        manual.click(force=True)
        page.wait_for_function("window.__analysisBodies.length === 2")
        page.wait_for_function("document.querySelector('.literature-map-analysis-error')")
        assert page.evaluate("window.__analysisBodies.length") == 2
        assert "首次显式分析结果" in panel.inner_text()
        assert "第二次生成失败" in panel.inner_text()
        browser.close()
