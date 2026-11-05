"""KB 失败/兜底提示的 CSS class ↔ DOM 双向契约（pytest 门禁包装器）。

背景
----
`tests/frontend/` 是一个 Python 包（存在 ``__init__.py``），因此 ``*.js`` 文件
**不会被 pytest 收集**——直接 ``pytest tests/frontend/xxx.js`` 会报
``ERROR: not found ... (no match in any of [<Package frontend>])``。
Spec012 架构评审 A-9 要求补「从真实 DOM 渲染结果反向断言 CSS class 存在」，
若只落一个 ``.js``，它永远不会进入 ``pytest tests/frontend`` 门禁，
等于一条**可静默失效**的守卫（regression-guard 第 12 条）。

本文件用 ``subprocess`` 在 Node 中真实执行 ``test_frontend_kb_failure_class_dom_contract.js``
（同一做法参考 ``test_frontend_optimistic_card_contract.py::_run_node``），
把结果纳入 pytest。被执行的 harness 本身也会被直接 ``node`` 单跑，便于定位。

断言内容见 harness 文件头：``.kb-item-error.kb-item-error-restart`` /
``.kb-item-hint`` 的反向 DOM 断言 + ``styles.css`` 选择器存在性与作用域核对。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
HARNESS = Path(__file__).resolve().parent / "test_frontend_kb_failure_class_dom_contract.js"


def _run_node_harness(script: Path) -> "subprocess.CompletedProcess[str]":
    node = shutil.which("node")
    if not node:
        pytest.skip("node executable not found on PATH")
    assert script.exists(), f"missing node harness {script}"
    env = dict(os.environ)
    # 让 harness 里 require('node:vm') 等内建在受限环境下也稳定可用。
    env.setdefault("NODE_OPTIONS", "")
    return subprocess.run(
        [node, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )


def test_kb_failure_and_hint_classes_are_present_in_rendered_dom() -> None:
    """反向 DOM 断言：渲染结果里真的有 `.kb-item-error-restart` / `.kb-item-hint`。

    该用例在实现被改坏时会真实失败（已用变异测试验证：把 ``app.js:6551`` 的
    class 改名 → 断言「恰好 1 个节点」失败；把 ``app.js:6564`` 的 class 改名 →
    断言「恰好 1 个 .kb-item-hint」失败；把 ``styles.css`` 选择器改名 →
    断言「styles.css 必须定义选择器」失败）。
    """
    result = _run_node_harness(HARNESS)
    assert result.returncode == 0, (
        "KB class ↔ DOM 契约 harness 失败：\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    assert "ok - kb failure class dom contract" in result.stdout, result.stdout


def test_the_harness_reads_the_real_production_files() -> None:
    """守卫自身有效性：harness 必须读真实 ``frontend/app.js`` / ``styles.css``。

    防止有人把 harness 改成读夹具副本后「恒绿」（regression-guard 第 12 条「恒真断言」）。
    """
    source = HARNESS.read_text(encoding="utf-8")
    assert "'../../frontend/app.js'" in source, "harness 必须读取真实 frontend/app.js"
    assert "'../../frontend/styles.css'" in source, "harness 必须读取真实 frontend/styles.css"
    # 断言必须来自渲染出的 DOM 节点，而不是只比对源码字符串。
    assert "findAll(" in source and "walk(" in source, "harness 必须遍历真实渲染出的 DOM 树"
    assert (FRONTEND / "app.js").is_file()
    assert (FRONTEND / "styles.css").is_file()
