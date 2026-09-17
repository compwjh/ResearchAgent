# Spec031 Task02：Ollama 拓扑基准门报告

## 结论

**单 Ollama 服务基准：GO（受资源探针约束）。多实例：NO-GO / blocked。**

- 现有 `qwen3.5:9b` 在单服务 `127.0.0.1:11434` 上完成 1/2/3/4 Worker 的冷/热受控请求，所有请求 HTTP 200，失败率 0。
- 热请求的聚合吞吐随 Worker 数由 12.502 → 16.012 completion tokens/s（4 Worker 相对 1 Worker 约 +28.1%），但中位 TTFT 由 220.580 → 761.619 ms（约 3.45×）。
- `/api/ps` 观察到单个 9B 模型驻留约 6,636,510,902 bytes（约 6.18 GiB）；模型共享驻留，未观察到每 Worker 额外复制显存。
- 在模型驻留时系统可用内存为 5,364,842,496 bytes，既有 `ResourceProbe.max_safe_workers()` 返回 `(1, None)`；清理模型后 `/api/ps` 为空，探针诚实返回 `(1, "RESOURCE_PROBE_FAILED")`。因此当前主机不能据此放行 2–4 个正常 Worker，Task03 应保留单 Worker 上限与失败降级。
- 当前只发现 `*:11434` 一个 Ollama listener；11435–11438 只读探针均无服务。没有第二实例的吞吐、内存或局域网入口保持证据，且第二份约 6.6 GiB 模型驻留会违反当前 20% 余量条件，故多实例不放行。

## 环境与固定输入

| 项目 | 值 |
|---|---|
| 时间 | 2026-09-17 14:25:52–14:26:37（Asia/Shanghai，UTC 06:25:52–06:26:37） |
| 服务 | `http://127.0.0.1:11434`；既有 listener `*:11434` |
| 模型 | `qwen3.5:9b`；`/api/tags` HTTP 200；模型文件 size `6,594,474,711` bytes |
| 输入 | `Return exactly the JSON object {"ok":true} and nothing else.` |
| 请求 | `stream=true`、`think=false`、`format=json`、`temperature=0`、`num_predict=8` |
| 冷样本 | 每个 Worker 档先以 `keep_alive=0` 并发一波；计入冷启动/加载耗时 |
| 热样本 | 每个 Worker 档预热后顺序执行 2 个并发波次；预热不计入热样本 |
| 指标 | TTFT 为客户端首个 token；服务端时延来自 Ollama 原生纳秒字段；吞吐按每个并发波次最长墙钟时间聚合；峰值显存来自 `/api/ps` |

## 1–4 Worker 结果

| Worker | 冷请求 | 热请求 | 热中位 TTFT (ms) | 热聚合吞吐 (tok/s) | 热失败率 | 峰值 `size_vram` (bytes) |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1/1 | 2/2 | 220.580 | 12.502 | 0% | 6,636,510,902 |
| 2 | 2/2 | 4/4 | 476.729 | 12.745 | 0% | 6,636,510,902 |
| 3 | 3/3 | 6/6 | 640.105 | 14.447 | 0% | 6,636,510,902 |
| 4 | 4/4 | 8/8 | 761.619 | 16.012 | 0% | 6,636,510,902 |

冷启动中位 TTFT / 聚合吞吐分别为：1 Worker `4108.342 ms / 1.380 tok/s`、2 Worker `3908.800 ms / 2.791 tok/s`、3 Worker `4266.371 ms / 3.535 tok/s`、4 Worker `4362.848 ms / 4.508 tok/s`。冷启动结果仅用于加载成本，不作为长期并发策略依据。

原始逐请求数据、`/api/ps` 快照和时间戳见 [`benchmark-raw.json`](./benchmark-raw.json)；可重跑 harness 见 [`ollama-topology-benchmark.py`](./ollama-topology-benchmark.py)。

## 多实例 Go/No-Go

结论：**NO-GO（当前环境 blocked，未启动或修改任何第二实例）**。

证据：

1. `lsof` 只发现 `*:11434` 的 `ollama` listener；11435、11436、11437、11438 的 `/api/tags` 只读探针均连接失败（HTTP 000，curl exit 7）。
2. 未配置或验证第二端口的模型、负载、显存和局域网访问；不能把单实例结果外推成多实例收益。
3. 当前驻留一个 9B 模型约 6.18 GiB，而驻留时可用内存约 5.00 GiB；在 Spec031 要求的至少 20% 余量下，增加第二份模型没有安全资源证据。
4. 既有入口 `11434` 未改变。后续若要重评，须在不改变入口的受控内部端口池上，用同一 harness 同时记录服务端吞吐、TTFT、`/api/ps` 峰值和故障率，并先证明资源余量与局域网入口不退化。

## 验证记录

| 命令/动作 | 结果 |
|---|---|
| `.venv/bin/python ...ollama-topology-benchmark.py --warm-waves 2 --workers 1,2,3,4` | exit 0；45.14 s；原始数据已落盘 |
| `.venv/bin/python -m pytest --noconftest -q tests/test_spec031_task02_benchmark_contract.py tests/test_spec027_runtime_contract.py tests/test_spec028_runtime_contract.py` | exit 0；46 passed |
| `.venv/bin/python -m py_compile ...ollama-topology-benchmark.py tests/test_spec031_task02_benchmark_contract.py` | exit 0 |
| `git diff --check` | exit 0 |
| 真实 `/api/tags`、`/api/ps` 与 1-token ResourceProbe 探针 | HTTP/调用成功；模型加载时 cap=1；清理后探针失败降级为 1 |
| 11435–11438 多实例只读探针 | 均无服务；未伪造多实例数据 |

系统 Python 直接收集既有 `tests/test_ollama_direct.py` / `tests/test_ollama_service.py` 时因环境缺少 `langchain_ollama` 报 collection error；项目 `.venv` 含完整依赖，本 Task 定向合同测试在 `.venv` 中通过。未运行全量 pytest。

文件 SHA-256：

- `benchmark-raw.json`: `ad36d67fe8b32a224d0e4300803cc3d1fe999082483318b64684ed7cae011168`
- `ollama-topology-benchmark.py`: `5eed1118250ceecb4bacf0c0539cd70a5ddbbbfd2313205c5345559265b9d8f7`
- `test_spec031_task02_benchmark_contract.py`: `5934ab7664615537f2279e07a6d4d4a1a8868b6e69ccc2b351f904de32ae0393`

## Task03 门禁与风险

- **放行条件**：Task03 可按单实例、动态路由观测和 shadow policy 继续；默认 Worker cap 取既有 `ResourceProbe` 结果，探针失败必须保留 `RESOURCE_PROBE_FAILED` 与单 Worker 降级。
- **不放行**：不得因本次 2–4 并发请求均成功就提升生产并发，也不得启用第二 Ollama 实例。
- **重评条件**：获得真实第二实例并保持 11434 入口后，重复本 harness；只有在资源余量、失败率、TTFT 和聚合吞吐均有可解释净收益时，才重新提交多实例 Go/No-Go。
- **范围控制**：本 Task 未改 `backend/**`、前端、Ollama 安装或监听方式；仅新增 artifact harness/raw/report 与离线合同测试。
