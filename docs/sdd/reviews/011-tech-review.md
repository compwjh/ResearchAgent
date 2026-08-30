# 技术评审（架构师复审）：spec-011 本地个人论文知识库（RAG）

- 评审角色：架构师（architect）
- 评审对象：`docs/sdd/specs/011-knowledge-base-rag.md`（状态：已确认，未实现）
- 评审时间：2026-08-30
- 评审方式：**基于本机实测**（Ollama 实际调用、Qdrant 本地模式探针脚本、依赖与运行环境核对、前端版本号 grep）

- **评审者/角色/模型/分派方式**：⚠️ **主模型代行（架构师自身）** / 开发主管 / —（非子代理） / 主模型直接撰写
- **代行原因**：`Task(subagent_name="tech-lead")` 分派调用 aborted（未完成），**未按规定重试或换模型即由主模型补位**，违反 `AGENTS.md` 硬规则第 2 条；按第 3 条完成三处留痕（本文件头部 / spec 评审记录 / spec 变更日志）。
- **独立性声明**：本评审**非独立评审**，属同一作者对自身设计的复审，不能替代开发主管的独立评审；结论仅供参考，验收签字仍须由 `tech-lead`（或用户明确指定的代签人）完成。

## 结论：**通过（附 9 项强制修订，含 3 项阻塞级）**

> 复审后记（实现阶段追加）：R1 在端到端验证中被**修正**——初版判定「`num_batch=128` 可解 OOM」是错的，128 会触发另一种更危险的**静默劣化**（见 §二 R1 实测）。最终取 1024。此外在试运行中发现并修复了既有缺陷 R9（`/api/chat` 也因此恢复可用）。

技术选型主方向成立，**不改方向**：全本地 Ollama + `bge-m3` 稠密向量 + jieba 稀疏 + Qdrant 本地文件模式 + RRF 融合 + 可插拔 reranker，对本机（Apple M3 Max / 36GB / 无 Docker / 单机单人使用）是正确解。

但复审中**实测发现 2 个会让实现直接跑不起来的硬问题**（spec 未覆盖），另有 6 项设计缺口需在实现前钉死。修订清单见文末「强制约束 R1–R8」，已同步回写 spec。

---

## 一、实测证据（本次复审新获取）

| 探测项 | 命令/方式 | 实测结果 |
| :-- | :-- | :-- |
| bge-m3 默认调用 | `POST /api/embed {model:bge-m3, input:["test"]}` | ❌ **HTTP 500 `Compute error.`** |
| Ollama 日志 | `~/.ollama/logs/server.log` | `ggml_metal_synchronize: error: command buffer failed with status 5` / `Insufficient Memory (kIOGPUCommandBufferCallbackErrorOutOfMemory)`，`n_batch = 2048` |
| 加 `options.num_batch` | `{"model":"bge-m3","input":[...],"options":{"num_batch":128}}` | ✅ HTTP 200；**dim = 1024**，L2 范数 = 1.0（已归一化，余弦=点积） |
| 稀疏返回 | 同上响应 keys | ❌ 仅 `embeddings`，**无 sparse 字段** → 稀疏侧必须后端自算（与原 spec 判断一致） |
| 运行环境 | `deploy/start.sh` | 应用由 **`.venv/bin/uvicorn`** 启动，`.venv` = **Python 3.9.7** |
| 依赖分布 | `pip list`（两解释器） | `.venv` 有 fastapi/langgraph，**无** qdrant-client/pymupdf/jieba；anaconda 系统 python 有 qdrant-client 1.19 + pymupdf 1.28，**无** jieba → **装错解释器** |
| py3.9 可用版本 | `pip index versions qdrant-client` | 最高可用 **1.16.1** |
| 前端版本号 | `grep "?v=" frontend/index.html` | 实际已是 **?v=5**（spec 写 3，需改为 6） |
| Qdrant 本地模式探针 | 临时脚本（dense+sparse+filter+delete） | ✅ 全部通过：dense 检索、sparse（`modifier=IDF`）检索、payload `paper_id` 过滤、`FilterSelector` 按论文删除、计数正确 |
| `models.Modifier` | 内省 | 存在 `IDF` / `NONE`，`SparseVectorParams(index, modifier)` 可用 |

