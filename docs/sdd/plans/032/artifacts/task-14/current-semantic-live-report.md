# Spec032 Task14：Semantic Scholar 当前部署真实 API 验收

> 角色：tester；范围：当前 `127.0.0.1:8000` 上 Semantic Scholar 只读 API
>（autocomplete、citations、references）；本报告不替代 Spec032 全量 E2E、四会议年度覆盖、研究任务导入或人工修复验收。

## 最终裁决

**BLOCKED（范围受限的 API live slice 通过，但不能交付为 Spec032 全量人工验收）。**

- 本轮 API slice：`PASS`。健康探活、autocomplete 两次调用、citations 和 references 各一次调用均为 HTTP 200；响应符合 metadata-only 公开契约，没有观察到凭据、Cookie 或 provider 授权头泄漏。
- 全量 Spec032：`BLOCKED / NOT_ASSESSED`。本轮按任务边界没有创建 Research Task、没有下载 PDF、没有改来源，也没有验证自然语言 Intake、候选评估→批准计划→导入、失败论文恢复、前端入口或最终报告产物。Task17 也明确图辅助前端入口仍关闭。
- P0/P1：`0`（本轮没有发现功能缺陷）。
- 证据原文与结构化记录：[evidence.json](./evidence.json)。

## 范围、前置条件与限制

- Spec：032；验收关联：Task14、Task15、Task16、Task17。
- 运行分支：`codex/spec032-final-acceptance`。
- 运行提交：`5b1b1d918db8858e848a73da4cee2df54f513ea2`（`docs(deploy): record main push receipt`）。
- 服务地址：`http://127.0.0.1:8000`；部署命令遵循 `deploy/README.md` 的默认端口约定。
- 已知公开 paper identity：`ARXIV:2403.11445`（当前 Spec032 Task14 Semantic Scholar 研究记录中的固定 probe identity）。未读取 `.env`、输出 `.env` 或任何 API key。
- 请求按串行顺序执行，未并发；每个 endpoint 的调用次数不超过 2 次。没有收到 429，因此本轮没有触发 Retry-After 退避；应用自身请求仍通过进程级共享限流器。未主动制造 429，以免增加外部调用。
- 所有请求均为 GET 只读调用；没有创建研究任务、下载/读取 PDF、变更来源、写入产品实体或调用内部函数。

## 运行时探活

| 请求 | 状态 | 耗时 | 脱敏响应要点 |
|---|---:|---:|---|
| `GET /api/health` | 200 | 33.438 ms | `status=ok`，`paper_discovery_enabled=true`；模型列表为公开运行时能力信息，未包含凭据 |

服务探活成功后才继续业务 API；没有把旧端口或旧分支证据混入本报告。

## 真实 API 请求与响应

### 1. autocomplete

路由契约：`GET /api/papers/semantic-scholar/autocomplete`，`query` 为非空、最多 100 字符，`limit` 为 1–20；成功响应只投影 `paper_id/title`。

| 请求 ID | 脱敏请求 | 状态 | 耗时 | 真实结果 |
|---|---|---:|---:|---|
| `autocomplete-01` | `GET /api/papers/semantic-scholar/autocomplete?query=Noise-Augmented%20Privacy-Preserving%20Empirical%20Risk%20Minimization&limit=5` | 200 | 2404.533 ms | `query` 原样回显；`candidates=[]`。这是 provider 的空匹配成功响应，不是错误体。 |
| `autocomplete-02` | `GET /api/papers/semantic-scholar/autocomplete?query=privacy&limit=5` | 200 | 3628.177 ms | 5 条去重候选，字段仅 `paper_id/title`：`1d1a045884911fe99b502960bf9e2718b32c238a`（Privacy and freedom）、`123d00c6a664ea6d4da57d0d89d980dd02347c79`（Privacy Preserving Data Mining）、`f2f8f7a2ec1b2ede48cbcd189b376ab9fa0735ef`（Privacy-preserving deep learning）、`abb826f40ce51ffb1154231640c35537faa0712e`（Privacy in Context: Technology, Policy, and the Integrity of Social Life）、`df077652e3e119e28a81d8a2e9d26f4e91c34676`（Privacy as contextual integrity）。 |

