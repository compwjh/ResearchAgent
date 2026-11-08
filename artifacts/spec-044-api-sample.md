# Spec 044 —— API 成功产物样例（会话答案展示与溯源增强）

生成时间：2026-11-08（Asia/Shanghai）
分支：`feature/spec-044-conversation-answer-display-and-provenance`
服务：`http://127.0.0.1:8000`（`PORT=8000 ./deploy/start.sh -d`，PID 39989）

**本次验证任务**

| 项 | 值 |
|---|---|
| conversation_id | `e23710c72163432585155f12218683c9` |
| user_message_id | `d5fa490f27174dc3869e422c53edd8cb` |
| assistant_message_id | `05f0b5efb7b6419288a84fa043a8f655` |
| 模型 / 模式 | `qwen3.8:27b` / `normal`，`reasoning_effort=off` |
| 终态 | `done` / `status=completed` / `duration_ms=25160.54` |
| 处理步骤 | 3 步全部 `completed`，全部携带 `step-evidence-v1` 明细 |
| 产物路径 | `artifacts/spec044-sse-raw.txt`、`artifacts/spec044-processing-steps.json`、本文 |

---

## 前置：部署版本探活

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/            # 200
curl -s http://127.0.0.1:8000/api/health                                    # {"status":"ok","model":"qwen3.8:27b",...}
```

本地 vendor 静态资源（全部 `HTTP 200`，`size_download` 为真实字节数）：

| URL | 状态 | 字节 |
|---|---|---|
| `/assets/vendor/katex/katex.min.js?v=1` | 200 | 270325 |
| `/assets/vendor/katex/katex.min.css?v=1` | 200 | 23804 |
| `/assets/vendor/katex/fonts/KaTeX_AMS-Regular.woff2` | 200 | 28076 |
| `/assets/app.js?v=72` | 200 | 384709 |
| `/assets/styles.css?v=70` | 200 | 159103 |
| `/assets/processing-tree.js?v=2` | 200 | 17153 |
| `/assets/conversation-research.js?v=2` | 200 | 8318 |

> Reranker 模型文件缺失，服务以 RRF 降级模式启动（不影响本 spec 的对话与证据链路）。

---

## Spec 044 —— 发起一次真实回答 `POST /api/conversations/messages`

请求：

```bash
curl -sS -N --max-time 240 -X POST "http://127.0.0.1:8000/api/conversations/messages" \
  -H 'Content-Type: application/json' \
  -d '{"content":"请用一句话解释什么是知识库检索，并用 $E=mc^2$ 举例说明公式。"}' \
  -o artifacts/spec044-sse-raw.txt \
  -w "HTTP=%{http_code} bytes=%{size_download}\n"
```

真实输出：`HTTP=200 bytes=10141`，`Content-Type: text/event-stream`（`Cache-Control: no-cache`、`X-Accel-Buffering: no`）。

首个 `meta` 帧（真实响应，未截断关键字段）：

```json
data: {"type": "meta", "message_id": "05f0b5efb7b6419288a84fa043a8f655", "event_seq": 1, "timestamp": "2026-11-07T18:41:04.134383Z", "project_id": null, "conversation_id": "e23710c72163432585155f12218683c9", "user_message_id": "d5fa490f27174dc3869e422c53edd8cb", "assistant_message_id": "05f0b5efb7b6419288a84fa043a8f655", "model": "qwen3.8:27b", "mode": "normal", "reasoning_effort": "off", "capabilities_source": "cache"}
```

末帧 `done`（真实响应）：

```json
data: {"type": "done", "message_id": "05f0b5efb7b6419288a84fa043a8f655", "event_seq": 58, "timestamp": "2026-11-07T18:41:29.180591Z", "conversation_id": "e23710c72163432585155f12218683c9", "status": "completed", "duration_ms": 25160.54050019011, "reasoning_duration_ms": null, "answer_duration_ms": 25160.54050019011}
```

`progress` 帧仍保持轻量——**不含 `detail_json`**（A 域明细只经历史接口读取，SSE 帧体未变），末帧前一步为 `generation / completed / "回答已生成"`。

---

## Spec 044 —— 验证证据明细落库 `GET /api/messages/{message_id}/processing-steps`

请求：

```bash
curl -s "http://127.0.0.1:8000/api/messages/05f0b5efb7b6419288a84fa043a8f655/processing-steps" \
  -o artifacts/spec044-processing-steps.json -w "HTTP=%{http_code} bytes=%{size_download}\n"
