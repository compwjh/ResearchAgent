# Task02 M3 Max 加载冒烟

关联：[Spec050](../../../../specs/050-agent-safety-and-factuality.md) · [授权与事件契约](authorization-and-event-contract.md) · [原始数据](m3max-load-smoke.json)

| 项 | 值 |
|---|---|
| 执行日期 | 2026-11-14 |
| 主机 | Apple M3 Max，36 GB 统一内存 |
| Python | 3.11.16（`/Users/wjh/piguard-repro/.venv`） |
| 依赖 | `torch` / `transformers` / `safetensors` / `psutil` 均可用 |
| 范围 | **只读加载 + 单次推理**；不训练、不写权重、不联网、不接入运行时 |

## 1. 命令与退出码

```bash
cd /Users/wjh/piguard-repro
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python /tmp/piguard_load_smoke.py \
  > /tmp/piguard_load_smoke.json 2> /tmp/piguard_load_smoke.err
echo $?   # 0
```

脚本内设 `local_files_only=True`、`HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1`、`SIGALRM` 240s 上限，符合 Spec050「关闭远程代码执行和自动下载」。原始 stdout 见 [m3max-load-smoke.json](m3max-load-smoke.json)，stderr 见 [m3max-load-smoke.stderr.txt](m3max-load-smoke.stderr.txt)。

## 2. 校验前置

加载前先按字节复算权重 SHA-256，不匹配则拒绝加载：

| 项 | 实测 |
|---|---|
| 文件 | `/Users/wjh/piguard-repro/runs/formal-v1/best_model.pth` |
| 字节数 | `735,414,838`（≈ 701 MiB） |
| SHA-256 | `3f284d8e2655ba9714ab2ab449645aa82f4953a1c7ec20cf62402dfb81af35ea` |
| 与 Spec050 候选哈希一致 | 是（`weight_sha_matches_manifest=true`） |

## 3. 资源基线（冒烟前）

| 项 | 实测 |
|---|---|
| 总内存 | 36.0 GB |
| 可用内存 | 14.9 GB |
| 进程 RSS | 18.8 MB |
| **swap 已用** | **15,423.81 MB / 16,384 MB** |
| MPS 可用 | `true` |

**如实记录**：本机 swap 使用率已达 94%，仅余约 960 MB。这是本次冒烟的资源前提，不是空闲机器上的结论。

## 4. 分阶段结果

| 阶段 | 耗时 | 结果 |
|---|---:|---|
| tokenizer 加载 | 1.48 s | 本地 `models/deberta-v3-base`，`local_files_only=True` |
| 架构加载 | 1.19 s | `PIGuard`（`upstream/PIGuard.py`），`num_labels=2`，device=`cpu` |
| state dict 严格加载 | 0.16 s | 200 个参数；`missing_keys=[]`、`unexpected_keys=[]` |
| 单窗口推理 | 0.113 s | `max_length=256`，实际 17 tokens；logits `[1.5542, -1.36]` → `benign(0)` |
| **合计** | **2.95 s** | `conclusion=PASS` |

推理输入为一段包含注入指令的合成文本，用于验证前向可运行；该单次结果**不是**检测效果评价，公开基准与产品端到端仍待执行。

## 5. 峰值与副作用

| 项 | 实测 |
|---|---|
| 加载后 RSS | 1,867.0 MB |
| 推理后 RSS | 2,009.2 MB（峰值 2,009.5 MB） |
| 结束时可用内存 | 14.53 GB（较基线 -0.37 GB） |
| **swap 增量** | **0.0 MB**（15,423.81 → 15,423.81 MB） |
| 退出码 | `0` |

单模型 CPU 加载常驻约 2.0 GB，本次未触发新的 swap 换出。

## 6. 结论与边界

- **加载可行性**：候选权重可按清单固定值加载，参数结构严格匹配，单窗口 256 token 前向可用，`PASS`。
- **本次未做**（按 Task02 范围，留待后续任务）：
  - 未做 MPS/GPU 推理计时（本次 `device=cpu`，仅确认 `mps_available=true`）。
  - 未做并发、排队、超时与失败注入；Spec050 要求「推理限制并发及队列，双模型常驻须经实测」，本次只验证**单模型单次**。
  - 未做 safetensors 离线转换与转换前后同输入一致性（Task08）。
  - 未做 4B 与 27B 双模型常驻、峰值统一内存与 swap 的联合实测。
  - 未把检测器接入任何运行时端点，默认关闭状态不变。
- **风险**：swap 基线已近满，双模型常驻与并发队列仍有不确定性；若后续实测不稳定，按 Spec050「记录第二次交付阻塞」处理，不影响第一次交付。
