# Spec031 Task02 基准门审查报告

## 固定字段

- 结果状态：**有条件通过（单实例路径）**
- spec：031 — 动态模型路由与资源调度优化
- task：Task02 — 单实例/多实例与 Worker 基准门
- 审查范围：Spec031、Task02 文档、benchmark report/raw/harness、Task02 合同测试、Spec027/028 runtime contract、既有 `ResourceProbe`/`_GlobalWorkerScheduler`
- 审查文件：`docs/sdd/plans/031/artifacts/task-02/review-report.md`
- 模型：Luna high
- 审查时间：2026-09-17 14:25–14:32 CST；总耗时约 7 分钟

## 结论

1. 1–4 Worker 的指标口径基本一致：固定模型/输入/请求选项，冷样本与热样本分离，热吞吐按并发波次最长墙钟时间聚合，TTFT 与 Ollama 原生纳秒时延均有明确计算路径。raw 中四档请求数分别为冷 `1/2/3/4`、热 `2/4/6/8`，与 harness 的默认参数一致；报告表格中的吞吐、TTFT、失败率可由 raw 的 warm summary 复核。
2. 单实例实测数据在当前交接物中是自洽的，且报告保守地把 2–4 Worker 仅作为观察结果，没有把失败率 0% 解释为生产安全放行。既有 `ResourceProbe` 在 20% 余量规则下将本机 cap 限为 1；探针失败返回 `RESOURCE_PROBE_FAILED` 的语义与 Spec027/028 合同一致。
3. 多实例结论应保持 **NO-GO**：交接物没有启动第二实例，也没有第二端口的吞吐/内存/局域网入口证据；以“无净收益证据且资源余量不足”为 NO-GO 是符合 Spec031 的安全门禁，而不是把单实例数据外推为 GO。
4. 但 Task02 的“可复现”门还不够强，存在两项 P1 级证据缺口：harness 将所有 HTTP `<400` 响应视为成功，没有校验固定 JSON 输出；raw 没有保存 `ResourceProbe` 内存快照、listener/备用端口探针结果或运行环境快照，报告中的关键 NO-GO 证据无法仅凭 raw+harness 自动重放。它们不阻塞 Task03 的单实例 shadow/观测实现，但必须在 Task06 收口前补齐或明确降级为人工证据。

## 关键审查发现

### 通过项

- `benchmark-raw.json` 覆盖 `[1,2,3,4]`，每档均有 cold/warm、TTFT、吞吐、失败率、`/api/ps` `size_vram` 和逐请求样本。
- `ollama-topology-benchmark.py` 使用既有 `/api/chat`、`/api/ps` 接口，设置 `think=false`、`format=json`、固定 `temperature=0`/`num_predict=8`，并设置 `trust_env=False`；未引入第二套业务模型客户端。
- `keep_alive=0` 建立冷加载边界，`30s` 驻留后执行 warm waves，最后 best-effort cleanup；请求超时为 60 秒，未见无限循环或无限并发。
- report 对 4 Worker 相对 1 Worker 的吞吐增幅和 TTFT 退化均可由 raw 复核；`size_vram` 在各档保持同一驻留模型，不能据此声称每 Worker 复制显存。
- Spec027 的 `ResourceProbe.max_safe_workers()` 仍以可用内存 × 0.8 ÷ 单模型驻留占用裁决，异常降 `(1, "RESOURCE_PROBE_FAILED")`；`_GlobalWorkerScheduler` 继续承担全局公平/不超卖，Task02 没有改变既有调度合同。

### 风险与阻塞

