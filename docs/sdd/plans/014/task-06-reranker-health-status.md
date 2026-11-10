# 任务 06 — 接入健康状态与前端展示

> 关联：[spec-014](../../specs/014-kb-reranker.md) ｜ 索引：[README](./README.md)
> 依赖：任务 03、04；当前状态：`完成`

## 一句话目标

让健康接口和现有知识库状态栏准确显示 Reranker 的启用、可用及降级原因，同时保持旧客户端兼容。

## 接口目标

`GET /api/kb/health` 保留：

```json
{"reranker": true}
```

并新增：

```json
{
  "reranker_detail": {
    "enabled": true,
    "available": true,
    "backend": "llama.cpp",
    "model": "ggml-org/Qwen3-reranker-0.6B-Q8_0-GGUF:Q8_0",
    "reason": null
  }
}
```

旧 `reranker` 的值等于 `enabled && available`。

## 实施步骤

1. 将 `reranker_available()` 从“模型名非空”改为真实服务/质量状态。
2. 健康探针设置短超时并缓存结果，避免页面轮询反复运行模型推理；缓存 TTL 固定为 30 秒，使用单调时钟和并发保护。
3. 区分 disabled、binary/model 未准备、connection、timeout、quality_probe_failed 与 available。
4. 扩展 health 响应但不删除或改名现有字段。
5. 前端沿用当前状态文本，增加可解释的降级原因；不得加入设置面板。
6. 更新路由和前端测试；静态资源查询版本随 JS 改动递增。

## 涉及文件与子代理拆分

- 分派 A（`junior-dev`）：健康状态服务/客户端模块与路由，最多两个文件。
- 分派 B（`junior-dev`）：`frontend/app.js` 与必要的 `frontend/index.html` 缓存版本更新。
- 测试由 `tester` 在 Task 07 汇总执行；实现期先完成针对性测试。

## 边界与明确不做

- 服务不可达时 health 本身仍返回 200，不拖慢超过探针超时。
- disabled 不应报告 error，应显示“未启用”。
- reason 只包含安全的短消息，不包含命令行、正文或异常堆栈。
- 不新增独立前端页面、模型下载按钮或启动按钮。
- 不让 health 请求负责启动服务。

## 验收标准

- 旧测试仍能读取布尔 `reranker`。
- 四种状态至少覆盖：禁用、不可达、质量失败、可用。
- 30 秒缓存内重复 health 请求不重复执行质量推理。
- 30 秒内并发 health 请求只执行一次探针，其他请求复用同一结果。
- 前端在缺少 `reranker_detail` 时仍兼容旧响应。
- JS 语法检查与路由测试通过。

## 风险、回滚与产出

- 风险：探针增加 health 延迟；通过短超时和缓存限制。
- 回滚：移除 detail 展示并保留原布尔字段，不影响检索。
- 产出：health 扩展、前端状态、测试和执行记录。
- 执行结果：
  - 健康探针实现 HTTP ready + 三文档质量验证，并对 URL、JSON、index、score 做严格校验。
  - 使用 monotonic 30 秒 TTL 与 single-flight 并发缓存；禁用时零网络请求，异常仅返回安全原因。
  - `/api/kb/health` 保留旧 `reranker` 布尔字段并增加 `reranker_detail`；前端状态栏兼容旧响应并显示降级原因，`app.js` 版本更新为 v14。
  - 统一启动后实测 `/api/kb/health` 返回 `reranker=true` 、`available=true`、`backend=llama.cpp`、`reason=null`；停服降级时返回 `reason=connection`。
  - 相关回归 `115 passed`（含 29 个 subtests），JavaScript `node --check` 、Python 编译与 diff 校验通过。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-02 | 架构师(自身) | 创建任务计划，状态为待执行 |
| 2026-09-02 | 架构师(自身) | Task 05 配置与检索集成验证通过，分派 Task 06 健康与前端小任务 |
| 2026-09-02 | Luna 高推理协作 Agent | 完成健康探针、路由扩展与前端降级状态展示 |
| 2026-09-02 | 架构师(自身) | 相关回归与静态检查通过，任务转完成 |

## 2026-11-10 任务 U 修订（恢复 spec-014 契约）

