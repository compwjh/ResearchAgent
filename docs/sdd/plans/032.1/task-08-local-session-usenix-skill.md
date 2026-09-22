# Task 08：本地会话可用的 USENIX 论文助手 Skill（含执行脚本）

> 关联：[spec-032.1](../../specs/032.1-usenix-skill-decoupling.md) ｜ 索引：[README](./README.md)
> 依赖：任务 04（产品侧 Tool 与 API 已就绪）；当前状态：`待执行，移交 Spec032 Task13`

> 2026-09-20：本任务保留为原始需求与验收记录，执行入口改为 [Spec032 Task13](../032/task-13-spec0321-carryover.md)；需按新版多来源合同核对既有 API，不得照旧文档假定端口 8000 或接口已完全接线。

## 一句话目标

让 **IDE 本地会话**里的 agent 也能检索并下载 USENIX 论文——在 `.codebuddy/skills/` 建立
带 `scripts/` 的 Skill，用 Bash 调用**本地产品服务的既有 API**，不重复实现抓取与下载。

## 背景与问题（用户实测反馈）

在本地会话中要求「使用 skill usenix-catalog-orchestration 下载一篇关于 agent 的论文」时，
模型回答「没有这个 skill，也没有联网访问 USENIX 的工具」。两层原因：

1. **Skill 目录不同**：`usenix-catalog-orchestration` 位于 `.agents/skills/`，
   **只被产品后端 `scanner.py` 加载**；IDE 本地会话加载的是 `.codebuddy/skills/`（研发类），
   因此本地会话看不到它。
2. **缺少工具**：Skill 只是协议文档，干活需要工具。产品侧已有
   `search_paper_catalog` / `fetch_paper_detail` / `download_and_import_paper`，
   但本地会话没有对应工具。

产品服务已在 `http://127.0.0.1:8000` 提供既有 API，可直接消费：

| 接口 | 用途 |
|---|---|
| `POST /api/papers/searches` | 发起检索（202，异步） |
| `GET /api/papers/searches/{search_id}` | 查询任务状态 |
| `GET /api/papers/searches/{search_id}/results` | 取冻结结果 |
| `POST /api/papers/imports` | 下载并导入论文 |

## 实施步骤与文件边界

1. 新建 `.codebuddy/skills/usenix-paper-assistant/SKILL.md`：
   - `name`: `usenix-paper-assistant`
   - `description`: **第三人称**，说明「需要检索或下载 USENIX Security 论文时使用」，
     并明确它依赖本地服务（`http://127.0.0.1:8000`）。
   - 正文用**祈使句**，给出可直接复制的 Bash 调用示例（先检索拿到候选，再下载指定一篇）。
   - **必须写明**：脚本只调用本地服务；不接受任意 URL；服务未启动时的处理。
2. 新建 `scripts/search_papers.py`：调用 `POST /api/papers/searches` 并轮询
   `GET /api/papers/searches/{search_id}/results`，输出候选列表
   （标题、年份、详情页 URL、摘要状态）。参数：`--query`、`--years`、`--limit`。
3. 新建 `scripts/download_paper.py`：调用 `POST /api/papers/imports` 完成下载导入。
   参数取自检索结果中的候选项。
4. 服务不可达时输出**可读的中文错误**并给出启动提示，不得抛出堆栈或静默失败。

**只允许新增** `.codebuddy/skills/usenix-paper-assistant/` 下的文件（SKILL.md + scripts/）。
**不要改** 产品后端 `backend/**`、`frontend/**`、`.agents/skills/*`。

## 子代理分派

角色 `backend-dev`（模型 `qwen3.8:27b-mlx`）。建议先加载 `skill-creator` 确保 SKILL.md 规范。
回传：脚本用法示例、实测输出、风险。

## 边界与明确不做

- **只消费既有产品 API，绝不重新实现**抓取、解析、下载或安全校验
  （这些能力产品侧已完备，重复实现即为第二套旁路）。
- 不接受任意 URL 入参；URL 必须来自检索结果，由服务端白名单校验。
- 不改产品侧任何行为；不改 `.agents/skills/` 下的四份 Skill。
- 不在脚本中内置 Cookie、密码或任何凭证。

## 验收

1. 服务运行时：执行检索脚本能返回真实候选列表（含标题与详情页 URL）。
2. 执行下载脚本能成功下载并导入一篇论文（可在知识库侧验证）。
3. 服务未启动：脚本输出可读中文错误与启动提示，**非 0 退出但不抛堆栈**。
4. 脚本不依赖新第三方库（标准库 `urllib`/`json` 即可，或复用项目 `.venv`）。
5. 不得新增第二套抓取/下载/安全校验实现（评审重点）。

## 产出物、执行结果与变更日志

### 移交至 Spec032 Task13 的执行结果（2026-09-20）

- 静态/契约：PASS。脚本路径为 `.codebuddy/skills/usenix-paper-assistant/scripts/search_papers.py` 与 `download_paper.py`；只调用本地产品 API，不接受客户端 URL。Task13 定向测试 `4 passed`，脚本 Ruff、`py_compile` 退出码均为 `0`。
- 不可达合同：PASS。`--base-url http://127.0.0.1:9` 退出码 `2`，输出中文错误、无 traceback；本轮修复错误文本显示实际 base URL，不再固定误报 8000。
- 真实服务：PASS（2026-09-20 复跑）。`search_papers.py --base-url http://127.0.0.1:18080 --query agent --years 2024 --limit 3` 返回 `partial` 和 3 个真实候选；随后第三个候选通过 `download_paper.py` 返回 `paper_id=7dfec772f919481aad9fc3bcbcf96041`、`status=indexed`、`existing=false`。首个候选重复导入返回 409，第二个候选返回 424，均符合失败/重复语义并记录在 [`artifacts/task-13/carryover.md`](../032/artifacts/task-13/carryover.md)。
