# Spec039 测试基建验证报告

日期：2026-09-20
分支：`chore/test-infra-complete`
范围：仅测试文件、测试 Skill/角色绑定、命名检查脚本与本报告；未修改 `backend/` 或 `frontend/` 业务代码。

## 完成项

- 使用 `git mv` 将遗留的 18 个含 `specNNN`/`taskNN` 的测试 basename 按能力重命名，保留 Git 历史。
- 修正移入 `tests/frontend/` 后 8 个 JavaScript 合同测试的 `require` 路径（包括本次重命名文件和此前分类提交遗漏的文件）。
- 新增 `.agents/skills/test-naming/SKILL.md`，并将 `test-naming` 绑定到后端/前端开发、评审与测试角色；同步补充 `.codebuddy/skills/test-naming/SKILL.md` 的绑定说明。
- 新增无第三方依赖的 `scripts/check_test_naming.py` 机械检查。

## 验证结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_naming.py` | 0 | 通过；`tests/` 下无违规 basename |
| 改名后 Python 测试定向收集（16 个改名 `.py` 文件） | 0 | `202 tests collected`，无收集错误 |
| 改名后 Python 受影响测试（16 个改名 `.py` 文件） | 0 | `202 passed in 4.37s` |
| `node tests/frontend/*.js` | 0 | 8/8 JavaScript 合同测试通过 |
| `git diff --check` | 0 | 通过 |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --collect-only -q` | 2 | `2057 tests collected, 37 errors` |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q` | 2 | 收集阶段同样 `37 errors` |

## 剩余阻塞

全量收集/回归被该隔离分支基线缺失的 Spec032 文件阻塞：多个既有测试导入
`backend.app.paper_discovery.infrastructure.source_registry`，但该文件不在
`chore/update-archify` 基线中（错误为 `ModuleNotFoundError`）。按用户范围不能修改
`backend/**`，因此未用业务实现绕过；定向改名测试已全部通过。补齐 Spec032 基线后，
应重新运行全量收集与回归，并将最终数量回填 Spec039 收口材料。