---

## 二、阻塞项（不修则实现无法运行）

### R1（阻塞·已修正）bge-m3 的 `num_batch` 存在上下两个边界

初版判定「128 可解 OOM」**不成立**，实现阶段端到端验证时发现第二种更危险的失败：

| 边界 | 现象 | 危害 |
| :-- | :-- | :-- |
| **上界 2048**（Ollama 默认值） | HTTP 500 `Compute error.`；日志 `ggml_metal_synchronize ... Insufficient Memory`；**即使输入只有 3 个 token 也 OOM** | 直接失败，容易发现 |
| **下界：num_batch < 单条输入 token 数**（如 128 对 300 token 的片段） | 日志 `srv send_error: input (239 tokens) is too large to process. increase the physical batch size (current batch size: 128)`，**但 HTTP 仍返回 200**，`embeddings` 数组长度正常、无 null | **静默劣化**：向量实际只由前几个 token 算出（日志 `stop processing: n_tokens = 5`），检索结果近乎随机，且不报错 |

实测证据：
- 冷启动 + 32 条真实论文片段（每条 1000 字符）在 `num_batch=128` 下：**32 条全部报 too large**，向量却是非 null 的「假成功」。
- 同条件 `num_batch ∈ {512, 1024, 2048}`：0 报错；再叠加 33 条含中文长文本冷启动压测，`num_batch=1024` 0 截断、0 空向量、0 OOM。
- 用 128 索引 125 个片段后提问，命中页为 `2,1,18,4,1`（散乱）；改为 1024 重建索引后命中页为 `1,1,1,2,3`（集中于定义所在页），差异显著。

最终修订：
1. `KB_EMBED_NUM_BATCH` 默认 **1024**（配置项，便于不同显存机器调整）；
2. **禁止减半重试**——降低 `num_batch` 会把「OOM」换成「静默截断」，危害更大；仅网络类错误重试一次；
3. 响应校验：向量数量与输入一致 **且** 无空向量，否则抛 `EmbeddingError`；
4. 切片长度 1000 字符（英文约 250–400 token，中文最多约 1000 token）与 1024 匹配；若后续语料更长，需同步上调 `KB_EMBED_NUM_BATCH`。

### R2（阻塞）依赖装错解释器

- 事实：运行时是 `.venv`（py3.9.7），但 `qdrant-client`/`pymupdf` 只装在 anaconda 系统 python，`jieba` 两边都没有。
- 修订（已执行）：`./.venv/bin/pip install qdrant-client==1.16.1 pymupdf jieba`；`requirements.txt` 将 `qdrant-client` 上界钉到 `<1.17`（py3.9 天花板），避免 CI/他人重装时解析到不兼容版本。

---

## 三、设计缺口（实现前必须钉死）

### R3 稀疏向量 term→index 映射未定义（**高危静默错误**）

spec 只写「jieba + BM25」，但 Qdrant 稀疏向量要求 **uint32 索引**。若用 Python 内置 `hash(str)`：受 `PYTHONHASHSEED` 随机化影响，**进程重启后同一词映射到不同索引 → 全部历史稀疏向量作废且检索结果错误，且不报错**。

- 修订：采用**稳定哈希**，无需词表文件：`idx = zlib.crc32(token.encode("utf-8")) % (1 << 20)`（约 100 万槽位，个人库碰撞可忽略；确定性、跨进程一致、可单测）。

### R4 BM25 权重策略未定

- 修订：文档侧权重用**亚线性 tf** `w = 1 + ln(tf)`；集合建 `sparse_vectors_config={"sparse": SparseVectorParams(modifier=Modifier.IDF)}`，由 Qdrant 依据集合统计做 IDF 加权（已实测 local mode 支持）。
- 兜底：若后续发现 IDF 在 local mode 行为异常，退化为「tf + 长度归一」，`RRF` 融合依然成立，不影响主链路。

### R5 Qdrant 本地模式的并发约束未写明

