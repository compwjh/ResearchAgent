"""tests/system 目录级预热隔离：污染源在本目录。

``tests/system/test_startup_warmup.py`` 调用 ``start_warmup()`` 会把注册表写成
``failed``。这里启用根 ``tests/conftest.py`` 的显式 fixture，把清理作用面限制在
本目录，而不是全仓 autouse（评审 MEDIUM-3）。
"""


import pytest


@pytest.fixture(autouse=True)
def _reset_warmup_registry_in_system(clean_warmup_registry):
    yield