> 本节为**追加记录**，说明任务 U 落地后的实际语义。上方 1–85 行「实施步骤」「验收标准」「执行结果」「变更日志」均为当时的历史决策原文，**保留不改**。
>
> **历史沿革**：任务 N 曾把心跳降为「只判 liveness、不跑质量推理」，并以「按新语义理解，不改写原文」自述豁免。2026-11-10 评审判定该自述**不构成契约变更**：`docs/sdd/specs/014-kb-reranker.md:72/102/131/149` 的字段定义、质量探针、30s 熔断与 A7 验收项从未修订，`:124` 明文规定「约束漏做即不得进入下一门禁」。任务 U 因此**不改 spec**，恢复实现以符合原文，并同步改写本节追加记录（历史原文 1–85 行不删）。

**任务 N 定位正确的部分（保留）**：旧实现把 health probe 的 connect/read timeout 统一钳到 ≤2.0s、每次心跳跑三文档完整推理、且 `timeout` 写 30s 负缓存；本机 CPU 约 2.23s 的正常慢响应会被误判 `timeout` 并全局降级 30s。`GET /health` + 有上限的宽松超时 + 30s 正缓存 + single-flight + `reason` 集合与响应结构不变，方向正确；问题只在于把同一策略过度套用到 `rerank_hits`（移除熔断）且未修订 spec。

**当前实现**（`backend/app/knowledge_base/infrastructure/retrieve.py` / `reranker.py`）：

| 项 | 当前语义 |
|---|---|
| `available` | **恢复 spec-014:72**：HTTP liveness 与三文档排序质量探针同时通过才为 `true`。`_health_probe()` 先 `GET /health`，再 `POST /v1/rerank` 固定三文档（:102），用 `_probe_scores()` 校验最相关文档排第一；失败报 `quality_probe_failed`（A7 可区分） |
| 质量探针频率 | `_RERANKER_HEALTH_TTL=30.0` monotonic + single-flight：30 秒内并发/重复 health 只触发一次探针（:134），即「liveness 心跳 + 周期性质量验证结果缓存」，不被慢推理拖垮 |
| 超时上限 | 两档：liveness `connect=2.0/read=6.0`；质量推理 `read=30.0`（覆盖实测单请求 1.5–2.3s 与 5 并发 18.3s，仍有硬上限）。不再统一钳到 2.0s → 慢但成功不假降级 |
| 30s 缓存 | 成功与「不可达 / 质量探针失败」写 30s（:131）；`timeout` 写 `_RERANKER_HEALTH_TRANSIENT_TTL=4.0` **短缓存**：零缓存会让持续故障时每次 health 重跑推理打满后端，30s 又是旧假降级根因 |
| 检索侧熔断 | `rerank_hits` 回退任务 N 的 `cacheable` 排除：timeout / ConnectTimeout / `invalid_*` / `unexpected` / 4xx / 5xx 全部 ≥30s 负缓存（:131）；`httpx.Timeout` 加 60s 硬上限（`config.py` 默认 60.0 冻结值不变） |
| 异常归类 | `ConnectTimeout` 单独归 `connection`（30s 熔断，修复 HIGH-1）；`ReadError`/`RemoteProtocolError` 在 health 与检索两处统一归 `connection` |

**验收标准（第 61 行）**：1–85 行原文「30 秒缓存内重复 health 请求不重复执行质量推理」**恢复字面成立** —— 正缓存 30s 复用可用结果，期间不重复跑三文档推理；`spec-014` 主文档一律未改。

**契约不变**：`/api/kb/health` 响应结构（旧 `reranker` 布尔 + `reranker_detail`）与 `reason` 取值集合不变；`enabled=false` 时零网络请求、直接返回 `reason="disabled"`。不带 `RERANKER_SERVER_BIN` 启动时，`deploy/start.sh` 在子脚本失败 / runtime URL 无效时 `export RERANKER_ENABLED=false` 干净降级为 RRF，属期望行为（详见 `deploy/reranker/README.md` 第 4 节）；两处 `|| true` 已改为显式告警（LOW-7）。

**运维验收旅程**（本机终端依次执行；主会话统一重启后执行）：

1. `RERANKER_SERVER_BIN="$PWD/deploy/reranker/.runtime/llama-b12230/llama-server" ./deploy/start.sh -d` → 终端看到 `使用 Reranker：http://127.0.0.1:<port>`。
2. 启动时 `probe.sh` 自动校验 → 看到 `reranker probe passed: health ready; ranking valid`；失败则终端出现降级提示。
3. 单次 `curl -sS http://127.0.0.1:8000/api/kb/health` → `reranker_detail.available=true, reason=null` 才算精排已启用（此时已经过运行期三文档质量验证）；`quality_probe_failed` 表示质量探针未通过，须排查模型；`connection` / `model_not_prepared` 恢复服务后最多等 30s 负缓存过期；`timeout` 最多等 4s 短缓存过期后自动重试。
4. 5 并发 KB 问答 + 40 次 health 轮询：`available` 应持续为 `true`（慢但成功不假降级），且 30s 内不重复跑质量推理；命令见任务 U 报告「主会话收口实机验证」。

