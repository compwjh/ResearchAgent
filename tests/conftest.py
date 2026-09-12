"""全局测试隔离（spec-035 Bug3）。

能力探测的 SQLite 二级缓存默认写在仓库 data/ 下；任何触碰
``get_reasoning_capabilities`` 的测试都可能把 mock 探测结果写入真实库，
污染后续用例。这里用 autouse fixture 把每个测试的 capability DB 重定向
到独立临时目录，结束即弃。
"""

import tempfile
from pathlib import Path

import pytest

from backend.app.platform import capability_store
from backend.app.platform.ollama import clear_reasoning_capability_cache


@pytest.fixture(autouse=True)
def _isolate_capability_db(tmp_path):
    capability_store.set_db_path(tmp_path / "model_capabilities.sqlite3")
    clear_reasoning_capability_cache()
    yield
    capability_store.set_db_path(None)
    clear_reasoning_capability_cache()
