# 技术评审：Spec017 后端限界上下文彻底重构

- **评审者**：开发主管（Tech Lead）
- **实际模型**：当前协作 Agent
- **评审对象**：`docs/sdd/specs/017-backend-bounded-context-modularization.md` 与 `docs/sdd/plans/017/`
- **评审时间**：2026-09-05（Asia/Shanghai）
- **评审方式**：核对当前 `backend/app` 的真实 import 图、路由、配置和测试；未修改业务代码、Spec 或 Git 状态。

## 结论：打回

目标目录和“无旧 import / 无兼容转发”的一次性迁移原则正确，也符合当前代码中 `api/routes.py` 直接装配基础设施、`services/kb/__init__.py` 过大 facade 的实际问题。但目前 Spec 与任务计划尚未把关键跨上下文端口、配置所有权和迁移时序固定到可实施程度。按现稿执行会迫使编码 Agent 自行决定 `paper_discovery → knowledge_base` 的依赖形式，并会让 Task04 与 Task06 同时迁移同一份设置数据，存在边界倒退和并行冲突风险。

在下列必改项写回 Spec017/任务计划并复审通过前，不得进入业务代码迁移。

## 代码事实核对

- `backend/app/api/routes.py` 是单一 `/api` 路由，含 20 余组系统、论文、文章、聊天及 KB 端点；它直接持有 `TaskStore`、`PaperDiscoveryStore`、`PaperImportBatchStore`、`PaperBrowserManager` 等单例，并直接 import KB store/index/retrieve、Ollama、浏览器和 HTTP 实现。拆路由是必要且可行的。
- `backend/app/services/paper_import.py` 直接 import `services.kb.index`、`services.kb.store`、`services.kb.tasks`。这与目标“论文发现只能通过 KB application 入口协作”冲突，不能只靠移动文件解决。
- `backend/app/services/kb/__init__.py` re-export index、store、tasks、retrieve 等 30 余成员；`main.py` 和路由依赖它。Task05 正确要求移除此 facade，但必须先固定替代入口和依赖反转方式。
- `ArticleSettings` 同时包含 article 与 `paper_discovery_*` 字段；`load_article_settings` 同时处理 `data/article_settings.json`、`ARTICLE_SETTINGS_JSON`、文章环境变量和论文发现环境变量，而 `save_article_settings` 整体覆盖 JSON。现有 `/api/agent/settings` 的 Pydantic 请求体也直接使用该对象。
- 当前测试大量从旧路径直接 import（例如 `backend.app.services.kb.*`、`backend.app.domain.*`、`backend.app.agents.*`、`backend.app.api.routes`）。一次性迁移可行，但迁移清单必须把这些测试 patch 点和 public test helper 一并列为强制迁移项。
- 当前聊天链路是 `services.ollama → graphs.chat → domain.chat`，文章 agent 反向从 `agents.article_agent` 动态 import `services.ollama`。重构后需避免把 `platform` 依赖业务模块，或让业务 application 绕过 platform 直接调用模型基础设施。

## 评审矩阵

| 维度 | 判定 | 结论 |
|---|---|---|
| 目标目录 | 基本可行 | 五个业务上下文加 `platform` 与 `api` 覆盖当前实现；允许按复杂度省略空层也合理。 |
| 依赖方向 | 打回 | Spec 图写为 `api → application → domain / infrastructure`，但边界又要求路由只能调用 application；两种描述不一致，且未定义跨上下文调用能否直接 import 对方 application。 |
| 论文发现与 KB 协作 | 打回 | 当前 paper import 直连 KB 内部 store/index/tasks；Task04/05 未固定 port、DTO、错误/幂等语义或由哪一任务先提供入口。 |
| API 拆分与装配 | 基本可行 | Task03 可先拆路由；但不能只“定义未来入口”，应明确 composition root 可创建哪些 infrastructure 实例、路由如何取得 application service。 |
| 配置保留 | 打回 | “分离对象且写入保留另一方字段”方向正确，但没有 JSON ownership/合并算法、未知字段策略、环境变量优先级或 `/agent/settings` 旧请求体映射契约。 |
| 一次性无兼容迁移 | 附条件可行 | 可不保留旧路径，但所有生产、测试、脚本、启动 import 和 monkeypatch 路径必须在同一变更集改完；Task02 的基线是必要前置。 |
| 任务依赖与并行 | 打回 | Task04 和 Task06 都涉及设置拆分；Task04 与 Task05 又需要跨上下文 import contract。它们现在标为可并行，却共同修改接口/装配边界。 |
| 验证设计 | 基本可行 | OpenAPI 快照、关键请求/响应比较、静态依赖检查、全量回归正确；还需明确快照标准化和边界检查的可执行规则。 |

## 必须修订项

