# Spec031 技术评审：Task02 基准与资源调度门

## 评审元数据

- 评审对象：Spec031、`plans/031/task-02-ollama-topology-benchmark.md`、Task02 benchmark artifacts
- 评审角色：开发主管 / SDD Gate Reviewer
- 评审模型：Luna high
- 评审范围：harness/raw/report、Task02 合同测试、既有 `ResourceProbe`、`_GlobalWorkerScheduler`、Spec027/028 runtime contract
- 评审时间：2026-09-17（Asia/Shanghai）

## 结论

**有条件通过；Task03 单实例放行，多实例 NO-GO。**

Task02 没有新增业务模型客户端或调度实现，且真实历史数据与既有 ResourceProbe/调度合同方向一致。1–4 Worker 口径能从 raw 与 harness 复核：每档先 `keep_alive=0` 冷请求，再预热并执行 2 个热并发波次；吞吐按各波次最长墙钟时间聚合；`/api/ps` 记录驻留模型 `size_vram`。

技术门仍有两项 P1 和两项 P2，必须在 Task06 前补齐或明确降级，不能在本评审中声称已修复：

- P1：`Sample.ok` 只由 HTTP `<400` 与无异常决定（harness:75–110），未验证响应是否为固定 `{"ok":true}`。
- P1：raw 只保存 benchmark blocks，未保存 ResourceProbe available-memory/snapshot、listener/备用端口探针、版本和平台 provenance。
- P2：CLI 参数允许越过 Task02 的 1–4 Worker 与正 warm-wave 边界。
- P2：合同测试未核对 samples 与 summary 的数量/数值一致性，也未要求质量和环境 provenance。

这些问题不阻止 Task03 继续实现单实例 shadow 观测，但若 Task03/后续 policy 激活直接依赖 benchmark 质量或多实例证据，必须先关闭相应 P1。

## 技术核对矩阵

| 技术点 | 判定 | 依据 |
|---|---|---|
| 请求合同 | 通过 | harness 使用既有 `/api/chat`，固定 model/prompt、`think=false`、`format=json`、temperature 0、num_predict 8、trust_env=False。 |
| 冷/热分离 | 通过 | `keep_alive=0` 形成冷加载边界；预热后以 `keep_alive=30s` 运行 warm waves；cleanup 不计入 measured。 |
| 1–4 Worker 覆盖 | 通过（边界需加固） | raw `worker_counts=[1,2,3,4]`，请求数与并发波次一致；CLI 尚未强制拒绝越界参数。 |
| TTFT/服务时延 | 通过 | TTFT 取客户端首次 content/thinking token；服务端 duration/load/eval 从 Ollama 纳秒字段转换为毫秒。响应内容质量仍未验证。 |
| 吞吐 | 通过 | `_summary` 以每个 `(phase,wave)` 的最长 wall time 作为并发波次耗时，再用成功 completion tokens 聚合；报告使用 warm summary。 |
| 峰值内存 | 部分通过 | `/api/ps` `size_vram` 快照已纳入 raw；但系统可用内存和 ResourceProbe 计算结果只在 report 文字中，未进入 raw provenance。 |
| ResourceProbe 复用 | 通过 | `backend/app/platform/ollama.py` 统一读取 `/api/tags`、`/api/ps` 和系统可用内存，20% 余量后裁决 cap；失败降 `(1,"RESOURCE_PROBE_FAILED")`。Task02 未新增第二套 probe。 |
| 全局调度合同 | 通过 | Spec027/028 定向合同覆盖公平、不超卖、释放和运行时状态；Task02 未改 `_GlobalWorkerScheduler`。 |
| 多实例门 | 通过（NO-GO） | 未启动第二实例；无第二端口负载、内存、失败率或 LAN 入口证据，不能证明净收益，因此不放行。 |

## Task03 技术边界

- 使用现有单实例 `ResourceProbe.max_safe_workers()` 结果；当前历史实测 cap=1，探针失败保留 `RESOURCE_PROBE_FAILED`。
- 只实现决策/结果记录和 shadow policy，不实现多端口实例池，不修改 Ollama listener 或局域网入口。
- 不能把 benchmark 的 HTTP 成功率当作质量门；Task03 仅可消费已声明为环境/性能观察的数据。
- policy 激活继续需要 Spec031 的最小样本、质量门和可回滚语义；多实例若未来重评，必须复用同一 harness 并增加完整环境 provenance。

## 定向验证记录

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest --noconftest -q tests/test_spec031_task02_benchmark_contract.py tests/test_spec027_runtime_contract.py tests/test_spec028_runtime_contract.py` | 0 | 46 passed；未运行全量 pytest |
| `.venv/bin/python -m py_compile docs/sdd/plans/031/artifacts/task-02/ollama-topology-benchmark.py tests/test_spec031_task02_benchmark_contract.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |
| raw 离线一致性核对 | 0 | 四档请求数、warm summary 与 report 表格一致 |

## P1/P2 关闭要求（Task06 前）

| 编号 | 要求 | 当前状态 |
|---|---|---|
| P1-1 | 解析并校验固定 JSON 输出，错误答案不得计入 successes/throughput | 未修复；Task06 前补齐 |
| P1-2 | raw 保存 ResourceProbe snapshot、available memory、listener/备用端口探针、Ollama/平台 provenance | 未修复；Task06 前补齐或明确人工证据限制 |
| P2-1 | CLI 拒绝 workers 越界/重复和 warm-waves 非正值 | 未修复；Task06 前补齐 |
| P2-2 | 合同测试核对 samples↔summary、HTTP status、质量字段和 provenance | 未修复；Task06 前补齐 |

## 评审边界

本技术评审只修改本评审文档；未修改 `backend/**`、harness、raw、既有 ResourceProbe/调度实现或测试；未启动/配置第二实例，未运行全量 pytest，未执行部署或 push/merge。
