---
name: test-naming
description: 测试文件命名与分类协议；创建、改名或评审 tests 下测试时按被测能力命名，禁止 spec/task 数字。
status: active
---

# 测试命名与分类

此 Skill 约束 `tests/` 下的 Python、JavaScript 测试文件。文件名必须以
`test_` 开头，并描述被测功能或能力；不得包含 `spec` 后跟数字或 `task`
后跟数字。测试目录按能力分组，公共 `fixtures/` 与 `runtime/` 目录保持独立。

## 执行协议

1. 新建或改名时先选择功能名，不把临时 spec/task 编号写入 basename。
2. 移动文件时同步检查 `Path(__file__)` 的仓库根路径、fixture 路径和包内导入。
3. 完成改动后运行 `python scripts/check_test_naming.py`。
4. 再运行 `pytest --collect-only -q`，确认无 `ERROR collecting`；若是纯改名/移动，收集数量应保持不变。

## 机械门禁

项目级轻量检查位于 `scripts/check_test_naming.py`。它只依赖 Python 标准库，
发现违规时返回非零退出码，适合在 pytest 之前运行。