- **P1：质量门未真正测量。** harness 仅以 `status < 400` 且无异常设置 `Sample.ok`（`ollama-topology-benchmark.py:75–110`），没有累积/解析响应内容，也没有断言输出为 `{"ok":true}`。因此“失败率 0%”严格说只是 HTTP/传输成功率， malformed JSON 或错误答案可能被计为成功，不能作为质量不退化证据。
- **P1：关键环境证据未进入 raw。** report 声称可用内存 `5,364,842,496`、`ResourceProbe` 返回值、`lsof` listener 和 11435–11438 探针结果，但 raw 顶层只保存服务 URL、模型、参数和 blocks；harness 也没有采集这些字段。仅凭提交的 raw/harness 无法复现“多实例 blocked”或重新计算 cap。建议至少保存 probe snapshot、available memory、listener/alternate-port probe、Ollama 版本/平台和命令退出码。
- **P2：参数边界未锁定。** `--workers` 可传入 0、负数、重复值或 5+，`--warm-waves` 可传入 0/负数；默认命令是安全的，但 harness 本身没有强制 Task02 的 1–4 Worker 与正 warm wave 范围。建议在 Task06 前增加参数校验并在合同测试中断言。
- **P2：合同测试偏结构性。** `test_spec031_task02_benchmark_contract.py` 只断言四个 block 和若干正值，没有核对 sample 数量、summary 与 samples 的一致性、所有 HTTP status、输出质量或 raw 的环境 provenance。它能防止文件缺失/明显空数据，但不能阻止人工改写指标。
- 当前复核时本机 `lsof` 仍看到 `*:11434`，但沙箱内对 `127.0.0.1:11434` 的只读 curl 连接失败；这不能推翻交接物在 14:25–14:26 的历史实测，但说明当前环境不能独立重跑真实 Ollama harness，报告应保留“历史运行证据”与“当前不可复跑”区分。

## Task03 门禁决定

**放行 Task03，但仅放行单实例、ResourceProbe 受限的动态观测与 shadow policy。**

- 默认/可用 Worker cap 必须继续读取既有 `ResourceProbe`；探针失败必须保留单 Worker 和 `RESOURCE_PROBE_FAILED`。
- 不得因为本次 2–4 Worker HTTP 200 就提高生产并发；不得启动或配置第二 Ollama 实例。
- 多实例仍为 **NO-GO**，直到在保持 11434 入口的前提下取得第二实例的同口径吞吐、TTFT、峰值内存、失败率、质量和局域网入口证据。
- P1 缺口不要求回退 Task03，但应列入 Task06 收口阻塞项；若 Task03 要把 benchmark 数据作为 policy 激活依据，则必须先补齐质量校验和环境 provenance。

## 后续动作

1. Task03 采用单实例 cap=1 的当前真实结论，继续实现决策/结果记录和 shadow replay，不实现多实例池。
2. Task06 前修订 harness：校验固定 JSON 内容；限制 `workers ∈ {1,2,3,4}`、`warm_waves >= 1`；把 `ResourceProbe` snapshot、内存余量、listener/备用端口探针、版本和命令结果写入 raw。
3. Task06 前增强合同测试，核对 raw summaries 与逐请求 samples 一致，并拒绝缺少 provenance 或质量校验字段的 benchmark artifact。
4. 将本报告作为 Task03 的交接约束；不要把当前 NO-GO 误写成多实例永久禁用，未来满足重评条件后再独立提交 Go/No-Go。

## 验证命令、退出码与结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest --noconftest -q tests/test_spec031_task02_benchmark_contract.py tests/test_spec027_runtime_contract.py tests/test_spec028_runtime_contract.py` | 0 | **46 passed**，0.38s；未运行全量 pytest |
| `.venv/bin/python -m py_compile docs/sdd/plans/031/artifacts/task-02/ollama-topology-benchmark.py tests/test_spec031_task02_benchmark_contract.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |
| 离线 raw 结构/汇总复核 | 0 | 四档 worker、cold/warm 请求数和报告表格数值一致 |
| 当前只读 `lsof`/备用端口探针 | 0（命令完成） | 仍见 `*:11434`；11435–11438 无服务；当前 sandbox curl 到 11434 不可达，未伪造重跑结果 |

## 审查边界

本轮只新增本报告；未修改业务代码、Spec031、既有 ResourceProbe/调度实现或既有测试；未运行全量 pytest；未启动/停止/配置 Ollama 实例；未执行 push/merge/reset/stash/clean。
