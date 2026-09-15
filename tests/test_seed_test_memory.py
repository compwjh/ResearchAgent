"""spec-038 收尾 · 测试数据 seed 脚本契约测试。

锁定 ``scripts/seed_test_memory.py`` 的外部行为（对应 task 硬性要求）：

1. **可指定目标目录**：默认写 ``data/memory``，但 ``--target`` 可覆盖；
   测试必须只在 tmp 目录跑，绝不污染真实 ``data/memory/``。
2. **幂等**：连续执行两次，条目数不翻倍（``--reset`` 语义先清空再重建）。
3. **三层数据齐全**：
   - L1：中文全局记忆（MEMORY.md）、项目级记忆（projects/<id>.md）、
     PENDING.md 待确认条目、USER.md 画像；
   - L2：会话 + 中英文混排消息（user/assistant 两种 role），索引重建后可检索。
4. **L2 可验证**：seed 结束后中文关键词能命中（脚本给出的统计非零）。
5. **离线**：不依赖 Ollama / reranker / 网络。

加载方式：脚本不是包内模块，用 importlib 按文件路径加载，避免要求
``scripts/__init__.py`` 或改动 sys.path 契约。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "seed_test_memory.py"


def _load_script_module():
    """按文件路径加载 seed 脚本，返回模块对象。"""
    spec = importlib.util.spec_from_file_location("seed_test_memory_under_test", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None, "无法加载 scripts/seed_test_memory.py"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def seed_module():
    assert _SCRIPT_PATH.is_file(), f"缺少脚本：{_SCRIPT_PATH}"
    return _load_script_module()


@pytest.fixture()
def target(tmp_path: Path) -> Path:
    """每个用例独立的 seed 目标目录。"""
    return tmp_path / "seed-memory"


def test_script_exists_and_has_main_guard():
    """脚本存在、可加载，且有 __main__ 入口。"""
    source = _SCRIPT_PATH.read_text(encoding="utf-8")
    assert 'if __name__ == "__main__":' in source


def test_cli_help_is_chinese_and_offline(seed_module):
    """``--help`` 可解析且说明为中文（不触发任何模型调用）。"""
    parser = seed_module.build_arg_parser()
    help_text = parser.format_help()
    assert "--target" in help_text
    assert "--reset" in help_text
    # 中文说明：帮助文本里应出现汉字。
    assert any("\u4e00" <= ch <= "\u9fff" for ch in help_text)


def test_seed_writes_three_layers(seed_module, target: Path):
    """一次执行后，L1 文件与 L2 会话/消息齐备。"""
    import sqlite3

    result = seed_module.seed_memory(target_dir=target, reset=True)
    assert result is not None

    # --- L1 ---
    assert (target / "USER.md").is_file()
    assert (target / "MEMORY.md").is_file()
    assert (target / "PENDING.md").is_file()
    projects_dir = target / "projects"
    assert projects_dir.is_dir()
    project_files = sorted(projects_dir.glob("*.md"))
    assert len(project_files) >= 1, "至少应造一个项目级记忆文件"

    user_text = (target / "USER.md").read_text(encoding="utf-8")
    memory_text = (target / "MEMORY.md").read_text(encoding="utf-8")
    pending_text = (target / "PENDING.md").read_text(encoding="utf-8")
    assert user_text.strip(), "USER.md 画像不应为空"
    assert memory_text.strip(), "MEMORY.md 全局记忆不应为空"
    assert pending_text.strip(), "PENDING.md 应有待确认条目"

    # 中文内容校验（抽样：全局记忆里应含汉字）。
    assert any("\u4e00" <= ch <= "\u9fff" for ch in memory_text)

    # --- L2：库存在且有会话与消息 ---
    db_path = target / "memory.sqlite3"
    assert db_path.is_file(), "应建立记忆库"
    connection = sqlite3.connect(str(db_path))
    try:
        conversations = connection.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        messages = connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        roles = {row[0] for row in connection.execute("SELECT DISTINCT role FROM messages").fetchall()}
    finally:
        connection.close()
    assert conversations >= 1
    assert messages >= 2
    assert {"user", "assistant"} <= roles, f"消息应含 user/assistant 两种 role，实际={roles}"


def test_seed_is_idempotent(seed_module, target: Path):
    """连续执行两次，条目数不翻倍（先清空后重建）。"""
    seed_module.seed_memory(target_dir=target, reset=True)
    first_memory_lines = (target / "MEMORY.md").read_text(encoding="utf-8").count("- ")
    first_pending = (target / "PENDING.md").read_text(encoding="utf-8").count("- ")

    seed_module.seed_memory(target_dir=target, reset=True)
    second_memory_lines = (target / "MEMORY.md").read_text(encoding="utf-8").count("- ")
    second_pending = (target / "PENDING.md").read_text(encoding="utf-8").count("- ")

    assert first_memory_lines > 0
    assert first_memory_lines == second_memory_lines, "重复执行不应让全局记忆翻倍"
    assert first_pending == second_pending, "重复执行不应让待确认条目翻倍"


def test_seed_l2_searchable_in_chinese(seed_module, target: Path):
    """seed 之后，中文关键词可通过 L2 检索命中（离线，无需模型）。"""
    result = seed_module.seed_memory(target_dir=target, reset=True)

    # 脚本自身应返回可验证的检索统计。
    assert "search_query" in result
    assert result["search_hits"] >= 1, "seed 后应能用中文关键词命中记录"

    # 独立复核：用同一套索引实现再搜一次（不依赖脚本内部实现细节）。
    from backend.app.memory.repository import MemoryRepository
    from backend.app.memory.session_search import SessionSearchIndex

    index = SessionSearchIndex(
        repository=MemoryRepository(target / "memory.sqlite3"),
        memory_dir=target,
    )
    hits = index.search(result["search_query"], limit=10)
    assert hits, f"搜索 {result['search_query']!r} 应命中，实际为空"


def test_seed_does_not_touch_real_data_memory(seed_module, target: Path):
    """seed 到 tmp 时，真实 data/memory 不应被创建/修改。"""
    real_dir = _REPO_ROOT / "data" / "memory"
    existed = real_dir.exists()
    before = sorted(p.name for p in real_dir.iterdir()) if existed else None

    seed_module.seed_memory(target_dir=target, reset=True)

    after = sorted(p.name for p in real_dir.iterdir()) if real_dir.exists() else None
    assert after == before, "seed 到自定义目录时不得改动真实 data/memory"


def test_seed_restores_memory_db_path_env(seed_module, target: Path, monkeypatch):
    """seed 结束时必须还原 MEMORY_DB_PATH，不把重定向泄漏给调用方/后续逻辑。"""
    import os

    monkeypatch.delenv("MEMORY_DB_PATH", raising=False)
    seed_module.seed_memory(target_dir=target, reset=True)
    assert "MEMORY_DB_PATH" not in os.environ, "seed 后应移除自己设置的 MEMORY_DB_PATH"

    monkeypatch.setenv("MEMORY_DB_PATH", "/tmp/original-db.sqlite3")
    seed_module.seed_memory(target_dir=target, reset=True)
    assert os.environ["MEMORY_DB_PATH"] == "/tmp/original-db.sqlite3", "seed 后应还原调用方原值"
