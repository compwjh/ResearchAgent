"""Isolated, synthetic SVG feasibility checks for the literature-map MVP.

This module deliberately does not import or exercise the production frontend.
The browser test opens the fixture directly from ``file://`` so that the
evidence measures the proposed SVG interaction boundary without starting an
application server or making network requests.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/frontend/fixtures/literature_map_performance.html"
ARTIFACTS = ROOT / "docs/sdd/plans/043/artifacts/task-02"
SCREENSHOT = ARTIFACTS / "screenshots/literature-map-200-nodes.png"
HIGH_SCREENSHOT = ARTIFACTS / "screenshots/literature-map-200-nodes-high-load.png"
EVIDENCE = ARTIFACTS / "browser-evidence.json"


def test_fixture_is_framework_free_and_has_a_bounded_sparse_graph() -> None:
    source = FIXTURE.read_text(encoding="utf-8")

    assert "<svg" in source
    assert 'id="literature-map"' in source
    assert "NODE_COUNT = 200" in source
    assert "requestAnimationFrame" in source
    assert "MAX_LAYOUT_ITERATIONS = 8" in source
    assert "HIGH_PROFILE_EDGE_COUNT = 620" in source
    assert 'get("profile") === "high"' in source
    assert "<script src=" not in source
    assert "react" not in source.lower()
    assert "vue" not in source.lower()
    assert "innerHTML" not in source
    assert "textContent" in source
    assert 'data-edge-kind="citation"' in source
    assert 'data-edge-kind="similarity"' in source


def test_fixture_contract_exposes_svg_interaction_boundaries() -> None:
    source = FIXTURE.read_text(encoding="utf-8")

    for marker in (
        'id="zoom-in"',
        'id="zoom-out"',
        'id="fit-map"',
        'id="literature-map"',
        "pointerdown",
        "pointermove",
        "pointerup",
        "selectNode",
        "scheduleViewRender",
        "scheduleNodeRender",
        "PerformanceObserver",
    ):
        assert marker in source

    assert "labelsRendered" in source
    assert "layoutIterations" in source
    assert "interactionDurations" in source
    assert "gestureWallDurations" in source
    assert "renderWallDurations" in source
    assert "maxFrameDurationMs" in source
    assert "longTaskSupported" in source


def _open_browser_or_skip(playwright):
    try:
        return playwright.chromium.launch(headless=True)
    except Exception as exc:  # pragma: no cover - depends on host permissions
        pytest.skip(f"真实浏览器阻塞，未将静态检查冒充性能通过: {type(exc).__name__}: {exc}")


def _load_profile(page, profile: str) -> None:
    suffix = "?profile=high" if profile == "high" else ""
    page.goto(f"{FIXTURE.as_uri()}{suffix}", wait_until="load")
    page.wait_for_function("window.__mapReady === true")
    # Yield to the browser for a bounded interval so the heavier profile can
    # finish its eight RAFs without relying on a RAF-polled wait predicate that
    # may starve headless macOS pages. The caller asserts the observed count.
    page.wait_for_timeout(1000)


def _read_graph(page) -> dict:
    return page.evaluate(
        """() => ({
            nodeCount: document.querySelectorAll('[data-node-id]').length,
            edgeCount: document.querySelectorAll('[data-edge-kind]').length,
            citationEdges: document.querySelectorAll('[data-edge-kind="citation"]').length,
            similarityEdges: document.querySelectorAll('[data-edge-kind="similarity"]').length,
            labelCount: document.querySelectorAll('#nodes text').length,
            metrics: window.__mapMetrics.snapshot(),
        })"""
    )


def _exercise_interactions(page, profile: str) -> dict:
    initial = _read_graph(page)
    assert initial["nodeCount"] == 200
    if profile == "high":
        assert initial["edgeCount"] == 620
        assert initial["citationEdges"] >= 300
        assert initial["similarityEdges"] >= 300
    else:
        assert initial["edgeCount"] == 34
        assert initial["edgeCount"] < initial["nodeCount"]
    assert initial["citationEdges"] > 0
    assert initial["similarityEdges"] > 0
    assert 0 < initial["labelCount"] <= 10
    assert initial["metrics"]["layoutIterations"] == 8
    assert initial["metrics"]["layoutRafCount"] <= 8
    assert initial["metrics"]["longTaskSupported"] is True

    initial_view = page.evaluate("window.__mapMetrics.snapshot()")
    page.get_by_role("button", name="放大").click()
    page.wait_for_timeout(50)
    after_zoom = page.evaluate("window.__mapMetrics.snapshot()")
    assert after_zoom["zoom"] > initial_view["zoom"]
    assert after_zoom["layoutIterations"] == initial_view["layoutIterations"]

    svg = page.locator("#literature-map")
    box = svg.bounding_box()
    assert box is not None
    page.mouse.move(box["x"] + 18, box["y"] + 18)
    page.mouse.down()
    page.mouse.move(box["x"] + 74, box["y"] + 48, steps=8)
    page.mouse.up()
    page.wait_for_timeout(50)
    after_pan = page.evaluate("window.__mapMetrics.snapshot()")
    assert after_pan["panX"] != 0 or after_pan["panY"] != 0

    node = page.locator('[data-node-id="node-17"]')
    node_box = node.bounding_box()
    assert node_box is not None
    before_position = page.evaluate(
        """() => {
            const node = document.querySelector('[data-node-id="node-17"]');
            return {x: Number(node.getAttribute('cx')), y: Number(node.getAttribute('cy'))};
        }"""
    )
    page.mouse.move(node_box["x"] + node_box["width"] / 2, node_box["y"] + node_box["height"] / 2)
    page.mouse.down()
    page.mouse.move(node_box["x"] + 34, node_box["y"] + 26, steps=6)
    page.mouse.up()
    page.wait_for_timeout(50)
    after_position = page.evaluate(
        """() => {
            const node = document.querySelector('[data-node-id="node-17"]');
            return {x: Number(node.getAttribute('cx')), y: Number(node.getAttribute('cy'))};
        }"""
    )
    assert after_position != before_position
    page.locator('[data-node-id="node-17"]').click()
    page.wait_for_function(
        "document.querySelector('[data-node-id=\"node-17\"]').getAttribute('data-selected') === 'true'"
    )

    # Exercise a burst of view updates and keep event, frame, and gesture wall
    # time as separate observations.
    page.evaluate("window.__mapMetrics.resetInteractionDurations()")
    page.mouse.move(box["x"] + 210, box["y"] + 140)
    page.mouse.down()
    for offset in range(12, 92, 8):
        page.mouse.move(box["x"] + offset, box["y"] + offset // 2)
    page.mouse.up()
    page.wait_for_timeout(150)
    final = page.evaluate("window.__mapMetrics.snapshot()")
    assert final["layoutIterations"] == initial_view["layoutIterations"]
    assert final["maxInteractionDurationMs"] < 50
    assert final["maxFrameDurationMs"] < 50
    assert final["maxLayoutFrameDurationMs"] < 50
    # The scripted gesture intentionally emits many pointer events; its wall
    # duration includes the input sequence itself.  A one-second ceiling catches
    # a stuck interaction without confusing it with per-frame responsiveness.
    assert final["maxGestureWallMs"] < 1000, final
    assert final["maxRenderWallMs"] < 250, final
    assert final["longTaskCount"] == 0
    assert final["renderRafCount"] > initial_view["renderRafCount"]
    return {"initial": initial, "after_zoom": after_zoom, "after_pan": after_pan, "final": final}


def test_synthetic_svg_supports_sparse_graph_interactions(tmp_path: Path) -> None:
    """Use a real browser to record baseline and representative-load facts."""

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        artifact_root = ARTIFACTS if os.environ.get("LITMAP_SAVE_FEASIBILITY_ARTIFACTS") == "1" else tmp_path
        screenshot_root = artifact_root / "screenshots"
        screenshot_paths = {
            "baseline": screenshot_root / SCREENSHOT.name,
            "high": screenshot_root / HIGH_SCREENSHOT.name,
        }
        records = {}
        for profile in ("baseline", "high"):
            page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
            _load_profile(page, profile)
            records[profile] = _exercise_interactions(page, profile)
            screenshot_root.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=screenshot_paths[profile], full_page=True)
            page.close()

        evidence_path = EVIDENCE if os.environ.get("LITMAP_SAVE_FEASIBILITY_ARTIFACTS") == "1" else artifact_root / "browser-evidence.json"
        evidence_path.write_text(
            json.dumps(
                {
                    "fixture": str(FIXTURE.relative_to(ROOT)),
                    "synthetic": True,
                    "profiles": {
                        "baseline": {"query": "", "edge_count": 34, "screenshot": str(screenshot_paths["baseline"])},
                        "high": {"query": "?profile=high", "edge_count": 620, "screenshot": str(screenshot_paths["high"])},
                    },
                    "viewport": {"width": 1440, "height": 900},
                    "records": records,
                    "thresholds": {
                        "max_layout_iterations": 8,
                        "max_event_handler_ms": 50,
                        "max_frame_work_ms": 50,
                        "max_layout_frame_work_ms": 50,
                        "max_gesture_wall_ms": 1000,
                        "max_render_wall_ms": 250,
                        "long_task_count": 0,
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        browser.close()
