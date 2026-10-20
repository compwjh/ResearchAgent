"""Task05 map-analysis and conversation bridge frontend contract checks."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = (ROOT / "frontend/literature-maps.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/literature-maps.css").read_text(encoding="utf-8")
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
FIXTURE = ROOT / "tests/frontend/fixtures/literature_map_component.html"


def _open_browser_or_skip(playwright):
    return playwright.chromium.launch(headless=True)


def test_map_analysis_contract_uses_frozen_evidence_and_navigation_shapes() -> None:
    assert "evidence_level" in MODULE
    assert "available_evidence_levels" in MODULE
    assert "source_versions" in MODULE
    assert "/analyses" in MODULE
    assert "/conversation" in MODULE
    assert "idempotency_key" in MODULE
    assert "document_ids" not in MODULE
    assert "innerHTML" not in MODULE
    assert ".literature-map-analysis" in STYLES
    assert ".literature-map-analysis-history-item" in STYLES
    assert "/assets/literature-maps.js?v=8" in INDEX
    assert "/assets/literature-maps.css?v=6" in INDEX
    assert "/assets/app.js?v=59" in INDEX


def test_component_fixture_supports_analysis_history_failure_and_conversation_bridge() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?analysis", wait_until="load")
        page.locator('[data-map-id="map-fixture"]').click()
        page.locator('[data-node-id="node-a"] circle').click()
        page.wait_for_selector(".literature-map-analysis")

        panel = page.locator(".literature-map-analysis")
        assert "摘要级" in panel.inner_text()
        assert "source-abstract-v1" in panel.inner_text()
        assert panel.get_by_role("button", name="基于摘要分析").is_enabled()
        assert panel.get_by_role("button", name="基于全文分析").is_disabled()
        assert "全文索引尚未就绪" in panel.inner_text()

        panel.get_by_role("button", name="基于摘要分析").click()
        page.wait_for_function("window.__analysisBodies?.length === 1")
        assert page.evaluate("window.__analysisBodies[0]") == {
            "evidence_level": "abstract",
            "idempotency_key": page.evaluate("window.__analysisBodies[0].idempotency_key"),
        }
        page.wait_for_selector(".literature-map-analysis-result")
        assert "仅基于摘要" in panel.inner_text()
        assert "摘要级分析结果" in panel.inner_text()
        assert "<img src=x onerror=alert(1)>" in panel.inner_text()
        assert page.locator("img[onerror]").count() == 0
        page.locator(".literature-map-analysis-history-button").filter(has_text="v0").click()
        assert "旧版本摘要结果" in panel.inner_text()
        assert page.locator(".literature-map-analysis-history-button[aria-pressed='true']").inner_text().startswith("v0")

        panel.get_by_role("button", name="关于本篇提问").click()
        page.wait_for_function("window.__conversationBodies?.length === 1")
        assert page.evaluate("window.__conversationBodies[0].evidence_level") == "abstract"
        assert page.evaluate("window.__conversationBodies[0].idempotency_key")
        assert page.evaluate("window.__openedConversation") == "conversation-fixture"
        assert page.locator(".literature-map-analysis").is_visible()
        page.close()
        browser.close()


def test_component_fixture_keeps_running_job_requeryable_after_poll_limit() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?analysis-poll-limit", wait_until="load")
        page.locator('[data-map-id="map-fixture"]').click()
        page.locator('[data-node-id="node-a"] circle').click()
        page.wait_for_selector(".literature-map-analysis")
        page.locator(".literature-map-analysis").get_by_role("button", name="基于摘要分析").click()
        page.wait_for_function("window.__analysisDetailCalls >= 120")
        page.wait_for_function("document.querySelector('.literature-map-analysis-state')?.textContent.includes('后台分析仍在运行')")
        assert "任务不会被标记失败" in page.locator(".literature-map-analysis-state").inner_text()
        assert page.locator(".literature-map-analysis").get_by_role("button", name="重新查询").is_visible()
        assert page.evaluate("window.__analysisBodies.length") == 1
        page.locator(".literature-map-analysis").get_by_role("button", name="重新查询").click()
        page.wait_for_function("window.__analysisDetailCalls >= 240")
        assert page.evaluate("window.__analysisBodies.length") == 1
        assert page.locator(".literature-map-analysis-state").inner_text().find("后台分析仍在运行") >= 0
        page.close()
        browser.close()


def test_component_fixture_shows_retryable_failure_and_drops_stale_analysis() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        failed = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        failed.goto(f"{FIXTURE.as_uri()}?analysis-fail", wait_until="load")
        failed.locator('[data-map-id="map-fixture"]').click()
        failed.locator('[data-node-id="node-a"] circle').click()
        failed.wait_for_selector(".literature-map-analysis")
        failed.locator(".literature-map-analysis").get_by_role("button", name="基于摘要分析").click()
        failed.wait_for_selector(".literature-map-analysis-error")
        assert "模型暂时不可用" in failed.locator(".literature-map-analysis").inner_text()
        assert failed.locator(".literature-map-analysis").get_by_role("button", name="重新分析").is_visible()

        race = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        race.goto(f"{FIXTURE.as_uri()}?analysis-race", wait_until="load")
        race.locator('[data-map-id="map-fixture"]').click()
        race.locator('[data-node-id="node-a"] circle').click()
        race.wait_for_selector(".literature-map-analysis")
        race.locator('[data-map-id="map-fixture-b"]').click()
        race.wait_for_timeout(450)
        assert race.locator("#literature-map-current-title").inner_text() == "第二张地图"
        assert race.locator(".literature-map-analysis").count() == 0
        assert race.evaluate("window.__analysisBodies") == []
        failed.close()
        race.close()
        browser.close()
