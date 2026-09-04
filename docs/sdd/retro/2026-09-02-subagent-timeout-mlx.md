# 复盘：子代理 junior-dev 超时无产出的根因与解决（mlx 模型替换）

> 关联：spec-013 任务 02、任务 03
> 日期：2026-09-02
> 性质：子代理可用性 + 本地模型选型。**结论需同步进 `AGENTS.md` 的「编码任务的模型选择依据」章节**（模型选型会反复用到，不是一次性问题）。

## 1. 现象

spec-013 任务 02、03 中连续两次分派 `junior-dev` 均失败：

| 次序 | 任务 | 结果 |
|---|---|---|
| 第 1 次 | 编写 4 个部署脚本（要求输出 4 个文件全文） | `Idle timeout - no output for too long` |
| 第 2 次 | 只读分析 qdrant-client 版本兼容性（不写文件） | `Subagent execution failed (code=10003): aborted` |

第二次任务更轻却也失败，说明**不是"任务太重"这么简单**。

## 2. 查验过程（关键：先证伪最容易误判的方向）

### 2.1 先确认"它以前能不能干活"

查 `.codebuddy/agent-logs/`，发现 `junior-dev` 历史上有大量详细日志：

```
junior-dev-011-20260831-000000.md          5050 B   （spec-011 前端改动，日志详实）
junior-dev-012-normalize-20260831-214331.md 9934 B  （spec-012 normalize.py）
junior-dev-012-chunkers-20260901-021053.md  1006 B  （spec-012 chunkers.py）
```

而本次两次分派**连第一条日志都没写出来**。

→ 结论：**配置没问题**（否则会像 2026-09-01 那次一样直接报 `model not found`），而是执行阶段卡住/超时。这排除了"模型名注册错误"这个最容易误判的方向。

### 2.2 确认配置与注册状态

- `.codebuddy/agents/junior-dev.md` 的 `model: qwen3.8-27b-q4`
- 用户级 `~/.codebuddy/models.json` 中存在同名 id（3.9 时期已按 `2026-09-01-subagent-model-naming.md` 的铁律注册）
- 模型在 Ollama 侧可响应

→ 配置链路完整无误。

### 2.3 量化模型本身的耗时（决定性证据）

用 Ollama 原生 timings 对两个 27B 模型做对照（各生成约 120 token，`think:false`）：

| 模型 | 总耗时 | 加载 | 预填充 | 解码 | 速度 |
|---|---|---|---|---|---|
| `qwen3.8:27b-mlx` | 8.45 s | 6.99 s | **0.30 s** | 1.11 s | **24.3 tok/s** |
| `qwen3.8-27b-q4`（原用） | 12.22 s | 9.00 s | 1.15 s | 2.03 s | **13.8 tok/s** |

**mlx 版解码快 76%、预填充快 3.8 倍、加载快 22%。**

### 2.4 环境层面的加重因素

检查系统资源时发现内存压力显著：

```
System-wide memory free percentage: 27%
vm.swapusage: total = 10240.00M  used = 8625.56M   （swap 用掉 86%）
Pageins: 51305526                                   （换页极其频繁）
```

当时本机同时运行：ClickHouse + PostgreSQL + Redis + MinIO + Langfuse web(Next.js dev) + Langfuse worker，而 Ollama 侧还常驻着 27B 模型。

## 3. 根因

三个因素叠加，而非单一原因：

1. **主因：模型推理吞吐低**。27B GGUF 只有 13.8 tok/s，而子代理任务需要生成几百到数千 token（第 1 次任务要求输出 4 个脚本全文，估算 3000+ token，仅生成就要 4 分钟以上）。
2. **每次分派都要付冷启动费**：`load_duration` 7~9 秒。Ollama 默认 `keep_alive` 只有 5 分钟，两次分派间隔超过就被卸载。
3. **加重因素：系统内存压力**（swap 86%、频繁换页）进一步拖慢推理。

> 值得注意：这与 spec-013 要解决的"对话首 token 太慢"是**同一个根因**——用户感受到的慢，和子代理超时的慢，都来自 27B 模型的加载与解码开销。

## 4. 解决方案

用户提供了 `qwen3.8:27b-mlx`（已下载），据此替换：

1. **备份**用户级 `~/.codebuddy/models.json`（历史教训：改乱配置会导致用户无法选择线上模型）。
2. 在 `models.json` 的 `models` 数组中**追加**条目（克隆已验证可用的 `qwen3.8-27b-q4` 条目字段，只改 `id`/`name`）：
   ```json
   {
     "id": "qwen3.8:27b-mlx",
     "name": "qwen3.8:27b-mlx",
     "vendor": "user",
     "url": "http://localhost:11434/v1/chat/completions",
     "maxInputTokens": 32768,
     "maxOutputTokens": 32768,
     "supportsToolCall": true,
     "supportsImages": true,
     "supportsReasoning": true
   }
   ```