判定：`PASS`。两次均为真实 provider 响应；第二次证明短候选去重与 `limit=5` 投影生效；第一条空候选保持 200，不被伪装为“有结果”。

### 2. citations

路由契约：`GET /api/papers/semantic-scholar/{paper_id}/citations`，`paper_id` 受控、`limit` 为 1–100、`offset` 非负；响应为 `relation/source_paper_id/items/offset/next_offset/total`，图边仅带论文元数据。

| 请求 ID | 脱敏请求 | 状态 | 耗时 | 真实结果 |
|---|---|---:|---:|---|
| `citations-01` | `GET /api/papers/semantic-scholar/ARXIV:2403.11445/citations?limit=3&offset=0` | 200 | 3581.230 ms | `relation=citations`，`source_paper_id=ARXIV:2403.11445`，3 条 `items`，`offset=0`，`next_offset=3`，`total=null`（provider 未返回 total）。 |

保留的真实实体（摘要在 Artifact 中按明确截断规则保存）：

- `affe4beb57abb513df3974d874aab8fd92eff19c` — *Privacy-Preserving Rényi Layer-Wise Budget Allocation Against Gradient Leakage for Federated Learning*，2026，DOI `10.1109/tmc.2025.3618185`。
- `7958772ef27f2fef3e04190f6cfb21a1919752c2` — *Metric Embedding Initialization-Based Differentially Private and Explainable Graph Clustering*，2025，DOI `10.48550/arxiv.2509.06214`，arXiv `2509.06214`。
- `0eded5cf7033f6082311bf692d07ee2e99817712` — *Meeting Utility Constraints in Differential Privacy: A Privacy-Boosting Approach*，2024，DOI `10.1109/sp61157.2025.00064`，arXiv `2412.10612`。

判定：`PASS`。关系、源 identity、metadata-only item 和分页字段均存在；没有报告、目录或 PDF 写入证据。

### 3. references

| 请求 ID | 脱敏请求 | 状态 | 耗时 | 真实结果 |
|---|---|---:|---:|---|
| `references-01` | `GET /api/papers/semantic-scholar/ARXIV:2403.11445/references?limit=3&offset=0` | 200 | 9232.776 ms | `relation=references`，`source_paper_id=ARXIV:2403.11445`，3 条 `items`，`offset=0`，`next_offset=3`，`total=null`（provider 未返回 total）。 |

保留的真实实体（摘要在 Artifact 中按明确截断规则保存）：

- `b845207461d896163d5c036d5d43da8f88e6dbb2` — *Privacy-Preserving Methods for Repeated Measures Designs*，2022，DOI `10.1145/3487553.3524216`。
- `fe6f8b49e73ca96f24c83cc933f3072c57a3e0c7` — *Optimal Accounting of Differential Privacy via Characteristic Function*，2021，arXiv `2106.08567`。
- `b60875567006195647f83963f0d86a9773bf1b7f` — *Tight Approximate Differential Privacy for Discrete-Valued Mechanisms Using FFT*，2020；`doi=null`、`arxiv_id=null`，响应中的 `abstract=null` 被保留为缺失而非编造。

判定：`PASS`。references 关系和 metadata-only 投影成立；缺失 DOI/arXiv/abstract 被如实保留。

## 限流、退避与脱敏核对

- 调用序列严格串行：探活 → autocomplete-01 → autocomplete-02 → citations-01 → references-01；没有并行请求。
- 业务调用均在前一调用返回后才发起，并复用服务端 lazy 单例 `SemanticScholarGraphClient` 的进程级 limiter；本轮没有并发或超限证据。
- 本轮没有 429/5xx/网络失败，故没有可记录的真实 `Retry-After` 值，也没有为了造失败而增加调用。已有实现的 Retry-After/有限退避只作为代码候选背景，不冒充本轮 live 证据。
- 入站请求不携带授权头或 Cookie；响应未出现 API key、Cookie、个人隐私或隐藏思维链。Provider `source_url`、作者名和论文元数据属于公开响应字段；Artifact 对长摘要做显式截断。
- 本轮未发出 POST/PUT/PATCH/DELETE，也未访问 PDF、Reader 或搜索 HTML。

## 人工验收案例与准备度

