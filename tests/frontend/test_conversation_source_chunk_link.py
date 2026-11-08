"""Static contracts for the conversation -> knowledge-base chunk locate link (Spec044)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
CONV = (ROOT / "frontend/conversation-research.js").read_text(encoding="utf-8")
KB = (ROOT / "frontend/kb-inspection.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def _slice_function(source, name):
    """Return the brace-balanced body of `function <name>(...)`."""
    marker = "function " + name + "("
    start = source.index(marker)
    brace_start = source.index("{", start)
    depth = 0
    for i in range(brace_start, len(source)):
        char = source[i]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[brace_start:i + 1]
    raise AssertionError("unbalanced braces for " + name)


def test_conversation_research_adds_chunk_locate_entry():
    for symbol in (
        "appendChunkLocateLink",
        "onLocateChunk",
        "定位到召回片段",
        "片段",
        "conversation-source-locate-button",
        "String(chunkId)",
    ):
        assert symbol in CONV


def test_original_pdf_source_entry_and_export_unchanged():
    assert "_blank" in CONV
    assert "noopener noreferrer nofollow" in CONV
    assert "打开知识库原文" in CONV
    assert "SOURCE_ROUTE" in CONV
    # 既有白名单/安全校验仍在导出。
    assert "safeSourceUrl" in CONV
    assert "safeSourceUrl" in CONV.split("return {")[-1]


def test_kb_inspection_exposes_focus_chunk():
    assert "focusChunk" in KB
    assert "pendingFocusChunkId" in KB
    # 控制器返回对象中暴露 focusChunk。
    ret = re.search(r"return\s*\{[\s\S]{0,400}?focusChunk", KB)
    assert ret is not None


def test_app_has_single_chunk_locate_path():
    for symbol in (
         "locateKnowledgeChunk",
         "onLocateChunk",
         "KB_LOCATE_ID_WHITELIST",
         "jumpToKnowledgeBase",
         "无法定位片段",
    ):
        assert symbol in APP

    assert APP.count("function locateKnowledgeChunk") == 1
    # 唯一一套高亮链路：经控制器 focusChunk 间接调用，app.js 内不得出现第二套直调。
    assert "controller.focusChunk" in APP
    assert "focusChunkFn(" in APP


def test_no_innerhtml_in_new_entry_points():
    # 用户文本不得拼进 innerHTML：两个新增/共用的入口函数体均不得出现 innerHTML。
    assert "innerHTML" not in _slice_function(APP, "renderStepEvidencePanel")
    assert "innerHTML" not in _slice_function(CONV, "appendChunkLocateLink")


def test_forbid_attr_kept_closed():
    assert "FORBID_ATTR" in APP
    forbid_attrs_block = APP.split("FORBID_ATTR:")[1].split("]")[0]
    assert "'style'" in forbid_attrs_block


def test_chunk_locate_styles_present():
    assert ".conversation-source-locate-button" in STYLES
    assert ".step-evidence-source-action" in STYLES
    assert ".step-evidence-panel" in STYLES
