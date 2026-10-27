"""Focused browser contracts for radius-aware map layout and viewport replay."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/frontend/fixtures/literature_map_component.html"
REAL_GRAPH = ROOT / "docs/sdd/plans/043/task-10-runs/20261027-baseline/graph.json"
TARGET_NODE_ID = "065389f0f0b64acda6c5a043cc9b6269"


def _launch(playwright):
    try:
        return playwright.chromium.launch(headless=True)
    except Exception as exc:  # pragma: no cover - host dependent
        pytest.skip(f"真实浏览器阻塞，未将布局检查冒充通过: {type(exc).__name__}: {exc}")


def _real_graph_replay() -> dict:
    graph = json.loads(REAL_GRAPH.read_text(encoding="utf-8"))
    # The isolated fixture exposes the same graph through its mock map route;
    # only the route identity is normalized. Node metadata, positions, edges,
    # viewport and the selected target remain the captured real payload.
    graph["map"]["map_id"] = "map-fixture"
    for node in graph.get("nodes", []):
        node["map_id"] = "map-fixture"
    for edge in graph.get("edges", []):
        edge["map_id"] = "map-fixture"
    if graph.get("latest_job"):
        graph["latest_job"]["map_id"] = "map-fixture"
    return graph


def _open_map(page, replay: dict | None = None, hidden_node_ids: tuple[str, ...] = ()) -> None:
    if replay is not None:
        page.add_init_script(
            "window.__literatureMapReplay = "
            + json.dumps(replay, ensure_ascii=False, separators=(",", ":"))
            + ";"
        )
    page.goto(FIXTURE.as_uri(), wait_until="load")
    if hidden_node_ids:
        selectors = ", ".join(f'[data-node-id="{node_id}"]' for node_id in hidden_node_ids)
        page.add_style_tag(content=f"{selectors} {{ display: none !important; }}")
    map_item = page.locator('[data-map-id="map-fixture"]')
    if not map_item.is_visible():
        page.locator("#literature-map-mobile-list-open").click()
    map_item.click()
    page.wait_for_selector("[data-node-id]")


def _spacing_metrics(page) -> dict:
    return page.locator("[data-node-id] circle").evaluate_all(
        """circles => {
          let minGap = Infinity;
          let limitingPair = null;
          const items = circles.map(circle => ({
            id: circle.parentElement.dataset.nodeId,
            x: Number(circle.getAttribute('cx')),
            y: Number(circle.getAttribute('cy')),
            r: Number(circle.getAttribute('r')),
          }));
          for (let i = 0; i < items.length; i += 1) {
            for (let j = i + 1; j < items.length; j += 1) {
              const a = items[i];
              const b = items[j];
              const gap = Math.hypot(a.x - b.x, a.y - b.y) - a.r - b.r;
              if (gap < minGap) {
                minGap = gap;
                limitingPair = [a.id, b.id, a.r, b.r];
              }
            }
          }
          return { count: items.length, minGap, limitingPair };
        }"""
    )


@pytest.mark.parametrize("count", [20, 30, 50, 200])
def test_new_graph_layout_keeps_radius_aware_clearance_for_mixed_sizes(count: int) -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 900, "height": 720}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?mixed-layout={count}", wait_until="load")
        page.locator('[data-map-id="map-fixture"]').click()
        page.wait_for_selector(f'[data-node-id="node-mixed-{count:03d}"]')
        page.wait_for_function(f"document.querySelectorAll('[data-node-id] circle').length === {count}")
        metrics = _spacing_metrics(page)
        assert metrics["count"] == count
        assert metrics["minGap"] >= 4 * max(metrics["limitingPair"][2:]) + 4, metrics
        assert "间距不足" not in page.locator("#literature-map-status").text_content()
        page.close()
        browser.close()


@pytest.mark.parametrize("width", [1440, 1280, 1180, 900, 390])
def test_real_graph_detail_stays_in_viewport_without_growing_canvas(width: int) -> None:
    page_errors: list[str] = []
    replay = _real_graph_replay()
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        is_mobile = width <= 760
        page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=1,
                                has_touch=is_mobile, is_mobile=is_mobile)
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        _open_map(page, replay)
        page.wait_for_selector(f'[data-node-id="{TARGET_NODE_ID}"]')
        page.wait_for_function(
            """() => {
              const canvas = document.querySelector('.literature-map-canvas');
              const svg = document.querySelector('#literature-map-svg');
              return canvas?.getBoundingClientRect().height > 0
                && svg?.getBoundingClientRect().height > 0;
            }"""
        )
        before = page.evaluate(
            """() => {
              const rect = element => {
                const value = element.getBoundingClientRect();
                return { left: value.left, top: value.top, right: value.right, bottom: value.bottom,
                  width: value.width, height: value.height };
              };
              return {
                canvas: rect(document.querySelector('.literature-map-canvas')),
                svg: rect(document.querySelector('#literature-map-svg')),
                transform: document.querySelector('#literature-map-viewport')?.getAttribute('transform') || '',
                    positions: Object.fromEntries([...document.querySelectorAll('[data-node-id] circle')]
                      .map(circle => [circle.parentElement.dataset.nodeId, [circle.getAttribute('cx'), circle.getAttribute('cy')]])),
              };
            }"""
        )
        target = page.locator(f'[data-node-id="{TARGET_NODE_ID}"] circle')
        target.scroll_into_view_if_needed()
        transform_before = page.locator("#literature-map-viewport").get_attribute("transform") or ""
        if is_mobile:
            target.tap()
        else:
            target.click()
        page.locator(".literature-map-detail-panel.is-open").wait_for(state="visible", timeout=5000)
        page.locator(".literature-map-detail-title").wait_for(state="visible", timeout=5000)
        page.wait_for_timeout(260)
        metrics = page.evaluate(
            """() => {
              const rect = element => {
                const value = element.getBoundingClientRect();
                return { left: value.left, top: value.top, right: value.right, bottom: value.bottom,
                  width: value.width, height: value.height };
              };
              const intersect = (first, second) => {
                const left = Math.max(first.left, second.left);
                const top = Math.max(first.top, second.top);
                const right = Math.min(first.right, second.right);
                const bottom = Math.min(first.bottom, second.bottom);
                return { left, top, right, bottom, width: Math.max(0, right - left), height: Math.max(0, bottom - top) };
              };
              const canvas = document.querySelector('.literature-map-canvas');
              const svg = document.querySelector('#literature-map-svg');
              const detailPanel = document.querySelector('.literature-map-detail-panel');
              const selectedCircle = document.querySelector('[data-node-id].is-selected circle');
              const browserViewport = { left: 0, top: 0, right: window.innerWidth, bottom: window.innerHeight };
              const canvasRect = rect(canvas);
              const svgRect = rect(svg);
              const nodeRect = rect(selectedCircle);
              let visibleMap = intersect(canvasRect, browserViewport);
              const detailRect = rect(detailPanel);
              const detailStyle = window.getComputedStyle(detailPanel);
              const detailOverlaysCanvas = detailPanel.classList.contains('is-open')
                && detailStyle.position === 'fixed'
                && detailRect.left < visibleMap.right && detailRect.right > visibleMap.left
                && detailRect.top < visibleMap.bottom && detailRect.bottom > visibleMap.top;
              if (detailOverlaysCanvas) {
                const candidates = [
                  { left: visibleMap.left, right: visibleMap.right, top: visibleMap.top, bottom: Math.min(visibleMap.bottom, detailRect.top) },
                  { left: visibleMap.left, right: visibleMap.right, top: Math.max(visibleMap.top, detailRect.bottom), bottom: visibleMap.bottom },
                  { left: visibleMap.left, right: Math.min(visibleMap.right, detailRect.left), top: visibleMap.top, bottom: visibleMap.bottom },
                  { left: Math.max(visibleMap.left, detailRect.right), right: visibleMap.right, top: visibleMap.top, bottom: visibleMap.bottom },
                ].filter(area => area.right > area.left && area.bottom > area.top);
                visibleMap = candidates.sort((first, second) =>
                  (second.right - second.left) * (second.bottom - second.top)
                    - (first.right - first.left) * (first.bottom - first.top))[0] || { left: 0, right: 0, top: 0, bottom: 0 };
              }
              visibleMap.width = Math.max(0, visibleMap.right - visibleMap.left);
              visibleMap.height = Math.max(0, visibleMap.bottom - visibleMap.top);
              const inBrowser = intersect(nodeRect, browserViewport);
              const inSvg = intersect(nodeRect, svgRect);
              const inVisibleMap = intersect(nodeRect, visibleMap);
              const hit = document.elementFromPoint(nodeRect.left + nodeRect.width / 2, nodeRect.top + nodeRect.height / 2);
              const circles = [...document.querySelectorAll('[data-node-id] circle')];
              return {
                width: window.innerWidth,
                canvas: canvasRect,
                svg: svgRect,
                detail: { display: detailStyle.display, position: detailStyle.position,
                  open: detailPanel.classList.contains('is-open'), rect: detailRect },
                detailContent: { display: window.getComputedStyle(document.querySelector('#literature-map-detail')).display,
                  scrollHeight: document.querySelector('#literature-map-detail').scrollHeight,
                  clientHeight: document.querySelector('#literature-map-detail').clientHeight },
                transform: document.querySelector('#literature-map-viewport')?.getAttribute('transform') || '',
                nodes: circles.length,
                selected: nodeRect,
                browserIntersection: inBrowser,
                svgIntersection: inSvg,
                visibleMapIntersection: inVisibleMap,
                visibleMap,
                detailOverlaysCanvas,
                hitNodeId: hit?.closest('[data-node-id]')?.dataset.nodeId || null,
                hitTag: hit?.tagName || null,
                title: document.querySelector('.literature-map-detail-title')?.textContent?.trim() || '',
                positions: Object.fromEntries([...circles]
                  .map(circle => [circle.parentElement.dataset.nodeId, [circle.getAttribute('cx'), circle.getAttribute('cy')]])),
              };
            }"""
        )
        before_scale = transform_before.split("scale(", 1)[1].rstrip(")")
        after_scale = metrics["transform"].split("scale(", 1)[1].rstrip(")")
        # Opening details may make the minimum necessary x/y pan, but it must
        # preserve the user's zoom level and the canvas's allocated height.
        assert float(after_scale) == pytest.approx(float(before_scale)), metrics
        assert metrics["detail"]["open"] and metrics["detailContent"]["display"] == "grid", metrics
        assert metrics["title"], metrics
        assert metrics["nodes"] == 21, metrics
        assert metrics["positions"] == before["positions"], metrics
        assert metrics["canvas"]["height"] <= before["canvas"]["height"] + 4, {"before": before, "after": metrics}
        assert metrics["svg"]["height"] <= before["svg"]["height"] + 4, {"before": before, "after": metrics}
        assert metrics["browserIntersection"]["width"] > 0 and metrics["browserIntersection"]["height"] > 0, metrics
        assert metrics["visibleMapIntersection"]["width"] >= min(metrics["selected"]["width"], metrics["visibleMap"]["width"]) - 1, metrics
        assert metrics["visibleMapIntersection"]["height"] >= min(metrics["selected"]["height"], metrics["visibleMap"]["height"]) - 1, metrics
        assert metrics["hitNodeId"] == TARGET_NODE_ID, metrics
        if is_mobile:
            assert metrics["visibleMap"]["width"] >= 300, metrics
            assert metrics["visibleMap"]["height"] >= 150, metrics
            next_node = page.evaluate(
                """({ visibleMap, targetId }) => {
                  for (const circle of document.querySelectorAll('[data-node-id] circle')) {
                    const group = circle.parentElement;
                    if (group.dataset.nodeId === targetId) continue;
                    const rect = circle.getBoundingClientRect();
                    const x = rect.left + rect.width / 2;
                    const y = rect.top + rect.height / 2;
                    if (x < visibleMap.left || x > visibleMap.right || y < visibleMap.top || y > visibleMap.bottom) continue;
                    if (document.elementFromPoint(x, y)?.closest('[data-node-id]')?.dataset.nodeId === group.dataset.nodeId) {
                      return { id: group.dataset.nodeId, x, y };
                    }
                  }
                  return null;
                }""",
                {"visibleMap": metrics["visibleMap"], "targetId": TARGET_NODE_ID},
            )
            assert next_node, metrics
            page.locator(f'[data-node-id="{next_node["id"]}"] circle').tap()
            page.wait_for_function(
                f"document.querySelector('[data-node-id=\\\"{next_node['id']}\\\"].is-selected') !== null",
                timeout=5000,
            )
        assert page_errors == [], page_errors
        print(json.dumps({"width": width, "before": before, "after": metrics, "pageerror": page_errors}, ensure_ascii=False))
        page.close()
        browser.close()


def test_old_graph_spacing_preview_is_write_free_until_explicit_confirmation() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=1)
        _open_map(page)
        page.wait_for_selector('[data-node-id="node-b"]')
        before = page.locator("[data-node-id] circle").evaluate_all(
            "nodes => Object.fromEntries(nodes.map(node => [node.parentElement.dataset.nodeId, [node.getAttribute('cx'), node.getAttribute('cy')]]))"
        )
        transform_before = page.locator("#literature-map-viewport").get_attribute("transform")
        page.get_by_role("button", name="预览整理间距").click()
        page.wait_for_selector("#literature-map-spacing-preview-confirm")
        page.wait_for_timeout(650)
        assert page.evaluate("window.__viewBodies") == []
        preview = page.locator("[data-node-id] circle").evaluate_all(
            "nodes => Object.fromEntries(nodes.map(node => [node.parentElement.dataset.nodeId, [node.getAttribute('cx'), node.getAttribute('cy')]]))"
        )
        assert preview != before
        assert page.locator("#literature-map-viewport").get_attribute("transform") == transform_before
        page.get_by_role("button", name="取消").last.click()
        assert page.locator("[data-node-id] circle").evaluate_all(
            "nodes => Object.fromEntries(nodes.map(node => [node.parentElement.dataset.nodeId, [node.getAttribute('cx'), node.getAttribute('cy')]]))"
        ) == before
        assert page.evaluate("window.__viewBodies") == []

        page.locator("#literature-map-label-mode").select_option("hidden")
        page.get_by_role("button", name="预览整理间距").click()
        page.get_by_role("button", name="确认保存").click()
        page.wait_for_function("window.__viewBodies.length === 1")
        body = page.evaluate("window.__viewBodies[0]")
        assert body["expected_revision"] == 3
        assert {item["node_id"] for item in body["positions"]} == {"node-a", "node-b"}
        assert page.locator("#literature-map-spacing-preview-panel").get_attribute("hidden") is not None
        page.close()
        browser.close()


def test_spacing_preview_conflict_keeps_preview_and_does_not_fake_save() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?view-conflict", wait_until="load")
        page.locator('[data-map-id="map-fixture"]').click()
        page.wait_for_selector('[data-node-id="node-b"]')
        page.get_by_role("button", name="预览整理间距").click()
        page.get_by_role("button", name="确认保存").click()
        page.wait_for_function("document.querySelector('#literature-map-status')?.textContent.includes('版本已变化')")
        assert page.evaluate("window.__viewBodies") == []
        assert page.locator("#literature-map-spacing-preview-confirm").is_visible()
        assert page.locator("#literature-map-spacing-preview-state").text_content() and '预览仍保留' in page.locator("#literature-map-spacing-preview-state").text_content()
        page.get_by_role("button", name="取消").last.click()
        assert page.evaluate("window.__viewBodies") == []
        page.close()
        browser.close()


def test_existing_graph_spacing_warning_is_read_only_and_counts_hidden_active_nodes() -> None:
    replay = _real_graph_replay()
    nodes = replay["nodes"]
    assert len(nodes) >= 3
    hidden_node_id = nodes[2]["node_id"]
    for index, node in enumerate(nodes):
        node["position"] = {"x": 300, "y": 300} if index < 3 else {"x": 2000 + index * 500, "y": 2000}
    nodes[2]["hidden"] = True
    original_positions = {node["node_id"]: dict(node["position"]) for node in nodes}

    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=1)
        _open_map(page, replay, hidden_node_ids=(hidden_node_id,))
        page.wait_for_selector("[data-node-id]")
        page.wait_for_function("document.querySelector('#literature-map-status')?.textContent.includes('间距不足')", timeout=5000)
        status = page.locator("#literature-map-status").text_content() or ""
        assert "3对" in status and "整理间距" in status, status
        assert page.locator(f'[data-node-id="{hidden_node_id}"]').evaluate("node => getComputedStyle(node).display") == "none"
        actual_positions = page.locator("[data-node-id] circle").evaluate_all(
            "nodes => Object.fromEntries(nodes.map(circle => [circle.parentElement.dataset.nodeId, {x:Number(circle.getAttribute('cx')), y:Number(circle.getAttribute('cy'))}]))"
        )
        assert actual_positions == original_positions
        page.wait_for_timeout(650)
        assert page.evaluate("window.__viewBodies") == []
        page.close()
        browser.close()


def test_existing_graph_spacing_check_ignores_removed_overlaps() -> None:
    replay = _real_graph_replay()
    nodes = replay["nodes"]
    assert nodes
    for index, node in enumerate(nodes):
        node["position"] = {"x": index * 500, "y": 0}
    overlap_position = dict(nodes[0]["position"])
    replay["nodes"].extend([
        {"node_id": "removed-overlap", "removed": True, "position": overlap_position},
        {"node_id": "tombstone-overlap", "tombstone": True, "position": dict(overlap_position)},
    ])

    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=1)
        _open_map(page, replay)
        page.wait_for_selector("[data-node-id]")
        page.wait_for_function(
            "['地图已打开', '地图部分完成', '间距不足'].some(message => document.querySelector('#literature-map-status')?.textContent.includes(message))",
            timeout=5000,
        )
        assert "间距不足" not in (page.locator("#literature-map-status").text_content() or "")
        page.close()
        browser.close()


def test_zero_sized_canvas_does_not_persist_viewport() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=1)
        _open_map(page)
        page.locator("#literature-map-svg").evaluate("node => { node.style.display = 'none'; }")
        page.get_by_role("button", name="重置视图").click()
        page.wait_for_timeout(650)
        assert page.evaluate("window.__viewBodies") == []
        page.locator("#literature-map-svg").evaluate("node => { node.style.display = ''; }")
        page.wait_for_timeout(120)
        page.close()
        browser.close()