本轮无法生成可交付的用户 UI 验收案例：Task17 明确“前端 UI 入口仍保持关闭”，而本任务又限定为只读 API。下列步骤只作为 API 复现记录，不应交给用户当作完整产品验收：

1. 在已启动的 `http://127.0.0.1:8000` 服务上执行 `GET /api/papers/semantic-scholar/autocomplete?query=privacy&limit=5`，期望 HTTP 200 和最多 5 个 `{paper_id,title}` 候选。
2. 取固定 identity `ARXIV:2403.11445`，执行 `GET .../citations?limit=3&offset=0`，期望 HTTP 200、`relation=citations`、`next_offset=3`。
3. 在上一请求完成后执行 `GET .../references?limit=3&offset=0`，期望 HTTP 200、`relation=references`、metadata-only items。
4. 不应点击导入、下载或创建研究任务；图边结果不能直接进入报告引用。若收到 429，应等待服务端 Retry-After/有限退避并使用“可重试”错误状态；本轮未触发该路径。

### 十项准备度矩阵（仅本 API slice）

| # | 检查项 | 结果 | 证据/说明 |
|---:|---|---|---|
| 1 | 服务已启动并可访问 | PASS | `/api/health` HTTP 200，`paper_discovery_enabled=true` |
| 2 | 真实 API 创建入口成功 | N/A | 本轮只读图辅助 API；Task17 将其定义为 metadata-only，不创建任务或实体 |
| 3 | 主路径参数正确解析 | PASS | autocomplete query/limit；graph relation/paper_id/limit/offset 均得到正确响应 |
| 4 | 任务/实体状态推进 | N/A | 本轮没有异步任务；图边路由不持久化状态 |
| 5 | 前端显示处理中提示 | FAIL | Task17 记录前端 UI 入口仍关闭，未验证 |
| 6 | 用户知道何时点击或等待 | FAIL | 仅有 API 复现步骤，没有当前 UI 文案/等待提示 |
| 7 | 核心业务产物真实生成 | N/A | metadata-only 图边不生成报告、PDF 或 KB 产物 |
| 8 | 失败状态有可操作恢复 | N/A | 本轮只验证成功路径，未主动制造 429/5xx；代码层失败契约不替代 live 失败证据 |
| 9 | 页面状态与 API 状态一致 | FAIL | 没有开放的前端图辅助入口，无法验证页面对照 |
| 10 | 步骤文档可由无上下文用户复现 | FAIL | 可复现的是 API 调用，不是 Spec032 产品主路径；UI 文案未验证 |

本矩阵不满足 `PASS >= 9/10`，且没有自然语言 Intake、导入产物和人工失败恢复证据，因此最终不能标记 `READY_FOR_USER`。

## 代码候选与后续动作

- `code_candidates: []`；本轮没有发现需要由 `backend-dev` 修复的 P0/P1 或明确 API 功能缺陷。
- `total=null` 是本次 provider 响应的真实值，当前路由保留它并返回 `next_offset=3`；没有足够证据把它判为缺陷，不建议为本轮另改公开契约。
- autocomplete 的长标题查询返回空候选但 HTTP 200，短 query `privacy` 返回 5 条；这更像 provider 匹配结果差异，不构成服务错误。
- 若要解除本报告的 `BLOCKED`，后续应由 Task14/架构师补做全量 Spec032 门禁：自然语言主路径、来源覆盖、候选评估与批准计划、真实导入/失败队列恢复、重启、前端文案和最终报告版本，并单独生成不可变 Artifact；不应把本报告的只读 API 成功响应扩展解释为上述证据。

## 证据文件

- API 结构化证据：[evidence.json](./evidence.json)
- 相关路由：`backend/app/api/routes_paper.py:277`、`backend/app/api/routes_paper.py:312`
- 相关客户端：`backend/app/paper_discovery/infrastructure/semantic_scholar_metadata.py:216`
- Spec/任务边界：`docs/sdd/specs/032-research-source-expansion.md` 的 Semantic Scholar 扩展、接口、边界；`docs/sdd/plans/032/task-15-semantic-scholar-metadata-enrichment.md`、`task-16-semantic-scholar-bulk-recall.md`、`task-17-semantic-scholar-graph-assistance.md`