```

真实输出：`HTTP=200 bytes=3206`。

3 个步骤全部 `completed`，且 `detail_json` 均为 `{"schema_version":"step-evidence-v1","records":[...]}`：

| 步骤 | status | records | 单条记录的真实字段 |
|---|---|---|---|
| `memory_recall` | completed | 5 | `kind, source_kind, ref_id, conversation_id, occurred_at, snippet`（**无 `score`**，符合「记忆类不编造分数」） |
| `system_rule` | completed | 1 | `kind, source_kind, ref_id="USER.md", snippet`（画像仅截断摘要） |
| `generation` | completed | 1 | `kind, title, snippet="耗时 25117ms；模型 qwen3.8:27b"`（无虚构 `source_kind`/`target`） |

关键校验（真实脚本输出）：

```
steps= 3
--- memory_recall completed detail_json= str:{"records": [{"conversation_id": "cc9f...
   schema= step-evidence-v1 records= 5
   rec keys= ['conversation_id', 'kind', 'occurred_at', 'ref_id', 'snippet', 'source_kind']
   rec keys= ['conversation_id', 'kind', 'occurred_at', 'ref_id', 'snippet', 'source_kind']
--- system_rule completed detail_json= str:{"records": [{"kind": "rule", "ref_id": "USER.md", ...
   schema= step-evidence-v1 records= 1
   rec keys= ['kind', 'ref_id', 'snippet', 'source_kind']
--- generation completed detail_json= str:{"records": [{"kind": "generation", "snippet": "耗时 25117ms...
   schema= step-evidence-v1 records= 1
   rec keys= ['kind', 'snippet', 'title']
```

> 修复前 `detail_json` 全为 `null`。P1-1 的扁平化修订在此得到运行时证明：所有字段处于脱敏 `depth ≤ 3`，`source_kind` / `ref_id` / `conversation_id` 均被保留；`source_ref` 嵌套与 `url` 键均不存在。

回答正文（真实 `GET /api/conversations/e23710c72163432585155f12218683c9/messages`）：

```
知识库检索是指从结构化或非结构化数据集中根据查询条件提取相关信息的过程，例如在输入 $E=mc^2$ 时，系统可快速定位并返回该质能等价公式的定义、推导背景及物理意义等上下文内容。
```

该回答含 `E=mc^2` 行内公式，是 C 域 KaTeX 渲染的可用真实样本。

---

## 补录（2026-11-08 实施收口）：B 域真实 RAG 命中与 `chunk_index` 落库

修复 B 域定位链路后重启服务（`launchctl remove/submit com.researchagent.recovery8000`，PID 88588，首页与 `/api/health` 均 200），以显式 `"reasoning_effort":"off"` 在绑定论文的会话触发真实知识库检索。

请求（`conversation_id=cc9f02f3d8184943bee35b4a23aa9481`）：

```bash
curl -sS -N --max-time 240 -X POST "http://127.0.0.1:8000/api/conversations/cc9f02f3d8184943bee35b4a23aa9481/messages" \
  -H 'Content-Type: application/json' \
  -d '{"content":"请用一句话说明这篇论文提出的比特币聚类验证方法。","reasoning_effort":"off","model":"qwen3.8:27b","mode":"normal"}' \
  -o artifacts/spec044-sse-rag-success.txt -w "HTTP=%{http_code} bytes=%{size_download}\n"
```

真实输出：`HTTP=200 bytes=29391`，帧型统计 `meta 1 / progress 7 / token 89 / sources 1 / done 1`，无 `error` 帧。关键帧：

```
progress  rag_retrieval  running   event_seq=5
progress  rag_retrieval  completed event_seq=6  summary="召回 5 条知识库证据"
sources   event_seq=98   5 条命中，均含 document_id / chunk_id / chunk_index / score / source_url
done      event_seq=99   status="completed"  duration_ms=62316.58
```

> 先前 `artifacts/spec044-sse-rag.txt` 失败的原因已定位：请求未带 `reasoning_effort`，后端默认填 `xhigh`（`routes_conversations.py:891`），本地 `qwen3.8:27b` 不支持该档位，返回 `REASONING_EFFORT_UNSUPPORTED`。显式传 `off` 后真实 RAG 链路贯通，**未伪造 `sources` 帧**。

`GET /api/messages/e66eeaa343c64a1aaf7bae5bfdba61d4/processing-steps` → `HTTP=200 bytes=6172`（`artifacts/spec044-processing-steps-rag.json`）。4 步全部 `completed`，全部 `schema_version: "step-evidence-v1"`。`rag_retrieval` 的 5 条记录真实字段：

```
['chunk_id', 'chunk_index', 'document_id', 'kind', 'score', 'snippet', 'source_kind', 'title']
rec0 document_id=55afc3b8f01445429462fe78ed0d4c98 chunk_index=38 chunk_id=086d957a-1352-51b5-9161-c3bcbba497b7
rec1 chunk_index=28  rec2 chunk_index=22  rec3 chunk_index=40  rec4 chunk_index=36
ALL_HAVE_CHUNK_INDEX=True   HAS_URL_KEY=False   HAS_NESTED_SOURCE_REF=False
```

即本次补入的 `"chunk_index": c.get("chunk_index")` 已真实落库并保持扁平（脱敏 depth ≤3）；C1「不落库 URL」与 P1-1 扁平化修订均在运行时成立。

## 补录：真实 Chromium B 域「定位到召回片段」端到端

脚本 `artifacts/spec044-b-domain-e2e.py`（Python Playwright，真实 Chromium headless），数据取自上面真实 `sources` 帧；结果落盘 `artifacts/spec044-b-domain-e2e.json`。

| 断言 | 真实结果 |
|---|---|
| 原 PDF 入口未回归 | `打开知识库原文` / `target="_blank"` / `rel="noopener noreferrer nofollow"` / `href=/api/kb/documents/55afc3.../source` |
| 第二入口渲染 | `定位到召回片段` 按钮存在且可点 |
| `locate_calls` | `[{documentId:"55afc3b8f01445429462fe78ed0d4c98", chunkId:"086d957a-...", chunkIndex:38}]` |
| 「切片检查」tab | `aria-selected="true"` |
| 文档下拉选中（修复前为 `""`） | `55afc3b8f01445429462fe78ed0d4c98`（65 个选项） |
| 切片节点渲染 | `57` |
| 高亮命中 | `1` 个，`data-chunk-index="38"`、`data-chunk-id="v1:38"` |
| pending 已消费 | `null` |
| `page_errors` | `[]` |
| console errors | 4 条 404，来自历史会话列表里已删除会话的 GET，与本 spec 无关 |

> 修复前同一场景为 `doc_select_value=""` / `chunk_nodes=0` / console `无法定位片段：定位片段时发生异常`。根因是 `frontend/app.js::jumpToKnowledgeBase()` 内两处引用了未定义变量 `documentId`，抛 `ReferenceError` 被 `.catch()` 吞掉；改为函数作用域内的 `key` 后，文档选择 → `loadInspection()` → `renderChunks()` → 消费 pending → `focusChunk` 的 `data-chunk-index` 回退匹配全部贯通。来源 `chunk_id` 是 `point_id()` UUID，检查器 `data-chunk-id` 是 `v1:38`，因此 `chunk_index` 回退键是必需的。

## 调用约束 / 已知限制

- `POST /api/conversations/messages` 的 `content` 必填且 ≤20000 字符；兼容拼写为 `question` / `message`；`model` 默认 `qwen3.8:27b`，`mode ∈ {normal, developer}`，`reasoning_effort ∈ {off, low, medium, high, xhigh}`。
- 该端点**直接返回 SSE 流**（`text/event-stream`），不是先返回实体再另开流；`message_id` / `assistant_message_id` 从首个 `meta` 帧取。
- `GET /api/messages/{message_id}/processing-steps` 用 **assistant** 的 `message_id`；消息不存在时 404，步骤为空但消息存在时返回 `{"steps":[]}`。
- 上面首次验证的问题未触发知识库检索，因此**没有 `rag_retrieval` 步骤**（只有 3 步）；这是按真实查询路由产生的，不是缺陷。`rag_retrieval` 的 `rag_hit` 记录需以含知识库证据的提问另行触发——该步骤已在下方「补录」章节以真实请求跑通，含 5 条 `chunk_index`。
- `detail_json` 是**字符串**，客户端需 `JSON.parse`；记录数受投影侧 ≤5 与脱敏侧列表截 32 / 字符串截 500 / 深度 3 / 总长 4000 约束；超限时整体降级为 `{"truncated":true}`。
- SSE `progress` 帧**不携带明细**，明细只在历史水合时读取；因此实时步骤卡在本次流式中暂不可点，刷新会话后可点开证据浮层（spec 明确的设计取舍）。
- Reranker 模型缺失 → 服务以 RRF 降级模式运行；不影响本 spec 的对话、证据投影与静态资源链路。
