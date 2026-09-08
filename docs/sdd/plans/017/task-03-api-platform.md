# 任务 03：拆分 API 与平台装配

> 关联：[Spec017](../../specs/017-backend-bounded-context-modularization.md) ｜ 索引：[README](./README.md)  
> 依赖：任务 02；当前状态：`已完成`

> 2026-09-08 收口：配置已迁入 `platform/config.py`，路由入口已去除兼容 facade，ProviderRegistry 与设置拆分通过回归。
> 本任务是 Task04/05/06 的**前置**：设置拆分、跨域 port 与 composition root 必须先于业务迁移交付。

## 目标

把聚合路由拆为按业务归属的 API 模块，并建立 `platform` 配置、Ollama、观测和生命周期装配入口；同时完成**设置拆分**与**跨域 port 定义**，为后续业务迁移提供稳定契约。

## 实施边界

- API 保持所有 `/api` 路径、schema 和错误行为；总注册入口统一 include 子路由。
- `main.py` 只保留装配职责；KB 启动恢复通过模块生命周期接口接入。
- 不在本任务移动论文、KB、文章或聊天业务实现，仅为它们定义 API/application 入口与装配边界。
- **设置拆分（技术评审必改项 3，前置交付）**：交付 `ArticleAssistantSettings`、`PaperDiscoverySettings` 与**唯一**的 settings repository，供 Task04/06 消费。写入必须 read-modify-write：保留另一上下文字段与未知 key，原子写（临时文件 + `os.replace`）。规则以 spec「环境与数据兼容性矩阵」为准，`/agent/settings` 请求/响应字段不变。
- **跨域 port 定义（技术评审必改项 2，只定义不实现）**：定义「论文导入 → 知识库」的 application port（Protocol + DTO），输入为候选快照 + 受信任本地 PDF 路径，输出为稳定 `paper_id`、索引状态与稳定错误码，**不暴露** Qdrant/store/task 对象。由 Task05 实现、Task04 消费。
- **composition root（技术评审必改项 4）**：给出 application service 的统一创建入口（推荐 `platform.bootstrap`）与 FastAPI dependency/provider 的**测试替换点**，消除 `routes.py` 的模块级单例。

## 分派与校验

每次最多迁移两个代码文件，先回传 diff 和测试结果；主 Agent 读回、运行 API 契约测试并确认路由列表未变化。评审时重点核对依赖方向（禁止 `api` 直连 infrastructure、禁止 `platform` 反向依赖业务模块）。

## 验收

- 不再存在单一业务聚合 `routes.py`。
- 路由/OpenAPI 基线差异仅允许模块来源变化，不允许路径、schema、状态码或错误体差异。
- 健康与应用启动测试通过。
- **设置**：保存文章助手设置后，论文发现配置与未知字段均未丢失；`PAPER_DISCOVERY_*` 环境变量仍按原优先级覆写；`/agent/settings` 的 GET/PUT 契约不变。
- **装配**：路由不再持有 `TaskStore`、`PaperDiscoveryStore`、`PaperImportBatchStore`、`PaperBrowserManager` 等模块级单例，改由 factory/dependency 注入，且测试可替换。
- **port**：跨域 port 以 Protocol + DTO 形式落盘，尚未被任何业务模块实现（实现留给 Task05）。
