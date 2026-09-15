# 首屏数据就绪：耗时基线

度量日期：2026-09-15
目标：回答「首屏这些数据要多久准备好、为什么这么久、能不能优化」，并作为优化前后的对比基线。

## 一句话结论

**慢的不是数据库，也不是占比数据，而是两处对外部依赖（Ollama / 向量化）的同步阻塞调用。**

- `/api/kb/health` 实测 **155,274 ms（约 2.6 分钟）** —— 单点最大瓶颈；
- `/api/models`、`/api/health` 各 **约 5,050 ms** —— `get_available_models()` 无缓存，每次请求都打满 `timeout=5`；
- 而真正被用户抱怨的**上下文占比数据本身只要 24 ms**，`/api/projects` 9 ms、`/api/kb/papers` 3 ms —— 数据库与占比链路**完全不是瓶颈**。

## 度量方法

- 服务端：已在运行的 uvicorn（`uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`，单进程、无 `--reload`）。
- 「冷」口径：新起 Python 进程，测模块导入与首次构建成本（jieba 前缀词典、首次向量化）。
- 「热」口径：直接打已在运行的服务端 HTTP 端点。
- 客户端用 `httpx.Client(trust_env=False)`，**绕过本机 HTTP 代理**（见下方「度量陷阱」）。
- 度量脚本一次性执行，不入库。

## 度量陷阱（重要，避免后人重复踩坑）

本机存在 HTTP 代理配置。用 `httpx` 且未设 `trust_env=False` 时，打 `127.0.0.1:8000` 的请求会被代理拦截，表现为：

```
status 503, body 空, headers: {'connection': 'close', 'proxy-connection': 'close', 'content-length': '0'}
```

**这不是服务端故障**。同一时刻用 `/usr/bin/curl` 直连返回 200。
判断依据：响应头出现 `proxy-connection`，且 `content-length: 0`、body 为空。
度量必须显式 `trust_env=False`，否则会得出「服务全面 503」的错误结论。

## 基线数据

### A. 进程内冷启动成本（新进程）

| 项 | 耗时 | 备注 |
|---|---|---|
| `import backend.app.platform.ollama` | 1,823 ms | 一次性，服务启动时已付 |
| `import ...embed` | 1,120 ms | 一次性 |
| `tokenize()` 首次（jieba 前缀词典） | 840 ms | 词典来自缓存文件，第二次 0 ms |
| `get_available_models()` 第 1 次 | 5,040 ms | `ConnectTimeout` |
| `get_available_models()` 第 2 次 | 5,045 ms | **与首次相同 → 确认无任何缓存** |
| `embed_texts(["测试"])` 第 1 次 | 150,086 ms | `EmbeddingError` |
| `embed_texts(["测试"])` 第 2 次 | 150,084 ms | **与首次相同 → 确认无缓存** |

### B. 服务端端点（热态）

| 端点 | 耗时 | 备注 |
|---|---|---|
| `GET /api/kb/health` | **155,274 ms** | 🔴 最大瓶颈 |
| `GET /api/models?probe=1` | 7,261 ms | 🟠 5s 模型列表 + 线上探测 |
| `GET /api/models` | 5,059 ms | 🟠 |
| `GET /api/health` | 5,045 ms | 🟠 两次调用均 ~5,050 ms → 无缓存 |
| `GET /api/conversations/{id}/context-usage` | 24 ms | 🟢 **占比数据极快** |
| `GET /api/conversations/{id}/messages` | 14 ms | 🟢 |
| `GET /api/conversations` | 5 ms | 🟢 |
| `GET /api/projects?limit=100` | 9 ms | 🟢 |
| `GET /api/kb/papers` | 3 ms | 🟢 |

并发 5 次 `/api/health`：墙钟 5,141 ms，各请求均为 ~5,140 ms，全部 200。
→ 并发下**不叠加**（线程池并行），但**每个请求都要付满 5s**，即同一页面 N 次调用 = N × 5s 的等待体验。

## 瓶颈归因

### 1. `/api/kb/health` 155s：健康检查做了真实向量化

`backend/app/api/routes_kb.py:154-158`：

```python
try:
    embed_texts(["健康检查"])
    status["embedding"] = True
except Exception:
    status["embedding"] = False
```

`embed_texts` → `_embed_batch` → `httpx.post(..., timeout=180)`，且网络类错误**重试一次**。
Ollama 不可达时，这一句就是 155s（约两次尝试）。一个「健康检查」端点承担了完整向量化往返的代价。

### 2. `get_available_models()` 5s × N：无缓存 + 外部依赖

`backend/app/platform/ollama.py:192-196`：

```python
response = httpx.get(f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags", timeout=5, trust_env=False)
```

- `OLLAMA_BASE_URL = http://192.168.31.180:11434` —— **局域网另一台机器**，度量期间不可达。
- 无任何缓存：连续两次调用都是 5,050 ms。
- 被 health / chat / conversations / kb / models / article 等多路由频繁调用，一次页面加载可触发多次。

### 3. 上下文占比「组件不出现」的真实原因：前端串行 await + 隐藏占位

占比数据本身 24 ms，不是后端慢。问题在前端：

- `frontend/app.js:2653-2656`：`loadProjects().then(...)` 之后才进入 `openConversation`；
- `frontend/app.js:1984-1990`：串行 `await loadProjectConversations` → `await loadConversationMessages` → `await loadContextUsage()`，**占比排在倒数第二步**；
- `frontend/app.js:777-778`：在 `loadContextUsage()` 返回前，组件为 `is-idle` → `visibility: hidden`，用户感知为「没有这个组件」，数据返回后才「凭空出现」。

