"""Spec-048 当前部署版本的真实 Chromium / API 端到端验证脚本。

运行：.venv/bin/python docs/sdd/plans/048/runs/task-04/browser_e2e.py
产物：browser-e2e.json、map-tabs-desktop.png、map-tabs-mobile.png
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8000"
TOPIC = "面向边缘设备的联邦学习隐私保护（Spec048 E2E）"

result: dict = {"base": BASE, "checks": {}, "api": [], "assets": [], "errors": []}


def record(page, label):
    def _on_response(response):
        url = response.url
        if "/api/" in url:
            try:
                body = response.text()[:300]
            except Exception:
                body = ""
            result["api"].append({"page": label, "url": url, "status": response.status, "body": body})
        if "/assets/literature-maps." in url:
            result["assets"].append({"url": url, "status": response.status})

    page.on("response", _on_response)


def open_maps(page):
    """用 hash 路由进入文献地图；窄屏侧栏被折叠时回退为 DOM click 触发同一导航处理。"""
    page.goto(BASE + "/#literature-maps-view", wait_until="load", timeout=30000)
    try:
        page.wait_for_selector("#literature-map-main-tabs", timeout=8000)
    except Exception:
        page.evaluate("() => document.querySelector('[data-view=\"literature-maps\"]')?.click()")
        page.wait_for_selector("#literature-map-main-tabs", timeout=15000)
    return page


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        desktop = browser.new_page(viewport={"width": 1440, "height": 900})
        record(desktop, "desktop")
        open_maps(desktop)

        maps_tab = desktop.locator("#literature-map-tab-maps")
        create_tab = desktop.locator("#literature-map-tab-create")
        create_panel = desktop.locator("#literature-map-create-panel")

        result["checks"]["tabs_present"] = desktop.locator('[role="tablist"]#literature-map-main-tabs').count() == 1
        result["checks"]["default_maps_selected"] = maps_tab.get_attribute("aria-selected") == "true"
        result["checks"]["create_panel_hidden_by_default"] = create_panel.is_hidden()
        result["checks"]["maps_panel_visible_by_default"] = desktop.locator("#literature-map-tabpanel-maps").is_visible()

        create_tab.click()
        result["checks"]["create_panel_visible_after_tab"] = create_panel.is_visible()
        topic = desktop.locator("#literature-map-topic")
        topic.fill(TOPIC)
        maps_tab.click()
        create_tab.click()
        result["checks"]["form_value_preserved_across_tabs"] = topic.input_value() == TOPIC

        maps_tab.click()
        refresh = desktop.locator("#literature-map-refresh-button")
        result["checks"]["refresh_in_canvas_tools"] = (
            desktop.locator(".literature-map-canvas-head .literature-map-tools #literature-map-refresh-button").count() == 1
        )
        result["checks"]["refresh_no_visible_text"] = refresh.inner_text().strip() == ""
        result["checks"]["refresh_aria_label"] = refresh.get_attribute("aria-label") == "刷新状态"
        result["checks"]["refresh_icon_node"] = refresh.locator(".literature-map-refresh-icon").count() == 1
        refresh.click()
        result["checks"]["spin_class_after_click"] = bool(
            desktop.evaluate("() => document.querySelector('#literature-map-refresh-button').classList.contains('is-spinning')")
        )
        result["checks"]["header_new_button_removed"] = desktop.locator("#literature-map-new-button").count() == 0
        result["checks"]["header_other_actions_retained"] = all(
            desktop.locator(f"#{button_id}").count() == 1
            for button_id in (
                "literature-map-continue-search",
                "literature-map-refresh-preview",
                "literature-map-open-saved-preview",
                "literature-map-stop-job",
                "literature-map-retry-job",
            )
        )
        result["checks"]["live_css_v36"] = any("literature-maps.css?v=36" in a["url"] for a in result["assets"])
        result["checks"]["live_js_v48"] = any("literature-maps.js?v=48" in a["url"] for a in result["assets"])
        desktop.screenshot(path=str(OUT / "map-tabs-desktop.png"), full_page=False)

        mobile = browser.new_page(viewport={"width": 375, "height": 812})
        record(mobile, "mobile")
        open_maps(mobile)
        mobile.locator("#literature-map-tab-create").click()
        result["checks"]["mobile_create_tab_opens_form"] = mobile.locator("#literature-map-create-panel").is_visible()
        mobile.locator("#literature-map-tab-maps").click()
        mobile_refresh = mobile.locator("#literature-map-refresh-button")
        box = mobile_refresh.bounding_box()
        result["checks"]["mobile_refresh_touch_target_ge_44"] = bool(box and box["height"] >= 44)
        result["checks"]["mobile_refresh_no_visible_text"] = mobile_refresh.inner_text().strip() == ""
        mobile.screenshot(path=str(OUT / "map-tabs-mobile.png"), full_page=False)
        browser.close()

    with urlopen(BASE + "/api/health", timeout=10) as response:
        result["health"] = {"status": response.status, "body": response.read(200).decode("utf-8", "replace")}


try:
    run()
except Exception as exc:  # 保证证据文件始终落盘，失败如实登记
    result["errors"].append(f"{type(exc).__name__}: {exc}")

result["passed"] = sum(1 for value in result["checks"].values() if value is True)
result["total"] = len(result["checks"])
result["failed_checks"] = [key for key, value in result["checks"].items() if value is not True]
result["conclusion"] = "PASS" if not result["failed_checks"] and not result["errors"] else "FAIL"
(OUT / "browser-e2e.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k: result[k] for k in ("passed", "total", "failed_checks", "errors", "conclusion")}, ensure_ascii=False))