1. **固定依赖规则与端口形态。** 把依赖规则统一为：`api` 仅依赖各上下文的 `application` 公共入口；`application` 依赖自身 `domain` 与通过构造函数注入的 port；`infrastructure` 实现 port；`domain` 仅依赖标准库/本上下文领域模型。明确跨上下文只允许调用对方 `application` 的显式 facade，禁止 import 对方 domain/infrastructure；`platform` 仅提供横切适配与 composition-root 支持，不能 import 业务模块。
2. **补论文导入—KB 端口契约与任务顺序。** 定义由 KB 暴露的最小导入 application interface（输入候选快照/受信任本地 PDF，输出稳定 `paper_id`、索引状态、稳定错误码；不暴露 Qdrant/store/task 对象）。Task03 建立接口和注入位置，Task05 先实现 KB adapter，Task04 再切换论文发现调用；或者将两任务改为不可并行的明确依赖。必须同时规定导入幂等与 v1/v2 索引完成语义沿用现有行为。
3. **把设置拆分前置且固定持久化矩阵。** 将 `ArticleAssistantSettings`、`PaperDiscoverySettings`、一个仅负责读写的 settings repository 放到 Task03（或新增独立前置任务），供 Task04/06 消费。固定：旧 JSON key 到新对象的映射、环境变量覆盖顺序、保存时 read-modify-write 保留另一域及未知 key、无效旧字段的处理、原子写入策略，以及原 `/api/agent/settings` 请求/响应字段保持不变的 adapter。Task04/06 不得并行移动同一 repository 或数据文件。
4. **补全 API composition-root 契约。** Task03 应列出每个子路由的模块、端点归属、路由前缀保持方式、请求/响应 schema 的最终位置，以及应用生命周期 hook 的注册方式。定义 application service 的创建地点（推荐 `platform.bootstrap`/明确 factory）和 FastAPI dependency/provider 的测试替换点，消除当前 routes 模块级单例。
5. **将全量迁移清单设为硬门禁。** Task02 的产物需逐项列出每个 `.py` 实现、测试、启动/部署脚本、import/monkeypatch 字符串、目标目录、负责人任务和删除时机；同一文件只能归属一个任务。尤其涵盖 `observability`（迁至 `platform`）、`core/config.py`、`core/article_settings.py`、所有 `services/kb/__init__.py` facade 消费者，以及 `tests/test_api_routes_coverage.py` 等路由 patch 点。
6. **定义静态边界检查的机械规则。** 在 Task07 明确使用的检查脚本/测试及允许表：禁止 `api` import `*.infrastructure.*`、禁止 domain import FastAPI/httpx/Playwright/Qdrant/Ollama/env config、禁止业务模块间循环；同时允许 application 的 protocol/DTO import。对无法以 import 判定的运行时装配规则，加入 architecture test 而非文字承诺。
7. **明确外部契约基线比较方式。** Task02 冻结 OpenAPI JSON 时必须剔除不稳定字段并记录 FastAPI/Pydantic 版本；Task07 比较 path、method、operation request/response schema、状态码和 error body。关键端点至少逐一覆盖当前论文、KB、文章助手、聊天、健康接口；禁止将内部模块名/operationId 的变化误当作 API 兼容失败，除非前端实际依赖。

## 可实施的修订后顺序

`02 契约与全量迁移清单 → 03 settings/platform/API composition root + 跨域 application contract → 05 KB application/adapter → 04 paper_discovery（使用 KB contract） → 06 article_assistant/chat（使用已拆分 settings/platform） → 07 删除旧结构与边界验证 → 08 验收部署`。

Task04 与 Task06 可在 Task03 完成设置拆分后并行；Task04 不得早于 Task05 的 KB application contract 可用。若团队希望 04/05 并行，必须在 Task03 先冻结 protocol/DTO 和由 platform 提供的临时 wiring，但不得借此保留旧 `services.kb` 转发。

## 最低放行验证（修订后）

- 单独的 import-graph architecture tests 能检出 API 直连基础设施、domain 外部副作用依赖、`platform → business` 反向依赖及业务间循环。
- 设置兼容测试覆盖：旧 JSON、仅环境变量、混合配置、保存文章设置不丢论文设置、保存论文设置不丢文章设置、未知键保留，以及 `/api/agent/settings` 的原 JSON 契约。
- 论文导入使用 fake KB application port 的单测，不允许测试/生产代码从 paper discovery import KB store/index/tasks。
- OpenAPI 标准化快照和现有 API 关键场景在迁移前后等价；全量测试改到新 import 路径并通过。

## 风险定级：中高

本次是横跨全部后端的目录移动，但主要风险不是文件移动本身，而是将现有隐式服务耦合重新包装成新的跨目录直接 import。先固定跨域端口、设置 repository 和 composition-root，才能保证“彻底迁移”真正减少耦合而不是换名保留。

## 阻塞项

- 技术评审当前为**打回**；上述七项未修订、未复审通过前，Spec017 保持待确认，不进入业务代码迁移。
