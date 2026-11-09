"""tests/ 级别共享的预热登记表清理 fixture（**显式 opt-in，非 autouse**）。

背景
----
``backend.app.platform.warmup._registry`` 是进程级单例。``tests/system/
test_startup_warmup.py`` 的用例调用 ``start_warmup()`` 后会把 ``embedding``
等项写为 ``failed``，但测试结束不清理；随后 ``tests/kb/test_kb_routes.py``
的 ``/api/kb/health`` 经 ``_probe_embedding_ready()`` 读到残留的 ``failed``
会直接短路返回 False，使断言结果依赖跨模块执行顺序。

任务 S 曾在此放 function 级 ``autouse``，作用于全仓（含 ``tests/frontend/**``
与 ``tests/e2e/**``），每个用例前后都导入整条 backend 依赖链；且
``reset_warmup()`` docstring 明确「不中断正在跑的线程」——上一用例的 daemon
``_runner`` 未收敛就 reset，残留 ``mark_done`` 会把 ``failed`` 写回、污染下一
用例（逻辑竞态窗口）。

修法（任务 U）
--------------
- 改为**显式 opt-in** fixture：本文件顶层不再导入 backend，作用面不再覆盖全仓；
  由 ``tests/system/conftest.py``（污染源）与 ``tests/kb/conftest.py``（受害者）
  各自以目录级 ``autouse`` 启用，达到同样的隔离效果但范围收窄。
- 竞态防护：清理前用 ``is_warmup_started()`` 判断是否有在飞预热，若有则**有界
  等待**登记表收敛到终态（ready/failed）再 ``reset_warmup()``，消除「重置被在
  飞线程覆盖」。没有在飞预热时零等待，不拖慢无关用例。
"""

import time

import pytest

_WARMUP_TERMINAL_STATUSES = ("ready", "failed")
_WARMUP_DRAIN_TIMEOUT_SECONDS = 5.0


def _drain_and_reset() -> None:
    """等待在飞预热线程收敛后再清空登记表（消除逻辑竞态）。"""
    from backend.app.platform import warmup

    if warmup.is_warmup_started():
        deadline = time.monotonic() + _WARMUP_DRAIN_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            snapshot = warmup.readiness_snapshot()
            if snapshot and all(
                item["status"] in _WARMUP_TERMINAL_STATUSES for item in snapshot.values()
            ):
                break
            time.sleep(0.01)
    warmup.reset_warmup()


@pytest.fixture
def clean_warmup_registry():
    """每个用例前后把预热登记表恢复为干净的 unknown 状态（需显式声明才生效）。"""
    _drain_and_reset()
    yield
    _drain_and_reset()
