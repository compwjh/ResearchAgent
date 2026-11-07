# Spec043 提 PR 前核验报告（verification-loop，2026-11-07）

执行范围：分支 `feature/spec-043-map-tags-and-ux-batch` 相对 `origin/main` 的全部改动（7 个本地提交）。命令均由主会话实际执行，输出如实记录，未把 N/A 项冒充通过。

## VERIFICATION REPORT

```
Build:     N/A  — 原生 HTML/JS/CSS，仓库无 package.json / 构建脚本；node --check 覆盖 PR 范围全部改动 .js 通过
Types:     N/A  — pyright 未安装；改以 py_compile 覆盖 PR 范围全部改动 .py，通过
Lint:      WARN — ruff 12 errors，均为既有债务；本次两个改动 .py 单独检查 All checks passed
Tests:     PASS — 4017 passed, 2 skipped, 67 subtests passed, exit 0
Security:  PASS — PR 范围 .py/.js 无硬编码密钥/令牌匹配
Diff:      125 files changed, +22477 / -897, 7 commits, merge-base 线性 OK
Overall:   READY for PR（lint 既有债务不阻塞，已在 PR 正文披露）
```

## Phase 1 — Build

- `ls package.json` → `NO_NPM_BUILD`：项目是原生 HTML/JS/CSS + FastAPI，没有 npm/pnpm 构建步骤。
- 对 `git diff --name-only origin/main...HEAD | grep '\.js$'` 的每个文件执行 `node --check` → `NODE_CHECK_ALL_OK`。
- 结论：**N/A（无构建产物可校验）**，语法层已覆盖。

## Phase 2 — Types

- `./.venv/bin/pyright --version` → `PYRIGHT_UNAVAILABLE`（项目未安装该依赖，不擅自新增）。
- `git diff --name-only origin/main...HEAD | grep '\.py$' | xargs ./.venv/bin/python -m py_compile` → `PY_COMPILE_OK`。
- 结论：**N/A（无类型检查器）**，语法层已覆盖。

## Phase 3 — Lint

`ruff check --output-format=concise` 对 PR 范围全部 `.py`：**12 errors**，逐条如下：

| 文件:行 | 规则 |
|---|---|
| `backend/app/literature_maps/application/service.py:1147` | SIM105 |
| `backend/app/literature_maps/application/service.py:1252` | SIM105 |
| `backend/app/literature_maps/infrastructure/store.py:2844` | SIM114 |
| `backend/app/literature_maps/infrastructure/store.py:3344` | SIM102 |
| `tests/frontend/test_frontend_literature_map_contract.py:8` | I001 |
| `tests/frontend/test_frontend_map_analysis_queue.py:3` | I001 |
| `tests/frontend/test_frontend_map_mobile_contract.py:9` | I001 |
| `tests/frontend/test_frontend_map_palette.py:15` | I001 |
| `tests/frontend/test_frontend_map_tags_ui.py:11` | F401 |
| `tests/literature_maps/test_map_tags_api.py:10` | F401 |
| `tests/research/test_single_paper_rag_intent_routing.py:15` | I001 |
| `tests/research/test_single_paper_rag_intent_routing.py:144` | F401 |

- 全部位于既有代码行（远离本批次改动区域），属历史债务；**本次两个改动文件** `backend/app/paper_discovery/application/paper_import.py` 与 `tests/paper_discovery/test_import_attempt_root_cleanup.py` 单独 `ruff check` → `All checks passed!`。
- 结论：**WARN，不阻塞本 PR**；不在 PR 前顺手修 12 处历史告警（避免范围扩大），建议另开 `chore/` 处理。

## Phase 4 — Tests

- 最终全量回归：`./.venv/bin/python -m pytest -q` → `4017 passed, 2 skipped, 5 warnings, 67 subtests passed in 827.12s`，**exit 0**（`docs/sdd/plans/043/artifacts/20261107-full-regression-final.log`）。
- 前序失败日志保留：`20261107-card-settings-full-regression.log`（2 failed，首次）、`20261107-full-regression-after-fix.log`（1 failed，冻结清单 hash 未同步），均不冒充全绿。
- 定向：`tests/frontend` 439 passed、`tests/literature_maps + 2 个 research 测试` 315 passed、`tests/paper_discovery` 1010 passed、冻结清单 2 passed、修复定向 6 passed。
- 真实 E2E：API 16/16、Chromium 32/32（6 截图、`page_errors=[]`）；部署 5/5 端点 200。
- **覆盖率：未测**。仓库无覆盖率采集配置，文档 `docs/github.md` 的「覆盖率 ≥ 80%」是规范预留，不得写成已达标。

## Phase 5 — Security

- 对 PR 范围全部 `.py` / `.js` 扫描 `sk-[A-Za-z0-9]{16,}` 与 `api_key = '…'` 形式的硬编码密钥 → **无匹配**。
- 仓库外 `sitecustomize` shim 相关修复只调整能力检测方式，未放宽 `lstat` / `S_ISDIR` / `is_symlink` / dev-ino token 校验，fail-closed 语义保留；新增 4 条非恒真回归用例锁定该边界。
- 结论：**PASS**。

## Phase 6 — Diff Review

- `git diff origin/main...HEAD --stat` → `125 files changed, 22477 insertions(+), 897 deletions(-)`（7 个提交累计，包含文档、评审、截图与 E2E 产物）。
- `git log --oneline origin/main..HEAD` → 7 条（见 PR 正文）。
- `git merge-base --is-ancestor origin/main HEAD` → `LINEAR_OK`：分支已线性位于 `origin/main` 之上，**无需 rebase**，不改写任何历史。
- 工作树仅两个无关未跟踪项 `.playwright-cli/`、`artifacts/jd-agent-infra-capability-map.md`，**未纳入提交/PR**。

## Issues to Fix（不阻塞本 PR，已披露）

1. ruff 12 条既有告警（上表），建议另开 `chore/` 处理。
2. 无真实 `.github/workflows/`，CI 全绿 / 覆盖率门禁为规范预留，无法自动化验证；本 PR 只提供本地验证结果。
3. 人工验收 8 步仍建议用户实走（已由真实 Chromium 自动化按同一路径执行，未冒充人工）。

## 结论

**READY for PR**：全量回归 exit 0、改动文件语法/静态检查干净、无硬编码密钥、分支线性、本地提交完整；lint 既有债务与无 CI 的事实已在 PR 正文如实披露。按 `docs/github.md` 与 `AGENTS.md`，本次只推送分支并创建 PR，**不合并 `main`、不 force push**，强制 Code Review approval 留给用户/开发主管。

## 补充记录（核验材料入库）

本核验报告与 `20261107-spec043-pr-body.md` 在六阶段核验完成后，以一条纯文档提交纳入分支，使 PR 中引用的路径真实存在。因此：

- 上文所有「7 个提交 / 7 commits / 7 条」均指**核验执行时所覆盖的代码提交范围**，是当时的真实快照，不回改历史数字；
- 最终推送的分支共 **8 个提交**，PR 正文的 Commit 表已按 8 条列全，最后一条为文档提交，不含任何业务代码；
- 该文档提交不改变 Build / Types / Lint / Tests / Security 的结论，也不改变 `4017 passed / exit 0` 的最终全量回归结果。
