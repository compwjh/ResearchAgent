---
name: test-naming
description: "Test file naming rule for this project: never embed spec numbers (specNNN) or task numbers (taskNN) in a test file name; name tests by the capability/function they exercise. Use when creating, renaming, or reviewing test_*.py / test_*.js files, or when an agent is about to write a new test. Enforced by spec-039."
agent_created: true
---

# Test File Naming — 禁 spec/task 数字，按功能命名

## 硬规则（违反即改）

1. **测试文件名不得包含 `spec` 编号**（如 `spec029`、`spec032`）或 **`task` 编号**（如 `task02`、`task07`）。
2. 文件名必须以 `test_` 开头、以 `.py`（或 `.js`）结尾，中间用**被测功能/能力**的简短英文命名。
3. 跨 spec 复用的能力（如来源适配器、证据矩阵、路由决策）一律按**功能**命名，不挂靠某个 spec。

## 为什么

- 一个能力往往跨多个 spec 演进（如 paper source 适配器贯穿 spec015/027/032/035）。用 spec 数字命名会把"功能归属"钉死在某一版 spec 上，后续该能力被别的 spec 改动时，文件名就撒谎了。
- task 编号是临时执行单元，任务收口后即无意义，留在文件名里纯噪声。
- **历史教训（2026-09-19 核实）**：用户曾在对话中口头要求此规则，但**从未沉淀到任何文档/skill**，结果 `git` 历史上 42 个含 spec 数字、17 个含 task 数字的测试文件全部由 `compwjh` 创建，规则无人遵守。规则必须落盘才能生效。

## 改名对照（反例 → 正例）

| ❌ 错误（含 spec/task 数字） | ✅ 正确（按功能） |
|---|---|
| `test_spec032_ccs_source.py` | `test_ccs_source_adapter.py` |
| `test_spec032_authority_registry.py` | `test_source_authority_registry.py` |
| `test_spec032_sources_api.py` | `test_paper_sources_api.py` |
| `test_spec029_acquisition_bridge.py` | `test_acquisition_bridge.py` |
| `test_spec030_matrix.py` | `test_evidence_matrix.py` |
| `test_spec031_selection_projection.py` | `test_routing_selection_projection.py` |
| `test_spec034_task07_contract.py` | `test_approval_guidance_contract.py`（按该测试验证的功能命名） |
| `test_spec027_runtime_contract.py` | `test_research_runtime_contract.py` |

## 执行清单（创建/重命名测试时）

- [ ] 文件名无 `spec\d+` / `task\d+` 子串。
- [ ] 文件名描述**被测功能**，不描述"属于哪个 spec/task"。
- [ ] 仍保持 `test_` 前缀 + 正确后缀（pytest 才能发现）。
- [ ] 若移动文件到子目录，检查文件内 `Path(__file__).resolve().parents[N]` / `__file__.parent / "fixtures"` 等路径：
  - 移入一层子目录后，原 `parents[1]`（仓库根）应改为 `parents[2]`；原 `__file__.parent / "fixtures"` 应改为从仓库根定位（如 `ROOT / "tests" / "fixtures"`，其中 `ROOT = Path(__file__).resolve().parents[2]`）。
- [ ] 改名/移动后用 `pytest --collect-only -q` 确认收集到的用例数与移动前一致，无 `ERROR collecting`。

## 绑定

此规则绑定到 `backend-dev` / `frontend-dev`（写测试）、`backend-reviewer` /
`frontend-reviewer`（评审测试）以及 `backend-tester` / `frontend-tester` /
`tester`（测试与验收）角色；`coding-standards` 评审与 `regression-guard`
收口时一并核对文件名。