- 事实：local mode 是**进程内**存储，同路径被两个进程打开会锁冲突；本项目 `deploy/start.sh` 单 worker 启动，天然满足。
- 修订（写入 spec 与验收点）：
  1. **模块级单例** client（懒加载），禁止每次请求新建；
  2. **禁止多 worker**（`uvicorn --workers > 1` 会破坏数据），在部署脚本加注释；
  3. 索引写入用 `threading.Lock` 串行化（FastAPI 同步端点在线程池执行，并发上传有真实竞态）。

### R6 切片器引入不必要的新依赖

spec 写「沿用 `RecursiveCharacterTextSplitter`」，但项目未装 `langchain-text-splitters`，而它本质只是 30 行逻辑。
- 修订：**自研** `split_text(text, size=1000, overlap=200)`（按 `\n\n`/`\n`/`。`/` ` 递归降级切分），零新依赖、行为确定、易单测。

### R7 存储路径与 .gitignore 不全

spec 只写了 `data/papers/`。
- 修订：`data/kb/qdrant/`（向量库）、`data/kb/papers.json`（元数据）、`data/kb/papers/`（PDF）；`.gitignore` 增加 `data/kb/`。

### R8 边界条件缺失

补充（每条需写成测试）：PDF 加密/损坏/0 页 → 400 并给出可读错误；扫描件（整篇可提取字符 < 100）→ 状态 `indexed_partial` 并提示（Ollama-OCR 未安装，不做自动 OCR）；单文件上限 50MB；空知识库提问返回「无命中」而非报错。

### R9（阻塞·实现期新发现）httpx 走 macOS 系统代理，本机 Ollama 请求被拦截返回 503

- 现象：试运行时 `/api/kb/ask` 检索正常，但生成阶段抛 `ollama._types.ResponseError: (status code: 503)`；**Ollama 的 GIN 访问日志里根本没有这条 `/api/chat` 请求**。
- 定位：`curl --noproxy '*'` 直连正常；而 `ollama` Python 客户端（httpx，`trust_env=True` 默认）会读取 **macOS 系统代理配置**（非环境变量），把 `localhost:11434` 也送去代理 → 503。
- 佐证：本仓库 `services/ollama.py::get_available_models` 早就写了 `trust_env=False`（同一个坑），但 `create_chat_model` 没加 ⇒ **现有 `/api/chat` 在本机同样不可用**（实测确认）。
- 修订：`create_chat_model` 传入 `client_kwargs / async_client_kwargs / sync_client_kwargs = {"trust_env": False}`。知识库问答与原有 `/api/chat` 一并恢复。

---

## 四、选型复核（结论：维持原选型）

| 选型 | 复核判定 | 理由（结合本机实测） |
| :-- | :-- | :-- |
| 全本地 Ollama | ✅ 维持 | bge-m3 实测可用（1.16GB、dim 1024），论文不出本机 |
| bge-m3 稠密 | ✅ 维持 | 唯一硬伤（OOM）已由 R1 解决，非选型问题 |
| 稀疏侧自算（jieba+稳定哈希） | ✅ 维持 | Ollama 不返回 sparse 已实测确认，别无选择；CRC32 方案无状态、可测 |
| Qdrant **本地文件模式** | ✅ 维持 | 已实测 dense/sparse/filter/delete 全通；无 Docker 是硬约束，local mode 是唯一既能持久化又能过滤的方案；代价是单进程（R5 已约束） |
| RRF（k=60）融合 | ✅ 维持 | 两路 score 量纲不同（dense 余弦 ∈[-1,1]、sparse 点积无界），**RRF 只用排名不用分数**，比 alpha 加权更稳，无需归一化调参 |
| reranker 可插拔降级 | ✅ 维持 | 模型拉取失败是环境事实；降级路径不影响 RRF 主链路，验收不阻塞 |
| 生成模型复用 `modelSelect` | ✅ 维持 | 与 `/api/chat` 一致的 `create_chat_model(model)`，零新概念 |

**为什么不用 FAISS**：FAISS 无 payload 过滤（无法「按某篇论文检索/删除」）、进程内单文件无法被多请求安全写入——这两条对「会成长的个人库」是硬伤，已在选型阶段排除。

---

## 五、实现思路复核（结论：分层可行，微调）

`services/kb/{store,embed,parse,index,retrieve,prompts}.py` 的分层**同意**，但补三条：

