# Reranker 精排：外部资产恢复与干净降级

`deploy/reranker/start.sh` 依赖**两项不入库的外部资产**：`data/models/`（`.gitignore:34`）与 `deploy/reranker/.runtime/`（`.gitignore:52`）均被忽略，换机/清理后需按本文件重建。

1. Qwen3-Reranker-0.6B Q8_0 GGUF（639,153,184 字节）
2. 支持 `--reranking --pooling rank` 与 `/v1/rerank` 的 `llama-server`

在拿到 `/api/kb/health` 的 `reranker_detail.available=true` 证据前，只能如实记录 RRF 降级（见 `deploy/VERIFICATION.md:73`），不得伪称精排已启用。任务 U 之后该字段重新代表「HTTP 与三文档排序质量探针均通过」（spec-014:72），见第 5 节。

## 1. 模型

官方源：`https://huggingface.co/ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF`；本环境 HuggingFace 不可达，改用可达的 ModelScope 镜像 `ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF`：

```bash
cd <repo-root>
mkdir -p data/models
curl -fL --no-progress-meter --connect-timeout 15 --max-time 300 \
  -o data/models/qwen3-reranker-0.6b-q8_0.gguf \
  'https://www.modelscope.cn/api/v1/models/ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF/repo?Revision=master&FilePath=qwen3-reranker-0.6b-q8_0.gguf'
stat -f%z data/models/qwen3-reranker-0.6b-q8_0.gguf       # 必须是 639153184
shasum -a 256 data/models/qwen3-reranker-0.6b-q8_0.gguf   # 必须是 22c9979ce4fbcdc5acdc310c6641c32797eff1aa980b8f7a2db8a8ea23429a48
```

字节数或 SHA256 任一不符：删除不完整文件，按第 4 节显式降级。

## 2. llama-server

`brew install llama.cpp` 在本机超时（卡在 `raw.githubusercontent.com` 拉取 formula），已按超时上限放弃；改用官方 release 预编译包（macOS **x86_64**，build 12230，含同目录 dylibs，无需 `DYLD_LIBRARY_PATH`）：

```bash
cd <repo-root>
mkdir -p deploy/reranker/.runtime
curl -fL --max-time 120 -o /tmp/llama-b12230-bin-macos-x64.tar.gz \
  'https://ghproxy.net/https://github.com/ggml-org/llama.cpp/releases/download/b12230/llama-b12230-bin-macos-x64.tar.gz'
tar -xzf /tmp/llama-b12230-bin-macos-x64.tar.gz -C deploy/reranker/.runtime
LLAMA_SERVER="$PWD/deploy/reranker/.runtime/llama-b12230/llama-server"
"$LLAMA_SERVER" --version                                  # 0.9.0-dev (build 12230) Darwin x86_64
"$LLAMA_SERVER" --help | grep -E -- '--reranking|--pooling|--no-webui'
```

官方直链 `https://github.com/ggml-org/llama.cpp/releases/download/b12230/llama-b12230-bin-macos-x64.tar.gz` 会 302 到 `release-assets.githubusercontent.com`（本环境不可达），故用镜像；网络允许时可直接用官方直链。若 `brew install llama.cpp` 成功，把 `RERANKER_SERVER_BIN` 指向 `$(brew --prefix)/bin/llama-server` 即可。

## 3. 启动（必须显式环境变量）

`.env` **不会**被 shell 读取，必须把二进制路径作为环境变量传入；仅模型存在、PATH 里没有 `llama-server` 时无法启用精排：

```bash
cd <repo-root>
RERANKER_SERVER_BIN="$PWD/deploy/reranker/.runtime/llama-b12230/llama-server" ./deploy/start.sh -d
```

验收（全部通过才算精排已启用）：

```bash
curl -sS -w '\nHTTP=%{http_code}\n' http://127.0.0.1:8000/api/health   # 200
./deploy/reranker/probe.sh                        # reranker probe passed: health ready; ranking valid
curl -sS http://127.0.0.1:8000/api/kb/health      # reranker=true, available=true, reason=null
.venv/bin/pytest -q tests/system/test_reranker_config.py tests/kb/test_kb_reranker.py tests/kb/test_kb_services.py tests/kb/test_kb_routes.py tests/kb/test_kb_observability.py
```

## 4. 干净降级（RRF）

缺任一资产时不要硬撑：`deploy/start.sh` 在 reranker 子脚本失败（模型/二进制缺失、启动时 `probe.sh` 质量探针失败）或 runtime URL 无效时，会 `export RERANKER_ENABLED=false` 后继续启动 FastAPI。**不带 `RERANKER_SERVER_BIN` 启动**（且 PATH 里也没有 `llama-server`）是最常见的缺二进制场景：子脚本因找不到可执行文件退出，由此干净降级为 RRF，属期望行为、不是故障。此时 `/api/kb/health` 明确给出 `reranker_detail.enabled=false, available=false, reason="disabled"`；后端 `reranker_health()` 在 `enabled=false` 时直接返回 `disabled`，零网络请求、不做心跳探测也不写缓存（该短路在任务 U 恢复质量探针后仍保持）。用户显式传 `RERANKER_ENABLED=false` 的既有行为不变（跳过启动与质量探针）。