**核对证据**：`retrieve.py` 常量、`_health_probe()` / `_probe_scores()` / `reranker_health()`；`reranker.py` 的 `MAX_READ_TIMEOUT` 与 `rerank_hits()` 熔断；`tests/kb/test_kb_reranker_health_probe.py`（27 例，RED→GREEN）；`tests/system/test_reranker_config.py:35`（60.0 冻结值）；`tests/system/test_deploy_start_reranker_degradation.py`（6 例，含清理告警）；`deploy/reranker/README.md` 第 5 节。

## 2026-11-11 任务 W 追加（残留 5 项工单收口）

> 本节为**追加记录**，与本文件 1–85 行历史原文、以及上方「2026-11-10 任务 U 修订」追加节逐字保留不改。任务 W 只收口 `docs/sdd/reviews/20261110-lingering-fixes-backend-recheck.md` 第三节列出的 5 项残留问题；`docs/sdd/specs/014-kb-reranker.md` 仍为零改动，`:131` 的「失败后至少缓存负状态 30 秒」与 `:134` 的 health 并发缓存要求不变。

| 项 | 任务 W 落地语义 |
|---|---|
| M-1 首个 60s 并发窗口 | `rerank_hits` 增加按 `(endpoint, model)` 的 single-flight（Condition + Event，复用 health 侧同款并发保护思路）：leader 发真实请求，等待者最多等 3.0s（依据正常单请求 1.5–2.3s）即复用 leader 失败 reason / 快速失败；leader 成功时等待者继续发自己的请求。5 并发 hang 只发生 1 次网络调用；60s/2s 硬上限、`config.py:91` 冻结默认值、≥30s 负缓存全部不变 |
| M-2 无界等待 / 非总时限 | health 等待者加真实时钟有界 deadline（50.0s = 总时限 45.0s + 5s 通知余量），超时返回 `available=false, reason=timeout` 不重复探测；探针改流式 `iter_bytes()` 并加 45.0s **总时限**（2×connect 2s + liveness 6s + quality 30s = 40s 理论最长合法耗时 + 5s 余量），慢速吐字节后端收敛为 `timeout`。6s/30s 两档 read cap 不变，正常 1.5–2.3s 推理不误杀 |
| L-1 兜底异常掩盖故障 | 两处兜底 `except Exception` 改用 `unexpected`（与 `reranker.py` 的 `RerankReason` 集合一致）并加 `logger.exception`；原始异常只进服务端日志，`/api/kb/health` 响应结构与 reason 可诊断性不变，`unexpected` 仍走 30s 负缓存 |
| L-2 TTL 下限未锁 | 检索侧补 `clock.advance(29)` 仍命中 / `advance(31)` 重新发请求的门禁用例（负向变异 `MIN_NEGATIVE_TTL=1.0` 会使其 FAIL），既有 10 例熔断断言一条未放宽 |
| L-3 质量集跨语言重复 | 抽为唯一数据源 `deploy/reranker/quality-probe.json`；Python 用 stdlib `json` 从 `__file__` 定位，`probe.sh` 复用既有 `python_bin` 检测读取（无 jq / 无新运行时依赖，缺文件或缺 Python 时脚本报错退出并由 `deploy/start.sh` 干净降级为 RRF）。三文档内容与 `scores[1]` 严格居首判定逐字不变；新增一致性测试解析两侧实际 POST 体并阻止任一侧重新硬编码 |

**测试与契约门禁**：`tests/kb/test_kb_reranker_health_probe.py` 由 27 例增至 34 例，新增 `tests/kb/test_kb_reranker_quality_probe_consistency.py` 3 例；`tests/system/test_reranker_config.py:35` 的 `RERANKER_READ_TIMEOUT_SECONDS=60.0` 冻结值未动；`/api/kb/health` 结构（旧 `reranker` 布尔 + `reranker_detail`）与 `enabled=false` 零探测短路不变。

**主会话收口实机验证**（本次未重启服务，仍按上方「运维验收旅程」执行）：`deploy/start.sh` 重启后确认 `probe.sh` 输出 `reranker probe passed: health ready; ranking valid`、`curl -sS http://127.0.0.1:8000/api/kb/health` 为 `available=true, reason=null`，再跑 5 并发 KB 问答 + health 轮询确认无假降级。
