# Spec032 Task13：032.1 余项移交审计

> 审计时间：2026-09-20（Asia/Shanghai）；本轮复核追加于同日
> 范围：032.1 Task08（IDE 本地 USENIX 助手）与 Task10（会话 Skill 粘性）
> 结论：**部分 PASS；USENIX 检索→导入真实 smoke 通过，Task10 真实连续会话仍待补证**

## 1. 结论摘要

| 子项 | 状态 | 结论 |
| --- | --- | --- |
| Task08 IDE Skill | **PASS（静态/契约/真实 smoke）** | Skill、搜索脚本、导入脚本均已存在；脚本只调用产品 HTTP API，且不可达时中文报错、非 0、无 traceback。新版异步结果 snapshot 的 `source_page_url` 作为官方详情页回退；本轮另修复不可达提示固定写 8000 的问题，改为显示实际 `--base-url`。18080 真实检索返回 3 篇候选，第三篇通过既有导入链成功 `indexed`。 |
| Task10 会话 Skill 粘性 | **PASS（代码/定向链路）** | `conversation_active_skill` 独立表、仓储读写、会话路由 `_resolve_sticky_skill` 和连续两轮工具链路已真实接线；测试覆盖激活、沿用、切换、退出、禁用清理、会话/owner 隔离。 |

## 2. Task08 证据

- Skill 文档已存在于 `.codebuddy/skills/usenix-paper-assistant/SKILL.md:1-46`，明确 IDE Skill 只消费本地 ResearchAgent API，不抓取 USENIX、不直接下载 PDF、不接受任意 URL，并给出检索→导入顺序与服务未启动提示。
- `search_papers.py:58-107` 调用 `POST /api/papers/searches`（固定 `conference_ids=["usenix-security"]`），轮询 `GET /api/papers/searches/{id}`，再读取冻结结果；候选 ID 来自服务端 `catalog_paper_id`。`source_page_url` 是新版冻结 snapshot 的官方详情页字段，已在 `:94-103` 加入优先回退链。
- `download_paper.py:14-57` 只提交 `search_id` 与 `candidate_id` 到 `POST /api/papers/imports`；产品端再从服务端 snapshot 解析候选并执行既有下载、白名单、身份和知识库导入链路。
- 产品合同核对：`backend/app/api/routes_paper.py:112-144`、`:160-182`、`:458-510` 与 `backend/app/api/schemas.py:138-176` 证明上述请求字段/状态/响应字段真实存在；异步结果 snapshot 在 `backend/app/paper_discovery/application/catalog_search_graph.py:1067-1087` 输出 `catalog_paper_id`、`abstract_status`、`source_page_url`。
- 主 Agent 随后在当前工作树前台服务上复跑真实链路：`search_papers.py --base-url http://127.0.0.1:18080 --query agent --years 2024 --limit 3` 返回 `search_id=f830dfc9d80e4c25bfd8a1da808c6cc6`、状态 `partial` 和 3 个候选（标题、年份、USENIX 详情页、摘要状态均返回）。第一篇重复导入按预期返回 HTTP 409；第二篇按既有失败合同返回 HTTP 424；第三篇 `077bbff9185f9f53d049e966115d36d3` 成功返回 `paper_id=7dfec772f919481aad9fc3bcbcf96041`、`status=indexed`、`existing=false`。这证明 IDE Skill → 产品 API → 既有安全下载/导入链真实打通；搜索的 `partial` 状态仍需在最终报告中如实呈现。

## 3. Task10 证据

- 表在 `backend/app/memory/migration.py:252-259` 建立，使用独立 `conversation_active_skill`，不改 frozen `Conversation` dataclass；`MemoryRepository` 的 `ActiveSkill` 与 owner-scoped 读写在 `backend/app/memory/repository.py:152-162`、`:492-546`。
- 会话路由在 `backend/app/api/routes_conversations.py:696-763` 实现退出词、命中写入、显式不可用清除、无命中沿用、注册表禁用/删除清除和正文缺失清除；接线点在 `:883-929`，产品 registry 作为真相源，`.codebuddy/skills/` 不被产品链路扫描。
- `tests/test_skill_carryover.py:54-101` 覆盖会话/owner 隔离、切换、退出与禁用清理；`:122-178` 覆盖连续两轮点名后第二轮沿用 Skill 并携带 `search_paper_catalog` 工具。
- 说明：该实现使用固定产品 owner `OWNER_ID`（当前默认 `local-user`），route 层没有把客户端 owner 作为输入，因此未产生跨任务串台；repository setter 的 `ON CONFLICT(conversation_id)` 仍应由后续安全评审考虑是否补 conversation-owner 一致性校验，但不是本次审计阻塞项。

## 4. 验证记录

