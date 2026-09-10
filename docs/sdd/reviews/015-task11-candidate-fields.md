# Spec015 Task11 候选来源字段接线报告

## 结果状态和摘要

已完成。PaperCandidate 的出版阶段与来源元数据、ConferenceSource 的 discovery_routes 已接入 SQLite 快照；新字段追加在 dataclass 末尾，保持现有位置参数构造兼容。SQLite 仍使用 schema version 1，启动时对旧表执行幂等增量迁移；旧候选默认为 `published` / `dblp` / 空来源值。

## 改动文件

- `backend/app/domain/paper_discovery.py`
- `backend/app/services/paper_discovery_store.py`

未修改 API、下载器、前端或测试代码。

## 测试命令、退出码和结果

- `.venv/bin/python -m py_compile backend/app/domain/paper_discovery.py backend/app/services/paper_discovery_store.py` — 退出码 0。
- `.venv/bin/python -m pytest -q tests/test_paper_discovery_store.py tests/test_paper_discovery_search.py` — 退出码 0，23 passed。
- 临时旧 schema SQLite 迁移与来源字段往返脚本 — 退出码 0，`legacy migration and source roundtrip ok`。
- `git diff --check`（含两个未跟踪修改文件的 no-index 检查）— 退出码 0，无空白错误。

## 产物路径

- `.codebuddy/agent-logs/junior-dev-spec015-task11-candidate-fields-20260905T031016Z.md`
- `docs/sdd/reviews/015-task11-candidate-fields.md`

## 决策依据

新增 dataclass 字段全部追加到末尾，避免影响已有位置参数调用。SQLite 新表直接包含字段，旧表由 `ALTER TABLE ... ADD COLUMN` 添加；JSON 列 `source_links` 与 `discovery_routes` 使用 `[]` 默认，字符串来源字段使用 `published` / `dblp` 默认，详情页与 arXiv 标识为空。全程保留 schema version 1，符合现有迁移契约。

## 风险与阻塞

无阻塞。`source_links` 与 `discovery_routes` 的 URL/路线内容校验仍由来源适配器或上层负责，本任务仅负责候选快照持久化。

## 主 Agent 后续动作

请读回两个代码文件，运行 Task11 来源解析器/arXiv 及全量相关回归，并在集成分支完成统一验收与提交；确认 accepted/prepublication 候选的上游字段映射到 PaperCandidate 后再进入 API/导入链路验收。

## 开始、结束和总耗时

- 开始：2026-09-05 03:10:16（Asia/Shanghai）
- 结束：2026-09-05 03:19:00（Asia/Shanghai）
- 总耗时：约 8 分 44 秒

## 模型、token 和工具调用统计

- 模型：gpt-5.6-luna high（按本次任务指定）
- token：未提供运行时 token 计数
- 工具调用：约 12 次（读取、补丁、编译、测试与临时迁移验证）

## 后续补充：USENIX 内置来源路线

2026-09-05 03:17–03:18（Asia/Shanghai）补充 USENIX Security 内置 seed：

- `usenix_accepted`：`https://www.usenix.org/conference/usenixsecurity{yy}/cycle{cycle}-accepted-papers`，启用，最小间隔 1.0 秒。
- `arxiv_fallback`：启用，最小间隔 3.0 秒。

CCS、IEEE S&P、NDSS 仍保存空路线。升级旧数据库时仅为路线为空的 USENIX 内置记录补齐默认路线，不覆盖已有自定义配置。

补充验证：`py_compile` 通过；存储/搜索定向测试 23 passed；新库默认路线和旧 seed 升级断言通过；`git diff --check` 通过。
