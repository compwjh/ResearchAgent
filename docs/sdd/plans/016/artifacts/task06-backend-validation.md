# Task06 backend implementation evidence

日期：2026-10-12。实现代理：backend-dev。工作树：`.worktrees/spec-016`。

## 已完成的实现切片

- `prompts.py`：按 canonical Task/claim/snapshot 绑定渲染 Prompt；只替换白名单变量；以原始 snapshot 保留 recovery baseline；检查敏感内容并原子写入私有 run 目录。发布前重新验证 canonical Spec 必须为“已确认”或“实施中”，且 Task 所有 `required_gates` 都已从 canonical view 核验满足。
- `results.py`：严格解析 `sdd-run-result/v1`；核对 run、Task、Prompt、canonical metadata（含 status）、claim 状态、before/after workspace 与真实 allowed-path 变化；校验声明的文件 hash、预期产物、时间和验证命令声明。成功结果必须声明全部预期产物；失败/阻塞可缺少产物，但每个缺失路径须出现在 blocker 中。验证命令记录只是声明，完成流程仍须实际重跑并记录退出码。
- `workspace.py`：snapshot/hash 支持最终路径为普通文件的 safe-in-worktree symlink；对目标执行 strict resolve、in-root 检查、nofollow/nonblocking regular-file FD hash，并复核链接 inode 与链接文本。逃逸、断链、循环、目录链接、FIFO、设备文件和链接竞态均失败关闭。目录 symlink 不递归遍历。

## 实际静态检查

| 切片 | 命令 | 结果 |
| --- | --- | --- |
| Prompt renderer | `PYTHONPYCACHEPREFIX=/tmp/spec016-pycache-promptguard /workspace/researchagent-cli-venv39/bin/python -m py_compile scripts/sdd_tasks/prompts.py` | 退出码 0 |
| Prompt renderer | `RUFF_CACHE_DIR=/tmp/spec016-ruff-cache /workspace/researchagent-cli-venv39/bin/ruff check scripts/sdd_tasks/prompts.py` | 退出码 0，All checks passed |
| Result validator | `PYTHONPYCACHEPREFIX=/tmp/spec016-pycache-strict /workspace/researchagent-cli-venv39/bin/python -m py_compile scripts/sdd_tasks/results.py` | 退出码 0 |
| Result validator | `RUFF_CACHE_DIR=/tmp/spec016-ruff-cache /workspace/researchagent-cli-venv39/bin/ruff check scripts/sdd_tasks/results.py` | 退出码 0，All checks passed |
| Symlink hashing | `PYTHONPYCACHEPREFIX=/tmp/spec016-pycache-symlinks /workspace/researchagent-cli-venv39/bin/python -m py_compile scripts/sdd_tasks/workspace.py scripts/sdd_tasks/results.py` | 退出码 0 |
| Symlink hashing | `RUFF_CACHE_DIR=/tmp/spec016-ruff-cache /workspace/researchagent-cli-venv39/bin/ruff check scripts/sdd_tasks/workspace.py scripts/sdd_tasks/results.py` | 退出码 0，All checks passed |

上述切片各自执行了以 `/tmp` 快照为左侧输入的 `git diff --no-index --check`；命令因文件有差异返回 1，均无 whitespace 诊断输出。Prompt/结果/ symlink 的独立行为测试正在由独立测试代理执行，完成后会在本 artifact 追加确切命令和结果。本代理没有声称这些行为测试已通过。

## 边界

结果校验不执行任务声明的命令，也不把结果 JSON 中自报的成功当作命令执行证据。completion runner 必须使用声明的安全 argv 再次执行、收集真实退出码/时长并将脱敏短收据关联到该 run，然后才能进入完成 journal 流程。`ValidationReport` 只报告验证结果，不写 DB/Git。

## Independent behavior-test results (completed cases)

- Prompt renderer, including nonclaimable Spec and unsatisfied-gate refusal: `PYTHONDONTWRITEBYTECODE=1 /workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_prompts -v` — exit 0, 7 tests passed in 5.321s; `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_prompts.py` — exit 0, all checks passed.
- Workspace safe/escaping symlinks: `PYTHONDONTWRITEBYTECODE=1 /workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_workspace -v` — exit 0, 5 tests passed in 1.062s; `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_workspace.py` — exit 0, all checks passed.
- The independent Result suite below includes partial-failure artifacts, claim-state/status drift, and safe artifact-symlink cases.
- Result validator: `PYTHONDONTWRITEBYTECODE=1 /workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_results -v` — exit 0, 9 tests passed in 13.230s; `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_results.py` — exit 0, all checks passed. Coverage includes failed/blocked missing-artifact blockers, success command declarations, change classifications/hashes, stale snapshots/Task authority, and safe/escaping artifact symlinks.