| 命令 | 退出码 | 结果 |
| --- | ---: | --- |
| `.venv/bin/python -m pytest -q tests/test_skill_carryover.py` | 0 | 4 passed |
| `.venv/bin/python -m pytest -q tests/test_conversations_api.py tests/test_memory_repositories.py tests/test_skill_intent.py` | 0 | 73 passed |
| `.venv/bin/ruff check .codebuddy/skills/usenix-paper-assistant/scripts/search_papers.py .codebuddy/skills/usenix-paper-assistant/scripts/download_paper.py` | 0 | 通过 |
| `PYTHONPATH=. .venv/bin/python -m py_compile`（两脚本） | 0 | 通过 |
| 离线 `_json_request` 契约探针（`source_page_url` → `article_url`） | 0 | PASS |
| 两脚本以 `127.0.0.1:9` 探测服务不可达 | 2 / 2 | 中文错误、无 traceback |
| `search_papers.py --base-url http://127.0.0.1:18080 --query agent --years 2024 --limit 3` | 0 | 返回 `partial`、3 个真实候选及官方详情页 |
| `search_papers.py --base-url http://127.0.0.1:9 --query agent --years 2024 --limit 3` | 2 | 明确不可达探针；中文错误、实际端口为 9、无 traceback |
| `download_paper.py`（候选 `997cbc09e69d06d23ce0ea17281614f0`） | 2 / HTTP 409 | 重复论文，服务明确返回“论文已在知识库中” |
| `download_paper.py`（候选 `24e12495bb127db4a8d345e12e50b54c`） | 2 / HTTP 424 | 既有导入失败合同，未伪造成功 |
| `download_paper.py`（候选 `077bbff9185f9f53d049e966115d36d3`） | 0 | `paper_id=7dfec772f919481aad9fc3bcbcf96041`，`status=indexed`，`existing=false` |
| `.venv/bin/python -m pytest tests/test_skill_carryover.py -q`（本轮） | 0 | 4 passed in 1.82s |
| `.venv/bin/ruff check`（两份 IDE 脚本与 Task13 测试） | 0 | All checks passed |
| `.venv/bin/python -m py_compile`（两份 IDE 脚本） | 0 | 通过 |
| `git diff --check --`（已跟踪改动范围）及新增文件无空白诊断检查 | 0 / 无诊断 | 通过；新增文件的 `git diff --no-index --check /dev/null <file>` 因预期存在 diff 返回 1，但没有 trailing-whitespace 输出 |
| `.venv/bin/ruff check` 扩大到已有 backend/test 文件 | 1 | 工作区既有告警（`repository.py` 旧 F401/SIM/F811 与 Task13 测试 import 排序），未将其伪报为本次 Skill 改动问题 |

## 5. 本次改动、边界与风险

- 本轮修改 `.codebuddy/skills/usenix-paper-assistant/scripts/search_papers.py` 与 `download_paper.py`：保留既有 `source_page_url` 官方详情页回退，并让不可达错误显示实际 `--base-url`；更新 `tests/test_skill_carryover.py` 锁定该输出契约。
- 未修改 `frontend/**`、`.agents/skills/**`、论文来源适配器或产品后端实现；会话粘性为工作区已有接线，本次只做审计和证据记录。
- 风险/阻塞：Task08 真实检索与一篇新论文导入已验证；搜索本次为 `partial`，另有重复/失败候选，需保留失败队列语义。Task10 的真实连续两轮会话仍未通过浏览器/API 复现，不能据此收口 032.1。

## 6. 主 Agent 收口动作

1. 将本文件纳入 Task13 交接，保留“Task08 静态/契约/真实 smoke PASS、Task10 真实连续会话待补证”的双层结论。
2. 不要重复实现 Task08 或 Task10；Task08 真实 smoke 已有证据，后续只补 Task10 连续会话真实复现。
3. 若要消除扩大 Ruff 的基线告警，应另开明确范围的后端/测试清理任务，不在本 Task13 追改。

## 7. Task10 真实会话 smoke 追加记录（2026-09-20）

- 健康探针：`curl -sS -w '\\nhealth:%{http_code}\\n' http://127.0.0.1:18080/api/health`，沙箱外退出码 `0`，HTTP `200`，服务返回 `status=ok`。
- 第一轮命令：`POST http://127.0.0.1:18080/api/conversations/messages`，内容为“使用 usenix-catalog-orchestration 搜索 agent 论文”，SSE 已返回 `skill_intent` completed 与 `intent`，其中 `skill=usenix-catalog-orchestration`、`source=rule`；未调用下载接口。该流按 HTTP `200` 建立。
- 第一轮状态复核：`GET /api/conversations/7e957237e2c44a25a752242efc301ee1/messages` 返回 HTTP `200`；助手消息仍为 `status=streaming`、`last_event_seq=7`、无完成时间，说明 Ollama/模型生成阶段约 60 秒后未收口。
- 第二轮精确文本“就下载第一篇吧”未执行：平台安全门禁判定该请求可能触发真实论文下载、外部网络及知识库写入；在“不下载论文”约束下不能绕过门禁。因此不能声称第二轮 sticky tool smoke 成功。
- 阻塞：真实模型生成未完成，且第二轮下载语义需要不触发副作用的测试 seam 或另行授权的受控环境。Task10 真实连续两轮仍待补证。

### Task10 无副作用第二轮补证（2026-09-20）

- 在同一会话发送“继续搜索第一篇吧”，未触发下载或文件写入。
- SSE 返回 `skill_intent=completed`，并明确返回 `intent`：`skill=usenix-catalog-orchestration`、`source=sticky`、`confidence=1.0`。这证明会话路由在用户不再次点名 Skill 时仍沿用已激活 Skill。
- 该轮生成阶段随后长时间保持 `streaming`（`last_event_seq=7`），属于当前 Ollama 生成收口慢的运行时问题；不影响 sticky intent 事件已被真实 API 观察到。
- 精确文本“就下载第一篇吧”仍未执行，因此不把下载工具调用标记为真实 PASS。若需关闭最后证据缺口，需要无副作用测试 seam 或用户明确授权的受控环境。
