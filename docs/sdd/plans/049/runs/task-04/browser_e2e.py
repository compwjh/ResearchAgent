"""Spec-049 / task-04 运行时验证：真实 Chromium + 真实 API 端到端验证与证据落盘。

运行：.venv/bin/python docs/sdd/plans/049/runs/task-04/browser_e2e.py
产物：browser-e2e.json、refresh-desktop.png、refresh-mobile.png
仅新建证据文件，不改 spec / 业务代码 / 测试 / 台账 / 评审文档。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8000"
HASH_VIEW = BASE + "/#literature-maps-view"
MAPS_API = "/api/literature-maps"

result: dict = {
    "spec": "049",
    "task": "04",
    "base": BASE,
    "checks": {},
    "api": [],
    "assets": [],
    "console_errors": [],
    "page_errors": [],
    "errors": [],
    "spin_timeline": {},
    "multi_click": {},
    "entity_ids": {},
    "homepage": {},
    "known_limitations": [],
}


def record(page, label, api_sink):
    def _on_response(response):
        url = response.url
        if "/api/" in url:
            try:
                body = response.text()[:300]
            except Exception:
                body = ""
            entry = {"page": label, "url": url, "status": response.status, "body": body}
            result["api"].append(entry)
            api_sink.append(entry)
        if "/assets/literature-maps." in url:
            result["assets"].append({"page": label, "url": url, "status": response.status})

    page.on("response", _on_response)


def watch_errors(page, label):
    def _on_console(msg):
        if msg.type == "error":
            result["console_errors"].append({"page": label, "text": msg.text})

    def _on_pageerror(exc):
        text = str(exc)
        result["page_errors"].append({"page": label, "text": text})
        result["errors"].append({"kind": "pageerror", "page": label, "text": text})

    page.on("console", _on_console)
    page.on("pageerror", _on_pageerror)


def open_maps(page):
    """hash 路由进入文献地图；窄屏侧栏折叠时回退为 DOM click 触发同一导航处理。"""
    page.goto(HASH_VIEW, wait_until="load", timeout=30000)
    try:
        page.wait_for_selector("#literature-map-main-tabs", timeout=8000)
    except Exception:
        page.evaluate('() => document.querySelector(\'[data-view="literature-maps"]\')?.click()')
        page.wait_for_selector("#literature-map-main-tabs", timeout=15000)
    return page


def inject_spin_observer(page):
    """MutationObserver 被动记录 is-spinning 的 add / remove（performance.now 时钟）。"""
    page.evaluate(
        """() => {
          const btn = document.querySelector('#literature-map-refresh-button');
          window.__spinEvents = [];
          if (window.__spinObs) window.__spinObs.disconnect();
          window.__spinObs = new MutationObserver(() => {
            window.__spinEvents.push({
              t: performance.now(),
              spinning: btn.classList.contains('is-spinning')
            });
          });
          window.__spinObs.observe(btn, { attributes: true, attributeFilter: ['class'] });
        }"""
    )


def spin_events(page):
    return page.evaluate("() => window.__spinEvents || []")


def trigger_click(page, force_dom=False):
    loc = page.locator("#literature-map-refresh-button")
    if force_dom:
        loc.dispatch_event("click")
        return "dispatch_event"
    loc.click(timeout=10000)
    return "locator.click"


def click_refresh_and_wait(page, label, api_sink, force_dom=False):
    inject_spin_observer(page)
    before = len(api_sink)
    before_maps = len([1 for e in api_sink if MAPS_API in e["url"]])
    with page.expect_response(lambda r: MAPS_API in r.url, timeout=15000) as ri:
        t_click = time.monotonic()
        method = trigger_click(page, force_dom=force_dom)
    resp = ri.value
    page.wait_for_function(
        "() => !document.querySelector('#literature-map-refresh-button').classList.contains('is-spinning')",
        timeout=15000,
    )
    t_removed = time.monotonic()
    evs = spin_events(page)
    adds = [e for e in evs if e["spinning"]]
    rems = [e for e in evs if not e["spinning"]]
    tl = {
        "label": label,
        "click_method": method,
        "api_url": resp.url,
        "api_status": resp.status,
        "elapsed_ms": round((t_removed - t_click) * 1000, 2),
        "spin_add_events": len(adds),
        "spin_remove_events": len(rems),
        "api_responses_after_click": len(api_sink) - before,
        "maps_api_responses_after_click": len([1 for e in api_sink if MAPS_API in e["url"]]) - before_maps,
    }
    if adds and rems:
        tl["spin_duration_ms_js"] = round(rems[-1]["t"] - adds[0]["t"], 2)
    return tl


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # ---------- 桌面 1440x900 ----------
        desktop = browser.new_page(viewport={"width": 1440, "height": 900})
        desktop_sink: list = []
        record(desktop, "desktop", desktop_sink)
        watch_errors(desktop, "desktop")
        open_maps(desktop)

        c = result["checks"]
        c["desktop_view_hash_route"] = "#literature-maps-view" in desktop.url
        c["tabs_present"] = desktop.locator("#literature-map-main-tabs").count() == 1
        refresh = desktop.locator("#literature-map-refresh-button")
        c["refresh_button_exists"] = refresh.count() == 1
        c["refresh_no_visible_text"] = refresh.inner_text().strip() == ""
        c["refresh_aria_label"] = refresh.get_attribute("aria-label") == "刷新状态"
        c["refresh_title_unchanged"] = refresh.get_attribute("title") == "重新读取地图和作业状态"
        c["refresh_icon_node"] = refresh.locator(".literature-map-refresh-icon").count() == 1

        # 轮 A：无干预，测量当前部署的真实旋转耗时
        native_tl = click_refresh_and_wait(desktop, "desktop-native", desktop_sink)
        result["spin_timeline"]["desktop_native"] = native_tl

        # 轮 B：CDP 250ms 延迟，测量慢响应下的旋转耗时（跟随 Promise 而非固定 700ms）
        cdp = None
        try:
            cdp = desktop.context.new_cdp_session(desktop)
            cdp.send("Network.enable")
            cdp.send("Network.emulateNetworkConditions", {
                "offline": False, "latency": 250,
                "downloadThroughput": -1, "uploadThroughput": -1,
            })
            result["cdp_throttle_ms"] = 250
        except Exception as exc:
            result["known_limitations"].append(f"CDP 网络节流未生效：{type(exc).__name__}: {exc}")

        throttled_tl = click_refresh_and_wait(desktop, "desktop-throttled-250ms", desktop_sink)
        result["spin_timeline"]["desktop_throttled"] = throttled_tl

        if cdp is not None:
            try:
                cdp.send("Network.emulateNetworkConditions", {
                    "offline": False, "latency": 0,
                    "downloadThroughput": -1, "uploadThroughput": -1,
                })
            except Exception as exc:
                result["known_limitations"].append(f"CDP 节流复位失败：{type(exc).__name__}: {exc}")

        c["spin_added_on_click"] = (
            native_tl["spin_add_events"] >= 1 and throttled_tl["spin_add_events"] >= 1
        )
        c["refresh_triggers_maps_api"] = (
            native_tl["maps_api_responses_after_click"] >= 1
            and throttled_tl["maps_api_responses_after_click"] >= 1
        )
        c["api_literature_maps_chain"] = (
            MAPS_API in native_tl["api_url"] and MAPS_API in throttled_tl["api_url"]
        )
        c["spin_removed_after_response"] = (
            native_tl["spin_remove_events"] >= 1 and throttled_tl["spin_remove_events"] >= 1
        )
        c["spin_not_fixed_700ms"] = (
            abs(native_tl["elapsed_ms"] - 700) > 100
            and abs(throttled_tl["elapsed_ms"] - 700) > 100
        )
        c["spin_duration_matches_promise"] = all(
            "spin_duration_ms_js" in tl and abs(tl["spin_duration_ms_js"] - tl["elapsed_ms"]) < 500
            for tl in (native_tl, throttled_tl)
        )

        status_loc = desktop.locator("#literature-map-status")
        status_text = (status_loc.text_content() or "").strip() if status_loc.count() else ""
        result["status_bar_after_refresh"] = status_text
        c["status_bar_nonempty"] = bool(status_text)

        # 连点 3 次：每次真实 API 响应 + 最终残留 0
        multi = {"clicks": 3, "responses": []}
        for _ in range(3):
            with desktop.expect_response(lambda r: MAPS_API in r.url, timeout=15000) as ri:
                trigger_click(desktop)
            multi["responses"].append({"url": ri.value.url, "status": ri.value.status})
        desktop.wait_for_function(
            "() => document.querySelectorAll('#literature-map-refresh-button.is-spinning').length === 0",
            timeout=15000,
        )
        multi["spin_residue"] = desktop.evaluate(
            "() => document.querySelectorAll('#literature-map-refresh-button.is-spinning').length"
        )
        result["multi_click"] = multi
        c["multi_click_3_real_requests"] = len(multi["responses"]) == 3
        c["multi_click_no_spin_residue"] = multi["spin_residue"] == 0

        c["live_js_v49_200"] = any(
            "literature-maps.js?v=49" in a["url"] and a["status"] == 200
            for a in result["assets"]
        )
        c["live_css_v36_200"] = any(
            "literature-maps.css?v=36" in a["url"] and a["status"] == 200
            for a in result["assets"]
        )
        c["marker_v47_not_loaded"] = not any(
            "literature-maps.js?v=47" in a["url"] for a in result["assets"]
        )
        c["marker_v34_not_loaded"] = not any(
            "literature-maps.css?v=34" in a["url"] for a in result["assets"]
        )

        desktop.screenshot(path=str(OUT / "refresh-desktop.png"), full_page=False)

        # ---------- 窄屏 375x812 ----------
        mobile = browser.new_page(viewport={"width": 375, "height": 812})
        mobile_sink: list = []
        record(mobile, "mobile", mobile_sink)
        watch_errors(mobile, "mobile")
        open_maps(mobile)

        c["mobile_view_hash_route"] = "#literature-maps-view" in mobile.url
        mobile_refresh = mobile.locator("#literature-map-refresh-button")
        box = mobile_refresh.bounding_box()
        result["mobile_refresh_box"] = box
        c["mobile_touch_target_ge_44"] = bool(box and box["height"] >= 44)
        c["mobile_no_visible_text"] = mobile_refresh.inner_text().strip() == ""

        mobile_tl = click_refresh_and_wait(
            mobile, "mobile-refresh", mobile_sink, force_dom=True
        )
        result["spin_timeline"]["mobile"] = mobile_tl
        c["mobile_spin_ends"] = (
            mobile_tl["spin_add_events"] >= 1
            and mobile_tl["spin_remove_events"] >= 1
        )
        c["mobile_no_visible_text_residue"] = mobile_refresh.inner_text().strip() == ""
        c["mobile_no_spin_residue"] = mobile.evaluate(
            "() => document.querySelectorAll('#literature-map-refresh-button.is-spinning').length"
        ) == 0

        mobile.screenshot(path=str(OUT / "refresh-mobile.png"), full_page=False)
        browser.close()

    # ---------- 首页 HTML：live script/link 与末尾 marker ----------
    with urlopen(BASE + "/", timeout=10) as r:
        html = r.read().decode("utf-8", "replace")
        result["homepage"]["status"] = r.status
    live_js = re.findall(r'<script[^>]*src="([^"]*literature-maps\.js\?v=\d+)"', html)
    live_css = re.findall(r'<link[^>]*href="([^"]*literature-maps\.css\?v=\d+)"', html)
    js_versions = re.findall(r"literature-maps\.js\?v=(\d+)", html)
    css_versions = re.findall(r"literature-maps\.css\?v=(\d+)", html)
    marker_lines = [
        line.strip() for line in html.splitlines()
        if "compatibility marker" in line and "literature-maps" in line
    ]
    result["homepage"]["live_script"] = live_js
    result["homepage"]["live_link"] = live_css
    result["homepage"]["last_js_marker"] = js_versions[-1] if js_versions else None
    result["homepage"]["last_css_marker"] = css_versions[-1] if css_versions else None
    result["homepage"]["marker_comment_lines"] = marker_lines
    c["homepage_live_v49_v36"] = bool(
        live_js and live_js[0].endswith("v=49")
        and live_css and live_css[0].endswith("v=36")
    )
    c["homepage_marker_47_34_last"] = (
        js_versions[-1] == "47" and css_versions[-1] == "34"
    ) if js_versions and css_versions else False

    # ---------- 直接 HTTP（curl 等价）：真实响应入 api 列表，含实体 ID ----------
    for path in ("/api/health", "/api/literature-maps/tags", "/api/projects"):
        with urlopen(BASE + path, timeout=10) as r:
            body = r.read().decode("utf-8", "replace")
            result["api"].append({
                "page": "direct-http",
                "url": BASE + path,
                "status": r.status,
                "body": body[:300],
            })

    pat = re.compile(r'"(project_id|schema_version|map_id|session_id|job_id)"\s*:\s*"([^"]+)"')
    ids: dict = {}
    for entry in result["api"]:
        for key, value in pat.findall(entry["body"]):
            ids.setdefault(key, [])
            if value not in ids[key]:
                ids[key].append(value)
    result["entity_ids"] = ids
    c["api_entity_id_present"] = any(ids.values())

    # ---------- 错误判定 ----------
    unhandled = 0
    for e in result["page_errors"] + result["console_errors"]:
        text = e["text"].lower()
        if "unhandled" in text or "rejection" in text or "uncaught (in promise)" in text:
            unhandled += 1
    result["unhandled_rejection_count"] = unhandled
    c["no_unhandled_rejection"] = unhandled == 0
    c["no_pageerror"] = len(result["page_errors"]) == 0
    if result["console_errors"]:
        result["known_limitations"].append(
            f"console.error 共 {len(result['console_errors'])} 条，明细见 console_errors"
        )


try:
    run()
except Exception as exc:
    result["errors"].append(f"{type(exc).__name__}: {exc}")

result["passed"] = sum(1 for v in result["checks"].values() if v is True)
result["total"] = len(result["checks"])
result["failed_checks"] = [k for k, v in result["checks"].items() if v is not True]
result["conclusion"] = "PASS" if not result["failed_checks"] and not result["errors"] else "FAIL"
(OUT / "browser-e2e.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(
    {k: result[k] for k in ("passed", "total", "failed_checks", "errors", "conclusion")},
    ensure_ascii=False,
))
