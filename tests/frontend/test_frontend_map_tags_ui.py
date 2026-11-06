# -*- coding: utf-8 -*-
"""FE-1a 地图级标签系统前端 UI 静态契约检查（Spec043 Task21）。

纯静态文本断言，不需要浏览器/后端。真实 API 与浏览器 E2E 属于任务验收门禁。
只验证「DOM 契约 / 必要符号 / 端点走 request 封装 / 无 innerHTML / +N 逻辑 / CSS 作用域」。
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = (ROOT / "frontend/literature-maps.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/literature-maps.css").read_text(encoding="utf-8")


def test_tags_ui_dom_contract_container_carries_data_map_id() -> None:
    # 卡片改为容器元素承载 data-map-id（保留属性与选图行为），不再是 <button>。
    assert "createElement('div', 'literature-map-list-item')" in MODULE
    assert "createElement('button', 'literature-map-list-item')" not in MODULE
    assert "item.dataset.mapId" in MODULE  # data-map-id 保留
    # ⋯ 是 <button> 触发按钮，点击 stopPropagation，不得触发 selectMap。
    assert "createElement('button', 'literature-map-card-menu-trigger', '⋯')" in MODULE
    assert "event.stopPropagation()" in MODULE


def test_tags_ui_safe_dom_no_innerhtml_and_color_via_style() -> None:
    assert "innerHTML" not in MODULE
    # 颜色只用于 style.setProperty（色点），不拼进 HTML。
    assert "style.setProperty" in MODULE
    # 标签名只用 textContent（createElement 第三参即 textContent）。
    assert "createElement('span', 'literature-map-tag-name'" in MODULE


def test_tags_ui_required_symbols_present() -> None:
    for symbol in (
        "function loadTags",
        "function renderTagFilterBar",
        "function openTagMenu",
        "function closeTagMenu",
        "function saveMapTags",
        "function createTag",
        "function renameTag",
        "function deleteTag",
        "MAP_CARD_TAG_LIMIT = 3",
    ):
        assert symbol in MODULE


def test_tags_ui_api_endpoints_reuse_request_helper() -> None:
    # 必须复用既有 request() 封装（禁止新增 fetch / 绕过 API_ROOT）。
    assert "request('/tags')" in MODULE          # GET /tags
    assert "method: 'POST'" in MODULE           # POST /tags
    assert "method: 'PUT'" in MODULE            # PUT /{map_id}/tags
    assert "method: 'PATCH'" in MODULE          # PATCH /tags/{id}
    assert "method: 'DELETE'" in MODULE         # DELETE /tags/{id}
    assert "/tags/${tag" in MODULE              # 单标签路径（PATCH/DELETE）
    assert "tag_ids" in MODULE                  # PUT 绑定请求体
    assert MODULE.count("fetch(") == 3          # 全模块仅 3 处 fetch（request/catalog/export）


def test_tags_ui_card_badge_plus_n_logic() -> None:
    # 最多显示 3 个，超出 +N，title/aria-label 列全部名称。
    assert "slice(0, MAP_CARD_TAG_LIMIT)" in MODULE
    assert "+${extra}" in MODULE
    assert "join('、')" in MODULE


def test_tags_ui_css_classes_scoped_to_view() -> None:
    for cls in (
        ".literature-map-list-tags",
        ".literature-map-tag-chip",
        ".literature-map-tag-dot",
        ".literature-map-tag-filter-bar",
        ".literature-map-tag-filter",
        ".literature-map-card-menu",
        ".literature-map-card-menu-trigger",
    ):
        assert cls in STYLES
    assert "#literature-maps-view" in STYLES