```bash
RERANKER_ENABLED=false ./deploy/start.sh -d        # 主动显式降级
./deploy/stop.sh                                   # 停止 FastAPI 与专用 Reranker
curl -sS http://127.0.0.1:8000/api/kb/health       # 核对 reason=disabled
```

## 5. 已知边界（本机 CPU）

> **2026-11-10 任务 U 修订**：任务 N 曾把心跳降为「只判 liveness、不跑质量推理」，但 `spec-014:72/102/131/149` 的 `available` 定义、质量探针、30s 熔断与 A7 验收项从未修订，plan 追加节的「按新语义理解」不构成契约变更。任务 U 已恢复实现以符合 spec 原文，并保留任务 N 对「慢响应假降级」根因的正确定位。本节为当前实现。

- **`available` = 质量已验证**：`_health_probe()` 先发轻量 `GET <base_url>/health`（liveness），再发一次固定三文档 `POST /v1/rerank` 质量探针（与 `deploy/reranker/probe.sh` 同一组 query/documents）。只有 HTTP 2xx、响应可解析、且最相关文档排第一（分数不完全相同）才返回 `available=true`。模型在运行中损坏（`/health` 正常但排序异常）时 health 会如实报 `quality_probe_failed`，不再与 `kb.rerank` 事件的 `degraded_reason` 互相矛盾。
- **不被慢推理拖垮**：`reranker_health()` 用 `_RERANKER_HEALTH_TTL=30.0` 的 monotonic + single-flight 缓存，30 秒内并发/重复 health 请求只触发一次探针（spec-014:134），等价于「liveness 心跳 + 周期性质量验证结果缓存」。
- **两档超时**：liveness `GET /health` 用 `_RERANKER_HEALTH_CONNECT_TIMEOUT_CAP=2.0` / `_RERANKER_HEALTH_READ_TIMEOUT_CAP=6.0`；质量 `POST /v1/rerank` 用 `_RERANKER_HEALTH_QUALITY_READ_TIMEOUT_CAP=30.0`（覆盖实测单请求 1.5–2.3s 与 5 并发最长 18.3s，仍有硬上限）。不再把 connect/read 统一钳到 2.0s，故慢但成功的推理不会假降级。
- **分层缓存**：成功与「不可达 / 质量探针失败」写 30s 缓存（spec-014:131）；`timeout` 写 `_RERANKER_HEALTH_TRANSIENT_TTL=4.0` 的**短缓存** —— 零缓存会让持续故障时每次 health 重跑推理打满后端，30s 又是旧假降级根因，4s 兼顾两者。
- **检索侧熔断恢复**：`rerank_hits` 对 timeout / ConnectTimeout / `invalid_*` / `unexpected` / 4xx / 5xx 等所有失败写 ≥30s 负缓存，避免 60s hang 时每次 KB 问答都阻塞、打满 FastAPI 线程池；`httpx.Timeout` 另加 spec-014:131 的 60s 硬上限（`config.py` 默认 `60.0` 不变）。`ConnectTimeout` 与 `ReadError` 在 health、检索两处统一归 `connection`。
- `/api/kb/health` 响应结构与 `reason` 取值集合不变：`null` / `disabled` / `connection` / `timeout` / `quality_probe_failed` / `model_not_prepared`。`quality_probe_failed` 现名实相符（协议异常或质量探针未通过）。

启动时 `deploy/reranker/start.sh` 仍会调 `deploy/reranker/probe.sh` 做一次三文档质量校验（第 3 节验收输出 `reranker probe passed: health ready; ranking valid`），失败即让 `deploy/start.sh` 干净降级；运行期质量由 health 周期探针持续验证，二者互补。

排查顺序（本机终端依次执行；资产恢复见第 1–2 节、启动环境变量见第 3 节）：

1. `RERANKER_SERVER_BIN="$PWD/deploy/reranker/.runtime/llama-b12230/llama-server" ./deploy/start.sh -d`；不带 `RERANKER_SERVER_BIN` 即干净降级为 RRF、`reason="disabled"`（见第 4 节），属期望行为。
2. `./deploy/reranker/probe.sh` → 看到 `reranker probe passed: health ready; ranking valid`。
3. 若曾出现 `connection` / `model_not_prepared` / `quality_probe_failed`，最多**等待 30s** 让负缓存过期；若为 `timeout`，最多等 4s 短缓存过期后自动重试（期间并发轮询复用同一结果，不重复跑推理）。
4. 单次 `curl -sS http://127.0.0.1:8000/api/kb/health` → 只有拿到 `reranker_detail.available=true` 且 `reason=null` 才能记录精排已启用，否则如实记录 RRF 降级（见 `deploy/VERIFICATION.md:73`）。
