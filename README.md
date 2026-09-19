# ResearchAgent

ResearchAgent 是一个面向科研工作的本地 AI 助手，提供论文检索、论文下载、知识库构建、混合检索和基于引用的问答能力。项目采用 FastAPI 后端和原生 HTML/CSS/JavaScript 前端，模型服务默认通过本机 Ollama 提供。

## 当前功能

### 对话与 Agent

- 提供普通聊天和流式响应。
- 支持文章助手 Agent，根据任务选择检索、下载等能力。
- 支持查看和修改 Agent 设置。
- 集成 `download-paper` 技能，用于论文下载流程编排。
- 记录模型调用、路由、链路和性能相关的观测信息。

### 论文检索与导入

- 支持 Crossref、OpenAlex 等文章元数据检索能力。
- 支持 USENIX Security 官方论文目录检索。
- 支持 DBLP 作为书目信息辅助来源。
- 支持异步论文搜索、来源进度、事件查询和分页结果。
- 支持会议列表、已接收论文列表和论文候选结果。
- 支持单篇导入、批量导入、失败重试、租约恢复和幂等处理。
- 下载阶段包含 URL、重定向、SSRF、文件大小、PDF 魔数、页数和临时文件安全检查。
- ACM/IEEE 等需要登录的下载流程使用受控的 Playwright 浏览器会话。

### 本地知识库与 RAG

- 支持 PDF 导入、分页文本提取、文本规范化和分块。
- 支持分块 v1/v2，以及基于规则和本地模型的边界判断。
- 支持 dense+sparse 混合检索、RRF 融合和可选 reranker。
- 支持论文引用过滤、页码引用和带引用的问答响应。
- 支持知识库重建、删除和状态查询。

### 开发与运维

- FastAPI 同时挂载后端 API 和静态前端资源。
- SQLite 用于本地任务、论文目录和搜索状态持久化。
- 后端按 `api`、`application`、`domain`、`infrastructure`、`platform` 等边界组织。
- 项目规则、SDD 流程、Agent 定义和共享技能位于 `AGENTS.md`、`.codebuddy/` 和 `docs/sdd/`。

### Langfuse 二次开发

本项目将 Langfuse v4.27.0 源码固定在 `vendor/langfuse/`，在其基础上增加面向本地 Ollama 的观测扩展。二次开发的重点是：

- 为聊天和知识库 RAG 链路补充统一的 trace、span 和 generation 结构。
- 将模型加载、预填充、首 token、解码和网络/框架开销拆分为可比较的阶段指标。
- 记录思考内容与正式输出、输入/输出 token、吞吐、冷启动状态及 `langchain`/`direct` 链路维度。
- 增加 Ollama 专用的统计查询和 Insights 页面，帮助定位首 token 慢、冷启动慢和链路开销问题。
- 增加 Langfuse 不可用或关闭时的静默降级，确保观测系统故障不影响聊天和知识库业务。

这样做的原因是：Langfuse 原生观测能够记录调用，但不能直接按本项目 Ollama 的本地运行特征拆解首 token 和阶段耗时；二次开发后，模型性能问题可以在同一套 trace 和统计视图中定位，而不需要另建一套观测平台。

## 项目架构图

打开 [ResearchAgent 项目架构图](docs/architecture/research-agent-architecture.html) 查看可交互的 Archify 架构图。

对应的 Archify 规格文件是 [research-agent.architecture.json](docs/architecture/research-agent.architecture.json)。该图基于仓库 commit `5a8181fabdbf11b776d9435eae3cf17fd40167b4` 的代码路径生成，包含 Research Task Runtime、动态模型路由和 Langfuse 观测层。

## 快速开始

### 1. 安装 Python 依赖

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

根据本机环境编辑 `.env`。不要将 `.env` 或任何 API key、密码、token 提交到 Git。

### 3. 准备 Ollama

先确认本机已安装 Ollama，再检查模型名称：

```bash
ollama list
```

复杂 Agent 和后端任务可使用项目配置中的 `qwen3.8:27b-mlx`；测试和轻量任务可使用 `qwen3.5:9b`。模型必须以 `ollama list` 的实际结果为准，并在本机的 CodeBuddy 配置中完成注册。

### 4. 可选：启动 Langfuse 观测平台

如果需要查看模型调用观测，先按 [Langfuse 部署说明](deploy/langfuse/README.md) 启动本地基础设施和 Web/Worker，再在 `.env` 中配置 `LANGFUSE_ENABLED`、`LANGFUSE_HOST` 以及对应的 project keys。Langfuse 默认关闭，关闭或不可用时不影响主要业务。

### 5. 启动服务

```bash
./deploy/start.sh
```

浏览器访问 [http://127.0.0.1:8000](http://127.0.0.1:8000)。后台启动：

```bash
./deploy/start.sh -d
```

停止后台服务：

```bash
./deploy/stop.sh
```

服务默认只绑定 `127.0.0.1`，不会自动公开到公网。详细部署说明见 [deploy/README.md](deploy/README.md)。

## 测试与检查

```bash
.venv/bin/python -m pytest -q
```

后端代码检查：

```bash
cd backend
../.venv/bin/ruff check .
```

## 目录结构

```text
backend/app/
├── api/                  # FastAPI 路由、请求和响应 schema
├── article_assistant/    # 文章检索与下载
├── chat/                 # 聊天领域和 LangGraph 流程
├── knowledge_base/       # PDF 解析、分块、索引和检索
├── paper_discovery/      # 论文目录、来源、导入和批量任务
├── platform/             # 设置、模型、观测和平台装配
└── main.py               # FastAPI 应用入口

frontend/                 # 原生 HTML/CSS/JavaScript 前端
docs/sdd/                 # Spec、任务计划、评审和复盘文档
.codebuddy/               # 项目级 Agent、技能和模型注册配置
deploy/                   # 本地启动与停止脚本
tests/                    # 后端与前端契约测试
```

## 当前限制

- 论文发现与导入仍处于 Spec015 的持续收口阶段，部分外部数据源、真实登录、公开 PDF 和 GUI 验收需要对应的外部网络或账号环境。
- Ollama 模型权重不随 Git 仓库分发，需要在每台开发机单独安装和拉取。
- 本地数据、论文文件、SQLite 数据库和运行日志默认不提交到 Git，具体规则见 `.gitignore`。
- 当前部署脚本是单进程本地部署，不包含 HTTPS、容器化和进程守护。

## 多 Agent 协作

- 项目级规则入口为根目录 `AGENTS.md`。
- Agent 定义和共享技能位于 `.codebuddy/agents/` 与 `.codebuddy/skills/`。
- 每个 Spec 使用独立特性分支，Agent 通过独立分支或 worktree 协作。
- Agent 不直接推送或合并到 `main`；提交信息遵循 Conventional Commits，并关联对应 Spec 编号。

## 相关文档

- [SDD 文档入口](docs/sdd/README.md)
- [部署说明](deploy/README.md)
- [后端说明](backend/README.md)
- [Spec015 论文发现与知识库导入](docs/sdd/specs/015-security-paper-discovery.md)
- [Spec017 后端限界上下文模块化](docs/sdd/specs/017-backend-bounded-context-modularization.md)