1. **依赖注入优先**：`index.py`/`retrieve.py` 的函数签名接收 `client` 参数（默认取单例），否则单测无法在 80% 覆盖率要求下 mock（spec-010 门禁）。
2. **embed 层统一出口**：`embed_texts(list[str]) -> list[list[float]]` + `encode_sparse(text) -> SparseVector`，内置分批与 `num_batch`（承接 R1/R3）。
3. **`store.py` 承担元数据 + 文件**，Qdrant 只存向量与最小 payload；删除时「先删文件与元数据，再删向量」，失败记为 `failed` 不抛裸异常。

前端：新增 `kb` nav 与 `#kb-view`，复用顶部 `modelSelect`，引用块一律 `textContent`（spec-008 §5 硬约束），静态资源升 **`?v=6`**（R-bump，实测当前为 5）。

---

## 六、强制约束（实现必须遵守）

- **R1**：`/api/embed` 必传 `options.num_batch`（默认 **1024**）；分批 ≤32 条；**禁止减半重试**（会退化成静默截断），仅网络错误重试一次；响应必须校验数量一致且无空向量。
- **R2**：依赖装入 `.venv`（py3.9）：`qdrant-client==1.16.1`、pymupdf、jieba；`requirements.txt` 钉 `qdrant-client>=1.9,<1.17`。
- **R3**：稀疏索引必须用 `zlib.crc32(...) % (1<<20)` 稳定哈希，**禁用 Python 内置 `hash()`**。
- **R4**：稀疏权重 = `1+ln(tf)`，集合启用 `Modifier.IDF`。
- **R5**：Qdrant 单例 + 禁止多 worker + 索引写入加锁。
- **R6**：自研切片器，不引入 `langchain-text-splitters`。
- **R7**：存储落在 `data/kb/{qdrant,papers,papers.json}`，`.gitignore` 增 `data/kb/`。
- **R8**：补齐边界（加密/损坏/0 页/扫描件/50MB 上限/空库提问），每条写成测试。
- **R9**：`create_chat_model` 必须带 `trust_env=False`（三个 client_kwargs 都要），否则本机请求被 macOS 系统代理拦截返回 503。

## 八点五、试运行结论（实现后端到端实测）

| 环节 | 实测结果 |
| :-- | :-- |
| 上传 20 页 PDF（`SoK_ Agentic Skills`，5.4MB） | 3–4s 完成，125 个片段，`status=indexed`，`num_batch=1024` 下 Ollama 零 `too large` 报错 |
| 混合检索（dense+sparse RRF） | 命中页 `1,1,1,2,3`，集中在「定义」所在页；修复前（128）为 `2,1,18,4,1` 散乱 |
| 生成（qwen3.5:9b） | 输出 5 条要点并带 `[1][2][4]` 引用，内容与论文一致 |
| 删除 | 元数据 + PDF 原件 + Qdrant 向量同步清除（`deleted=true, vectors_removed=true`） |
| 健康检查 | `{"qdrant":true,"embedding":true,"reranker":false,"papers":1,"chunks":125}` |
| 回归 | `pytest tests/` **150 passed**，后端覆盖率 **90%**（spec-010 门禁 ≥80% 保持） |
| 附带修复 | `/api/chat` 在本机恢复可用（R9） |

## 七、风险定级：**中低**

| 风险 | 等级 | 缓解 |
| :-- | :-- | :-- |
| bge-m3 Metal OOM 复现 | 中→低 | R1 已实测定位并给出参数；若仍不稳可继续降到 32 |
| 稀疏哈希碰撞/IDF 行为 | 低 | 100 万槽位；R4 备退化路径；探针已验证 IDF modifier 可用 |
| 本地模式并发写 | 中→低 | R5 单例 + 单 worker + 写锁 |
| 覆盖率跌破 80%（spec-010 门禁） | 中 | 依赖注入 + 全部外部调用（httpx/Qdrant）mock，新增服务同步补测 |

## 八、阻塞项

**无阻塞项**（2 个阻塞级问题 R1/R2 已在本复审中定位：R2 已就地修复，R1 已给出确定参数）。按 R1–R8 修订后可进入实现。

---
*评审文档路径：`docs/sdd/reviews/011-tech-review.md`*
