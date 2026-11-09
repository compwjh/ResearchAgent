"""tests/kb 目录级预热隔离：受害者在本目录。

``tests/kb/test_kb_routes.py`` 的 ``/api/kb/health`` 会读预热注册表。这里启用
根 ``tests/conftest.py`` 的显式 fixture，保证任意执行顺序都从干净的 unknown
状态开始，同时不把重置强加给全仓其它目录（评审 MEDIUM-3）。
"""


import pytest


@pytest.fixture(autouse=True)
def _reset_warmup_registry_in_kb(clean_warmup_registry):
    yield