3. 校验 JSON 语法与**重复 id**（历史上被重复 id 坑过）。
4. 用 curl 打到 Ollama 的 `/v1/chat/completions` 确认该模型名可响应，再改 agent 配置。
5. 改 `.codebuddy/agents/junior-dev.md`：`model: qwen3.8-27b-q4` → `model: qwen3.8:27b-mlx`。

## 5. 验证

分派**极窄任务**（写单个 README，≤60 行）做对照实验：

- 结果：**成功**，耗时 220.84s，8 次工具调用
- 产出：`deploy/langfuse/README.md`（46 行），进展日志已落盘
- 对照：此前同等甚至更轻的任务均失败

→ **mlx 替换确实解决了超时问题。**

## 6. 落地校验抓到的两个错误（证明"必须校验、不能盲信子代理"）

子代理产出的 README 里写了这条命令：

```bash
mysql -h127.0.0.1 -P8123 -q < deploy/langfuse/clickhouse-grants.sql   # 错误
```

问题：本机没有 mysql，且 8123 是 ClickHouse 的 **HTTP 接口**（MySQL 兼容端口是 9004）。

我改成 curl 后实测，又暴露第二个问题：

```
Code: 62. DB::Exception: Syntax error (Multi-statements are not allowed)
```

→ ClickHouse 的 HTTP 接口**默认不接受多语句**，而 grants.sql 是多语句脚本。

最终修正为（已实测 exit=0、授权 74 项生效）：

```bash
~/opt/clickhouse/clickhouse client --host 127.0.0.1 --port 9000 --user default \
  --multiquery < deploy/langfuse/clickhouse-grants.sql
```

**这两处错误如果没做落地校验，会写进文档误导后续操作。**

## 7. 可复用规则

1. **子代理失败时，先查历史日志判断"它以前行不行"**——能快速区分"配置坏"与"执行慢"，避免重复排查已解决的配置问题。
2. **Apple Silicon 上优先用 mlx 版模型**：同样 27B，mlx 比 GGUF 解码快 76%、预填充快近 4 倍。本机已有 `qwen3.8:27b-mlx`。
3. **给 27B 子代理派活要控输出量**：按 13.8 tok/s（GGUF）或 24 tok/s（mlx）估算生成时间，一次只让它产出一个文件。第 1 次失败的根源就是要求它一次性输出 4 个脚本全文。
4. **子代理产出必须落地校验**：尤其是命令类内容，要实际执行验证。本次连抓两个错误（mysql 命令、curl 多语句）。
5. **评估子代理性能时要看系统整体负载**：内存 swap 用掉 86% 时，模型推理慢不全怪模型。
6. **改 `models.json` 前必须备份**，改后校验语法与重复 id（沿用 `2026-09-01-subagent-model-naming.md` 的教训）。
7. **模型名必须「三层一致」，且以绑定层为准**（2026-09-03 补，本次复盘的延伸教训）：

   | 层 | 位置 | 作用 |
   |---|---|---|
   | **绑定层** | `.codebuddy/agents/*.md` 的 `model:` 字段 | **决定实际跑哪个模型** |
   | **注册层** | **用户级** `~/.codebuddy/models.json` | 框架查找模型的白名单；项目级不被识别 |
   | **文档层** | `AGENTS.md` 角色分配表、`docs/sdd/MODEL_REGISTRY.md` | 供人查阅与 spec 执行配置取用 |

   - 任一处不一致，就会出现「照文档分派却跑了别的模型」或 `model not found` 静默回退。
   - **文档只能描述绑定层，不能反过来当配置来源**——本次正是文档层（分配表写 GGUF 旧值）滞后于绑定层（已是 mlx），且与 `AGENTS.md` 自身第 112 行「27B 一律用 MLX」的规则自相矛盾。
   - 写法陷阱：`qwen3.8:27b-mlx` 是**冒号**；`qwen3.8-27b-mlx`（连字符）在 Ollama 中不存在，填了必然失败。

## 8. 待办

- [x] 把 mlx 选型结论同步进 `AGENTS.md`（2026-09-03 已完成：①「角色模型分配」表中 `junior-dev`/`tech-lead` 改为 `qwen3.8:27b-mlx`，并加"必须与 agent 文件逐字一致"警示；②「编码任务的模型选择依据」沿用既有 MLX 规则；③ `docs/sdd/MODEL_REGISTRY.md` 新增 MLX 条目、GGUF 标记弃用、选型速查同步——同时关闭 spec-014/016 与 014 技术评审标记的"模型库未登记 MLX"缺口）
- [ ] 后续给 `junior-dev` 分派时保持"单文件 + 明确输出路径 + 要求写进展日志"的模式
