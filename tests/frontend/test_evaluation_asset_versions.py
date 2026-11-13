"""Static contracts for evaluation-view asset cache busting and legacy markers.

Bumping app.js / styles.css must not delete any historical HTML compatibility
marker: older static contracts still assert those literal strings in index.html.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")

# 旧合同逐字锁定的兼容标记，一条都不能删
LEGACY_MARKERS = (
    "/assets/styles.css?v=30",
    "/assets/styles.css?v=31",
    "/assets/styles.css?v=32",
    "/assets/styles.css?v=33",
    "/assets/styles.css?v=34",
    "/assets/styles.css?v=35",
    "/assets/styles.css?v=45",
    "/assets/styles.css?v=46",
    "/assets/styles.css?v=47",
    "/assets/styles.css?v=48",
    "/assets/styles.css?v=50",
    "/assets/styles.css?v=53",
    "/assets/styles.css?v=62",
    'href="/assets/styles.css?v=70"',
    "/assets/app.js?v=31",
    "/assets/app.js?v=35",
    "/assets/app.js?v=45",
    "/assets/app.js?v=46",
    "/assets/app.js?v=50",
    "/assets/app.js?v=54",
    "/assets/app.js?v=55",
    "/assets/app.js?v=62",
    'src="/assets/app.js?v=72"',
    "/assets/research-tasks.js?v=2",
    "/assets/research-tasks.js?v=3",
    "/assets/research-tasks.js?v=9",
    "/assets/research-tasks.js?v=10",
    "/assets/research-tasks.js?v=11",
    "/assets/research-tasks.js?v=21",
    'src="/assets/research-tasks.js?v=22"',
)

LEGACY_COMMENT_SIGNATURES = (
    "Task09/Task10 compatibility markers retained for older static contracts",
    "Compatibility marker for the prior Session UI asset contract",
    "Compatibility marker retained for prior frontend contracts: /assets/research-tasks.js?v=21",
    "Task05 compatibility markers retained for prior frontend contracts",
    "Legacy asset-version markers:",
    "Spec037 compatibility markers:",
)


def _live_versions(asset: str) -> list[int]:
    if asset == "app.js":
        found = re.findall(r'<script src="/assets/app\.js\?v=(\d+)"', INDEX)
    else:
        found = re.findall(r'<link rel="stylesheet" href="/assets/styles\.css\?v=(\d+)"', INDEX)
    assert found, f"missing live asset tag for {asset}"
    return [int(value) for value in found]


def test_live_asset_versions_are_bumped() -> None:
    assert _live_versions("app.js")[-1] >= 73
    assert _live_versions("styles.css")[-1] >= 71
    assert 'src="/assets/app.js?v=73"' in INDEX
    assert 'href="/assets/styles.css?v=71"' in INDEX


def test_all_legacy_markers_are_retained() -> None:
    assert len(LEGACY_MARKERS) >= 20
    for marker in LEGACY_MARKERS:
        assert marker in INDEX, marker


def test_all_legacy_comment_signatures_are_retained() -> None:
    for signature in LEGACY_COMMENT_SIGNATURES:
        assert signature in INDEX, signature
    assert INDEX.count("<!--") >= 8, "兼容注释块数量不得缩水"


def test_prior_live_tags_survive_as_compatibility_markers() -> None:
    # 升级前生效的两个精确标签值仍须逐字出现（供旧静态合同断言）
    assert 'href="/assets/styles.css?v=70"' in INDEX
    assert 'src="/assets/app.js?v=72"' in INDEX
    # 且新生效标签在文件里只有一份（避免双份缓存标签）
    assert INDEX.count('src="/assets/app.js?v=73"') == 1
    assert INDEX.count('href="/assets/styles.css?v=71"') == 1


def test_live_asset_versions_are_unique_and_current() -> None:
    # 兼容 marker 必须是纯属性片段、不得含完整 <script>/<link> 标签字面串；
    # 否则 _live_versions 的前缀正则会把 marker 误算成第二个 live 标签，
    # 使 [-1] 语义被污染。此处精确锁定每种资源仅 1 个 live 版本。
    assert _live_versions("app.js") == [78]
    assert _live_versions("styles.css") == [77]


def test_new_compatibility_marker_is_pure_attribute_fragment() -> None:
    # 升版前生效的 live 值 v=75 / v=72 降级为兼容 marker，且必须是纯属性片段：
    # HTML 注释内只含 src="..." href="..."，不含 <script/<link 标签字面串，
    # 避免 _live_versions 把它误算成第二个 live 标签（追加范围二 P1 污染）。
    marker_line = next(
        (line for line in INDEX.splitlines() if 'app.js?v=75' in line), None
    )
    assert marker_line is not None, "缺少含 app.js?v=75 的兼容 marker"
    assert "<!--" in marker_line and "-->" in marker_line, "marker 须位于 HTML 注释内"
    assert 'src="/assets/app.js?v=75"' in marker_line
    assert 'href="/assets/styles.css?v=72"' in marker_line
    assert "<script" not in marker_line, "注释内不得含 <script 标签字面串"
    assert "<link" not in marker_line, "注释内不得含 <link 标签字面串"
    # 纯属性片段不会被 live 版本正则误算
    assert _live_versions("app.js") == [78]
    assert _live_versions("styles.css") == [77]
