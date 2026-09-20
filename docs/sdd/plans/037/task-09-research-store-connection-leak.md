> 关联：[spec-037](../../specs/037-startup-readiness-gap-and-ux-bugs.md)（Bug 9） ｜ 索引：[README](./README.md)
> 依赖：任务 01；当前状态：`已完成`

# 任务 09：修复 ResearchStore 的 SQLite 连接泄漏（fd 耗尽）

## 一句话目标
把 `ResearchStore._connect()` 改为保证关闭连接的上下文管理器，消除 SQLite 连接只开不关导致的文件句柄耗尽。

## 背景与前置条件（已核实，不要再重复排查）
- **现象**：Ollama 正常，但 `/api/health` 返回 500、模型库空白。
- **实测**：出问题的进程打开 **88,778 个句柄**，去重后仅 87 个路径，其中 **88,778 个全部指向 `data/research/research.sqlite3`**；重启后新进程仅 144 个句柄。
- **根因**：`backend/app/research/infrastructure/research_store.py:797` `_connect()` 返回裸 `sqlite3.Connection`；**全部 89 个调用点**写作 `with self._connect() as conn:`。`sqlite3.Connection` 作上下文管理器**只管理事务（提交/回滚），不关闭连接**；全文件 **0 处 `.close()`**，连接只能等 GC，实测未及时回收 → fd 耗尽 → 新建 `httpx.Client`（`ssl.create_default_context` → `certifi`）抛 `OSError: [Errno 24] Too many open files` → 所有新出站 HTTP 失败。
- 调用点形态已确认：`self._connect()` 的 89 处**全部**是 `with ... as` 形式（`as conn` / `as connection` / `as read_conn` / `as verification_connection` / `as audit_connection`），**没有** `conn = self._connect()` 这类赋值用法 → 可单点修复，无需改调用点。
- 文件当前**未导入** `contextlib.contextmanager`。

## 实施步骤（文件边界：`backend/app/research/infrastructure/research_store.py`）
1. 补 import：`from contextlib import contextmanager`（以及类型标注所需的 `Iterator`，若文件已用 `from __future__ import annotations` 则按需）。
2. 把 `_connect()` 改为 `@contextmanager`，在 `finally` 中 `connection.close()`；内部保留 `with connection:` 以**维持原有事务语义**（成功提交、异常回滚）：

```python
@contextmanager
def _connect(self) -> Iterator[sqlite3.Connection]:
    """新建连接：超时 30s、Row 工厂、外键开启。

    必须以 ``with`` 使用：内部 ``with connection:`` 维持原有事务语义（成功提交、
    异常回滚），``finally`` 保证连接被关闭——``sqlite3.Connection`` 作上下文管理器
    只管事务、不关连接，此前因此泄漏了数万个文件句柄（spec-037 Bug 9）。
    """
    connection = sqlite3.connect(str(self.database_path), timeout=30.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()
```

3. **不要**改动 89 个调用点中的任何一个，也不要改 SQL、表结构或业务逻辑。
4. 顺带自查同文件是否有其它直接 `sqlite3.connect` 未关闭的写法；若有，按同样方式收口（并在回传中说明）。

## 边界与明确不做
- 只改 `backend/app/research/**`；不碰 `frontend/**`。
- 不重构 `ResearchStore` 的表结构 / SQL / 业务逻辑；不改成连接池或全局单连接。
- 不改其它模块的数据库连接管理（本次仅 research 模块实测存在该泄漏）。
- 事务语义必须保持不变：成功仍提交、异常仍回滚（现有 41 处 `conn.commit()` 与 `with conn:` 行为不得改变）。

## 产出物、执行结果与变更日志

- 实现：`backend/app/research/infrastructure/research_store.py` `_connect()` 改为 `@contextmanager`（`finally` 中 `close()`，内层 `with connection:` 维持事务语义）+ 补 `contextlib.contextmanager` / `typing.Iterator` 导入。89 个调用点零改动。
- 新增 `tests/test_research_store_connection_leak.py`（5 用例：成功/异常路径连接关闭、300 次读调用 fd 不增长、300 次异常调用 fd 不增长、写入仍提交）。
- **反向验证**：`git stash` 还原修复后该文件 3 failed（含 fd 增长用例），证明测试可捕获缺陷；恢复后 5 passed。
- 连带适配：`tests/test_spec027_backend_research_slice.py` 的级联回滚测试原先用 `store._connect = lambda: failing` 注入失败连接，新契约下返回的是上下文管理器，已改为 `@contextlib.contextmanager` 包装（保留"失败必须整体回滚"意图，刻意不引入事务包装以维持原语义）。
- 回归：research 定向 **62 passed**；全量 **2401 passed / 6 failed**（与既有基线一致，无新增）。

## 验收
- `ResearchStore._connect()` 在**正常返回**与**抛异常**两条路径下都关闭连接（`finally` 保证）。
- 新增测试：连续 ≥200 次调用 `ResearchStore` 的读/写方法（含一个会抛异常的方法以覆盖异常路径）后，进程对该 sqlite 文件持有的句柄数**不随调用次数增长**。
- 既有 research 相关 pytest 全绿（事务/回滚语义未被破坏）。
- 部署后复测：进程句柄数长时间保持稳定（不再出现 8 万级），`/api/health` 持续 200、模型库可用。
