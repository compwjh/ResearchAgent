"""spec-038 P3：测试套件级别的记忆目录隔离。

背景
----
P3 之后，``MemoryAnalysisWorker`` / ``MemoryEvolutionWorker`` / ``CompactionWorker``
在缺省参数下会构造 ``MarkdownMemoryStore()``，其根目录取
``backend.app.memory.markdown_store.MEMORY_DIR``（默认仓库内 ``data/memory``）。
若不在测试层隔离，任何触发这些 worker 的接口用例都会把**测试数据写进真实用户记忆目录**，
既污染仓库（虽然已被 .gitignore 忽略），也会让「文件记忆为空」类断言产生**跨用例顺序依赖**。

做法
----
autouse 的 function 级 fixture，把 ``markdown_store.MEMORY_DIR`` 指向每个用例自己的
``tmp_path/memory``。只改 store 模块的读取点，不动 ``platform.config.MEMORY_DIR``，
以免破坏显式断言配置默认值的用例（``test_memory_injection_chain``）。
显式传入 ``memory_dir`` 的用例不受影响（它们自己指定路径）。
"""

import pytest


@pytest.fixture(autouse=True)
def _isolate_default_memory_dir(tmp_path, monkeypatch):
    """把默认 MEMORY_DIR 隔离到 tmp，保证测试不写真实记忆目录。"""
    monkeypatch.setattr(
        "backend.app.memory.markdown_store.MEMORY_DIR", tmp_path / "memory"
    )
    return tmp_path / "memory"

@pytest.fixture(autouse=True)
def _isolate_capability_db(tmp_path):
    """Keep the model capability cache out of the repository data directory."""
    from backend.app.platform import capability_store
    from backend.app.platform.ollama import clear_reasoning_capability_cache

    capability_store.set_db_path(tmp_path / "model_capabilities.sqlite3")
    clear_reasoning_capability_cache()
    yield
    capability_store.set_db_path(None)
    clear_reasoning_capability_cache()