### 4. 模型数量「一开始是 0」

`#model-count` 的赋值发生在模型拉取之后，而 `/api/models` 需 5s、`/api/models?probe=1` 需 7.3s。
在拿到真值前，DOM 里是初始的 `0` —— 这是「错误中间态」，用户会误读为「有 0 个模型」。

### 5. 次要：jieba 首次分词 840 ms

`backend/app/knowledge_base/infrastructure/embed.py:42-48` 延迟导入，首次 `tokenize()` 才构建前缀词典。量级仅 0.84s，属次要项，但仍值得预热。

## 优化方向（按收益排序）

| 优先级 | 措施 | 预期收益 |
|---|---|---|
| P0 | `/api/kb/health` 的 embedding 探测改用短超时（不再 180s × 2），并复用预热结果 | 155s → 秒级 |
| P0 | `get_available_models()` 加 30s TTL 缓存 + 失败短 TTL 负缓存 + 单飞 | 5s × N → 每 30s 至多一次 |
| P1 | lifespan 后台预热（jieba / `/api/tags` / embedding / Qdrant） | 冷启动成本移出请求路径 |
| P1 | 前端各区块就地加载态 + 10s 兜底转圈 | 消除「空白/0」误读 |
| P2 | `openConversation` 内三个独立加载改 `Promise.all` 并行 | 占比不再排队到最后 |
| P2 | 模型数量未就绪时显示转圈而非 `0` | 消除错误中间态 |

## 优化后复测

在同机另起一个独立实例做 A/B：**8000 = 改动前旧实例，8010 = 改动后新实例**（预热 + 缓存 + kb/health 短超时）。
同一时刻对比，可排除环境波动的影响。

> ⚠️ 口径说明：复测时 **Ollama 已恢复可达**（此前不可达属本次波动），因此**不能**直接拿这里的数字与不可达期的 155s 相比。
> 下表是与**同时刻旧实例**的对照，才是干净的改善幅度。

| 端点 | 旧 8000（改动前） | 新 8010（改动后） | 变化 |
|---|---|---|---|
| `GET /api/kb/health` | 5,744 ms | **1,222 ms** | **快 4.7 倍** |
| `GET /api/health` | 89 ms | 45 ms | −49% |
| `GET /api/projects?limit=100` | 160 ms | 94 ms | −41% |
| `GET /api/models` | 223 ms | 169 ms | −24% |
| `GET /api/kb/papers` | 39 ms | 39 ms | 持平（本来就快） |

连续两次 `/api/health`：

- 旧实例 96 ms → 87 ms（**每次仍回源**）
- 新实例 36 ms → 35 ms

### 预热实测（新实例启动日志 + `/api/ready`）

```
{"ready":true,"warmup":{
  "jieba":       {"status":"ready","elapsed_ms":830.7,"error":null},
  "ollama_tags": {"status":"ready","elapsed_ms":148.7,"error":null},
  "embedding":   {"status":"ready","elapsed_ms":126.2,"error":null},
  "qdrant":      {"status":"failed","elapsed_ms":1319.6,"error":null}}}
```

`qdrant` 失败但 `/api/ready` 仍返回 `ready:true`、服务正常提供 —— **fail-open 符合预期**。

### 缓存的真实收益在哪里

依赖健康时差异不明显（本来就是百毫秒级）；**依赖不可达/变慢时差距才凸显**：

- 不可达期实测 `/api/health` = 5,050 ms，且**连续两次都是 5,050 ms**（每次都回源）；
- 加负缓存后，同一故障在 TTL 内只需付一次超时代价，后续请求立即失败返回，不再排队等 5s。

这正对应本报告开头记录的现场：当时一连串请求各自打满 5s，累积起来就是用户感知的「要等很久」。

## 已完成改动

**后端**

- `backend/app/platform/ollama.py`：`get_available_models()` 加 30s 成功 TTL + 5s 网络失败负缓存 + 单飞（回源全程持锁）；新增 `refresh_available_models()` 供预热强制回源。
- `backend/app/platform/config.py`：`OLLAMA_TAGS_CACHE_TTL_SECONDS=30`、`OLLAMA_TAGS_FAILURE_TTL_SECONDS=5`（env 可配）。
- `backend/app/platform/warmup.py`（新增）：jieba / `/api/tags` 轻量项先行，embedding / Qdrant 后台；每项 `unknown/loading/ready/failed` + 耗时，`Lock` 保护，全 fail-open。
- `backend/app/api/routes_kb.py`：健康检查的 embedding 探测改为「预热注册表短路 + 3s 短超时兜底」，不再承担 155s 完整向量化往返。
- `backend/app/api/routes_system.py`：新增 `GET /api/ready`，恒 200。
- `backend/app/main.py`：`lifespan` 在既有索引代次收尾后**非阻塞**启动预热。

**前端**

- `frontend/app.js`：通用 `withAsyncSlot`（`aria-busy` + spinner + 10s `setTimeout` 追加「仍在加载…」+ 失败重试），禁用 `innerHTML` 与 `setInterval`；
  占比圆圈新增「加载中」**第三态**（与「无会话 `is-idle`」区分，仍为 `visibility` 占位，组件从头可见）；
  模型数量未就绪显示 spinner 而非 `0`；知识库列表骨架行 + health 前缀转圈；
  `openConversation` 内三路加载改 `Promise.all` 并行，占比不再排队到最后。
- `frontend/index.html`：`?v=48` → `?v=49`，4 处契约测试断言同步。

**回归**：67 passed（含新增 `tests/test_startup_warmup.py` 6 项）。
