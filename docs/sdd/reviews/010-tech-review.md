# 技术评审：spec-010 后端测试覆盖率提升至 80%

- 评审角色：开发主管（tech-lead）
- 评审对象：`docs/sdd/specs/010-backend-coverage-80.md`
- 评审时间：2026-08-29
- 评审方式：基于真实代码核对（Read routes.py / chat.py / main.py / 服务层 + 现有测试 test_api.py）

## 结论：通过（附意见）

## 达标可行性判定：**能到 80%（余量充足）**

缺口 = 88 条语句。经逐函数核对，未覆盖语句主要来自「从未被执行过的端点入口」，补测收益明确：

| 目标 | 可触达/未覆盖 | 补测手法 | 预估新增覆盖 |
| :--- | :--- | :--- | :--- |
| `routes.py` 未触达端点 | health / get_settings(GET) / put_settings(PUT) / get_task / probe / login_completed / chat 共 7 端点 | TestClient + patch 外部依赖 | ~55–65 |
| `routes.py` run_agent 内部 generate 分支 | 模型不存在 error / search 异常 502 / 无候选 / 全低置信度 4 个 return 分支 | patch build_task + search_articles + get_available_models | ~15–20 |
| `chat.py` build_chat_graph + ask_model | 15 未覆盖 | mock model.stream 返回若干 chunk | ~13 |
| `main.py`（backend/main.py） | 5 未覆盖 | `import backend.main` 即覆盖 | ~5 |
| **合计** | | | **~90–100** |

即仅「未触达端点 + chat.py + main.py」就足以覆盖 88 条缺口并留 50% 余量；异常分支补测进一步扩大安全垫。**结论：达标可行，且无需依赖最难的强耦合模块。**

## 评审意见

| 维度 | 判定 | 说明 |
| :--- | :--- | :--- |
| 改动面 | ✅ | 仅新增 `tests/**`，零业务改动。测试组织为 2 个新文件 + 并入既有文件，合理。 |
| 补测路线可行性 | ✅ | routes.py 144 未覆盖中约 70% 是「未触达端点」，TestClient + patch 可高收益覆盖；非强耦合死结。 |
| 可控 vs 强耦合分支 | ⚠️ 已识别 | 见下方「难测分支清单」。可测性整体良好，无不可测死结。 |
| 离线 mock 策略 | ✅ 合理 | 用 `unittest.mock.patch` 打 `routes` 模块命名空间下的 `get_available_models`/`search_articles`/`probe_pdf_url`/`skill_status`/`build_chat_graph`/`download_article`/`download_under_skill`，与现有 test_api.py 一致做法，天然离线。 |
| 兼容性 | ✅ | 只读调用现有路由，不改请求链路；patch 在测试进程内生效，不影响生产。 |
| 容错 | ✅ | spec 要求异常路径断言错误类型/状态码，覆盖 run_agent 的 4 个 return、download 的 503/502/404/PermissionError 分支。 |
| 安全 | ✅ | 纯测试，无 innerHTML / 密钥 / 新输入面；mock 隔离后不产生真实网络请求。 |
| 模型与上下文预算 | ✅ | 执行配置沿用本地 Ollama 已注册名（qwen3.8:27b / qwen3.5:9b），无含 `/` 非法名，符合 AGENTS.md。 |

## 难测分支清单（需重点关注 / 优先 mock，不得真跑）

| 函数/端点 | 难测原因 | 建议 mock 点 |
| :--- | :--- | :--- |
| `routes.py:download_under_skill`（download_paper_skill.py） | 内部走 `subprocess` 子进程调用本地 skill 脚本，且 SKILL_DIR 硬编码为 `/Users/wjh/.codex/skills/download-paper` | **必须** patch `routes.download_under_skill` / `routes.skill_status`，绝不真执行子进程 |
| `routes.py:download_article_endpoint` → `probe_pdf_url` / `download_article` | `httpx.stream` 真实网络 + 递归探测 | patch `routes.probe_pdf_url` 返回预设 `(status,url)`；patch `routes.download_article` 返回迭代器 |
| `routes.py:chat` / `run_agent(chat)` → `build_chat_graph` | langgraph `get_stream_writer` + ChatOllama 流式 | patch `routes.build_chat_graph` 返回一个 `graph.stream()` 可迭代的假对象（或用 mock 的 model.stream） |
| `chat.py:ask_model` | `get_stream_writer()` 需 graph 运行上下文 | 直接测 `build_chat_graph(model).stream(...)`，model 用 mock；或 patch `chat.get_stream_writer` |
| `routes.py:login_completed` | 内部再次调用 `download_article_endpoint` | patch `routes.download_article_endpoint` 或复用其 mock 链，避免真实下载 |

## 建议补测优先级（供实现侧排序）

1. **P0 高收益低风险**：health / GET settings / PUT settings / get_task / probe —— 全是无外部依赖或轻 mock，直接抬升覆盖率。
2. **P1 chat.py + main.py**：`import backend.main`（+5）、`test_chat_graph` 用 mock model（+13），性价比最高。
3. **P2 routes 剩余端点**：chat 端点、login_completed、run_agent 各 return 分支（用 P0 同款 patch 手法）。
4. **P3 异常分支**：download 的 503/502/PermissionError/404、search 的 502，逐一对断言状态码。
5. **P4 兜底**：article_search 纯函数（`_score` / `_candidate_from_payload`）/ article_download（`safe_filename`）若仍未达标再补。

## 强制约束（实现必须遵守）

- **T1**：所有 patch 目标必须是 `backend.app.api.routes.<symbol>` 命名空间（与现有 test_api.py 一致），禁止 patch 到 httpx / subprocess 内部实现。
- **T2**：任何涉及 `download_under_skill`、`download_article`、`probe_pdf_url`、`build_chat_graph` 的用例，**先 mock 再调用**，测试运行期间不得出现真实子进程、真实 HTTP、真实 Ollama 调用（可用 `unittest.mock` 的 `assert_called` / 断网复跑来验证）。
- **T3**：`login_completed` 用例必须把其下游 `download_article_endpoint` 一并 mock（或走 mock 链），不得触发真实下载。
- **T4**：chat.py 用例的 mock model 必须返回**至少 2 个非空 content chunk**（覆盖 `ask_model` 的 `answer_parts` 累加分支），并断言最终 `answer` 拼接正确，禁止只断言「不报错」。
- **T5**：`main.py` 覆盖用例允许「import 即覆盖」，但须额外断言 `backend.main.app is backend.app.main.app` 或 `hasattr(app, "routes")` 之类的真实结构断言，避免纯 import 空用例（满足 C2「必须含真实断言」）。
- **T6**：新增用例须断言**具体状态码与响应字段**（如 `assertEqual(response.status_code, 503)` + 断言 `detail`），不得仅 `assertEqual(200)` 后结束。

## 风险定级：低（含 2 个受控点）

| 风险 | 等级 | 缓解 |
| :--- | :--- | :--- |
| 误执行真实子进程/网络导致测试不可重复 | 中（已控） | T2/T3 强制 mock；验收 V3「断网可跑」复验 |
| `skill_status` 依赖本地 `/Users/wjh/.codex/skills` 真实文件存在 | 低（已控） | 一律 patch `routes.skill_status`，不依赖真实文件 |
| 为凑覆盖率写无断言空测试 | 低（已控） | C2 + T4/T5/T6 + V3 多重锁定 |
| 覆盖率因环境差异波动（如 cov 版本） | 低 | 目标区间 80%–85% 留余量，88 条缺口 vs ~90–100 预估收益 |

## 阻塞项
无。可进入实现阶段。
