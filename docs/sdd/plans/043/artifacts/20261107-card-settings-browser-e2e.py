"""Spec043 卡片设置列表：真实 Chromium 1440x900 / 760x900 端到端验收脚本。

可复现：cd 项目根目录后执行
  ./.venv/bin/python docs/sdd/plans/043/artifacts/20261107-card-settings-browser-e2e.py
产物：同目录 20261107-card-settings-browser-e2e.json 与 6 张 PNG 截图。
脚本会自行创建并删除一张测试地图，不触碰用户既有地图。
"""

import datetime
import json
import sys
import traceback
import urllib.error
import urllib.request
import uuid

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
VIEW = BASE + "/#literature-maps-view"
DIR = "docs/sdd/plans/043/artifacts/"
PREFIX = "20261107-card-settings-"
ART = DIR + "20261107-card-settings-browser-e2e.json"

checks, steps, shots, page_errors = {}, [], [], []


def api(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            raw, status = r.read().decode(), r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read().decode(), e.code
    return status, (json.loads(raw) if raw.strip() else None)


def shot(page, name):
    path = DIR + PREFIX + name + ".png"
    page.screenshot(path=path)
    shots.append(path)


def mbox(page):
    loc = page.locator(".literature-map-card-menu")
    loc.wait_for(state="visible", timeout=10000)
    return loc.bounding_box()


def open_menu(page, card):
    card.locator(".literature-map-card-menu-trigger").click()
    page.locator(".literature-map-card-menu-settings").wait_for(state="visible", timeout=10000)


def in_viewport(box, width=760, height=900):
    return bool(
        box
        and box["x"] >= 0
        and box["y"] >= 0
        and box["x"] + box["width"] <= width
        and box["y"] + box["height"] <= height
    )


OVERLAP_JS = """(cardId) => {
  const card = document.querySelector('[data-map-id="' + cardId + '"]');
  const trigger = card && card.querySelector('.literature-map-card-menu-trigger');
  if (!card || !trigger) return {ok: false, hits: ['missing element']};
  const t = trigger.getBoundingClientRect();
  const leaves = [...card.querySelectorAll('*')].filter(
    (el) => el !== trigger && !trigger.contains(el) && el.children.length === 0 && el.textContent.trim()
  );
  const hits = leaves.filter((el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 &&
      !(r.right <= t.left || t.right <= r.left || r.bottom <= t.top || t.bottom <= r.top);
  }).map((el) => el.textContent.trim().slice(0, 24));
  return {ok: hits.length === 0, hits};
}"""


def main():
    key = "ui-card-settings-" + uuid.uuid4().hex[:8]
    name0 = "E2E 浏览器卡片设置 " + key
    status, created = api(
        "POST",
        "/api/literature-maps",
        {"topic": "browser card settings probe", "name": name0, "limit": 20, "idempotency_key": key},
    )
    checks["test_map_created_202"] = status == 202
    map_id = created["map_id"]
    entities = {
        "map_id": map_id,
        "initial_name": name0,
        "initial_revision": created["map"]["revision"],
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: page_errors.append(str(e)[:300]))
        page.goto(VIEW, wait_until="domcontentloaded")
        card = page.locator(f'[data-map-id="{map_id}"]')
        card.wait_for(state="visible", timeout=30000)
        checks["test_map_card_visible"] = True

        # ① 一级「卡片设置」列表
        open_menu(page, card)
        entries = page.locator(".literature-map-card-menu-entry").all_text_contents()
        checks["level1_exactly_three_items"] = entries == ["设置标签", "重命名地图", "删除地图"]
        aria = card.locator(".literature-map-card-menu-trigger").get_attribute("aria-label")
        checks["trigger_aria_renamed"] = bool(aria and aria.startswith("卡片设置："))
        checks["no_export_in_menu"] = "导出" not in "".join(entries)
        box1 = mbox(page)
        steps.append({"step": "1440 一级设置列表 box", "value": box1})
        shot(page, "01-settings-list-1440")

        # ② 二级标签面板 + Esc 两级回退 + 返回 + 外部点击
        page.locator('.literature-map-card-menu-entry[data-action="tags"]').click()
        page.locator(".literature-map-card-menu-view-tags").wait_for(state="visible", timeout=10000)
        checks["level2_tags_panel"] = True
        checks["back_button_present"] = page.locator(".literature-map-card-menu-back").inner_text() == "← 返回"
        box2 = mbox(page)
        checks["tags_panel_width_le_200"] = bool(box2 and box2["width"] <= 200)
        checks["tags_panel_width_is_200"] = bool(box2 and abs(box2["width"] - 200) <= 1)
        checks["tags_panel_empty_height_le_105"] = bool(box2 and box2["height"] <= 105)
        tag_count = len((api("GET", "/api/literature-maps/tags")[1] or {}).get("tags", []))
        steps.append({"step": "1440 二级标签面板 box", "value": box2, "global_tag_count": tag_count})
        shot(page, "02-tags-panel-1440")

        page.keyboard.press("Escape")
        page.locator(".literature-map-card-menu-settings").wait_for(state="visible", timeout=10000)
        checks["esc_level2_to_level1"] = True
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        checks["esc_level1_closes"] = page.locator(".literature-map-card-menu").count() == 0

        open_menu(page, card)
        page.locator('.literature-map-card-menu-entry[data-action="tags"]').click()
        page.locator(".literature-map-card-menu-back").click()
        checks["back_returns_to_level1"] = page.locator(".literature-map-card-menu-settings").count() == 1
        page.mouse.click(2, 2)
        page.wait_for_timeout(200)
        checks["outside_click_closes"] = page.locator(".literature-map-card-menu").count() == 0

        # ③ 重命名（真实 PATCH，只带 expected_revision + name）
        new_name = "E2E 浏览器已重命名 " + key
        open_menu(page, card)
        page.locator('.literature-map-card-menu-entry[data-action="rename"]').click()
        page.locator(".literature-map-card-menu-view-rename").wait_for(state="visible", timeout=10000)
        inp = page.locator('.literature-map-card-menu-mapform input[type="text"]')
        checks["rename_prefilled"] = inp.input_value() == name0
        shot(page, "03-rename-form")
        inp.fill(new_name)
        page.locator(".literature-map-card-menu-submit").click()
        page.wait_for_function(
            "() => document.querySelector('#literature-map-status')?.textContent.includes('地图已重命名')",
            timeout=20000,
        )
        checks["rename_status_success"] = True
        page.wait_for_function(
            "(a) => { const c=document.querySelector('[data-map-id=\"'+a.id+'\"]'); return c && c.textContent.includes(a.name); }",
            arg={"id": map_id, "name": new_name},
            timeout=15000,
        )
        checks["rename_updates_card_title"] = True
        _, got = api("GET", "/api/literature-maps/" + map_id)
        checks["rename_persisted_backend"] = got["map"]["name"] == new_name
        entities["renamed_name"] = new_name
        entities["revision_after_rename"] = got["map"]["revision"]

        # ④ 构造 409：外部推进 revision（名字不变），页面本地仍持旧值
        _, ext = api(
            "PATCH",
            "/api/literature-maps/" + map_id,
            {"expected_revision": got["map"]["revision"], "name": new_name},
        )
        checks["external_revision_bump_200"] = bool(ext and ext["map"]["revision"] > got["map"]["revision"])
        entities["revision_after_external_bump"] = ext["map"]["revision"]
        open_menu(page, card)
        page.locator('.literature-map-card-menu-entry[data-action="rename"]').click()
        page.locator('.literature-map-card-menu-mapform input[type="text"]').fill("E2E 冲突重试 " + key)
        page.locator(".literature-map-card-menu-submit").click()
        page.wait_for_function(
            "() => document.querySelector('#literature-map-status')?.textContent.includes('地图已在别处更新')",
            timeout=20000,
        )
        checks["stale_revision_shows_dedicated_notice"] = True
        steps.append({"step": "409 状态提示", "value": page.locator("#literature-map-status").inner_text()})
        page.keyboard.press("Escape")

        # ⑤ 删除二次确认：取消零请求 → 确认后卡片与后端都消失
        page.reload(wait_until="domcontentloaded")
        card = page.locator(f'[data-map-id="{map_id}"]')
        card.wait_for(state="visible", timeout=30000)
        open_menu(page, card)
        page.locator('.literature-map-card-menu-entry[data-action="delete"]').click()
        page.locator(".literature-map-card-menu-view-delete").wait_for(state="visible", timeout=10000)
        checks["confirm_shows_map_name"] = new_name in page.locator(".literature-map-card-menu-confirm-name").inner_text()
        checks["confirm_shows_irreversible"] = "删除后不可恢复" in page.locator(".literature-map-card-menu-hint").inner_text()
        shot(page, "04-delete-confirm")
        page.locator(".literature-map-card-menu-cancel").click()
        checks["cancel_returns_to_level1"] = page.locator(".literature-map-card-menu-settings").count() == 1
        status_after_cancel, _ = api("GET", "/api/literature-maps/" + map_id)
        checks["cancel_sent_no_delete"] = status_after_cancel == 200
        page.locator('.literature-map-card-menu-entry[data-action="delete"]').click()
        page.locator(".literature-map-card-menu-view-delete").wait_for(state="visible", timeout=10000)
        page.locator(".literature-map-card-menu-confirm").click()
        page.wait_for_function(
            "(id) => !document.querySelector('[data-map-id=\"'+id+'\"]')", arg=map_id, timeout=25000
        )
        checks["confirm_removes_card"] = True
        _, listed = api("GET", "/api/literature-maps")
        checks["confirm_persisted_backend_delete"] = map_id not in [m["map_id"] for m in listed["maps"]]
        steps.append({"step": "删除后状态提示", "value": page.locator("#literature-map-status").inner_text()})

        # ⑥ 760px 视口：用列表首张卡片测量（不删除）
        page.set_viewport_size({"width": 760, "height": 900})
        page.reload(wait_until="domcontentloaded")
        # 760px 下地图列表默认折叠，须先点「地图列表」按钮展开，卡片才可见。
        page.locator("#literature-map-mobile-list-open").click()
        page.wait_for_timeout(300)
        page.wait_for_selector(".literature-map-card-menu-trigger", state="visible", timeout=30000)
        first_card = page.locator("[data-map-id]").first
        first_id = first_card.get_attribute("data-map-id")
        trig = first_card.locator(".literature-map-card-menu-trigger").bounding_box()
        checks["760_trigger_44px"] = bool(trig and trig["width"] >= 44 and trig["height"] >= 44)
        steps.append({"step": "760 触发器 box", "value": trig})
        overlap = page.evaluate(OVERLAP_JS, first_id)
        checks["760_trigger_does_not_cover_text"] = bool(overlap["ok"])
        steps.append({"step": "760 触发器与卡片文本重叠", "value": overlap})

        open_menu(page, first_card)
        b1 = mbox(page)
        checks["760_level1_in_viewport"] = in_viewport(b1)
        steps.append({"step": "760 一级列表 box", "value": b1})
        shot(page, "05-settings-list-760")
        page.locator('.literature-map-card-menu-entry[data-action="tags"]').click()
        page.locator(".literature-map-card-menu-view-tags").wait_for(state="visible", timeout=10000)
        b2 = mbox(page)
        checks["760_level2_in_viewport"] = in_viewport(b2)
        checks["760_tags_panel_width_le_200"] = bool(b2 and b2["width"] <= 200)
        checks["760_tags_panel_width_is_200"] = bool(b2 and abs(b2["width"] - 200) <= 1)
        steps.append({"step": "760 二级标签面板 box", "value": b2})
        shot(page, "06-tags-panel-760")
        browser.close()
    return entities


if __name__ == "__main__":
    out_entities = {}
    try:
        out_entities = main()
    except Exception:
        checks["browser_exception"] = False
        steps.append({"step": "EXCEPTION", "value": traceback.format_exc()[-1600:]})
    finally:
        artifact = {
            "timestamp": datetime.datetime.now().isoformat(),
            "base_url": BASE,
            "view": VIEW,
            "purpose": "Spec043 卡片设置列表：真实 Chromium 1440x900 / 760x900 端到端验收",
            "entities": out_entities,
            "checks": checks,
            "steps": steps,
            "screenshots": shots,
            "page_errors": page_errors,
            "artifact_path": ART,
        }
        with open(ART, "w", encoding="utf-8") as f:
            json.dump(artifact, f, ensure_ascii=False, indent=2)
        print("CHECKS:", json.dumps(checks, ensure_ascii=False))
        print("BOXES:", json.dumps([s for s in steps if "box" in s["step"]], ensure_ascii=False))
        print("SCREENSHOTS:", len(shots), "PAGE_ERRORS:", page_errors[:3])
        bad = [k for k, v in checks.items() if v is not True]
        print("ALL_GREEN:", not bad, "NOT_TRUE:", bad, "ARTIFACT:", ART)
        sys.exit(0 if not bad else 1)
