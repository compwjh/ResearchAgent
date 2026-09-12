# Task 02：后端能力失败语义与 default_effort 修正

> 关联：[spec-026](../../specs/026-reasoning-effort-feedback-fixes.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01；当前状态：`已完成`

## 一句话目标

让能力探测失败不再抛异常，而是产出 `unknown` / `stale` 两态能力对象；并把 `default_effort` 从「最低档」修正为「支持的最高档」。

## 背景与前置条件

- 已确认 spec：[`docs/sdd/specs/026-reasoning-effort-feedback-fixes.md`](../../specs/026-reasoning-effort-feedback-fixes.md)（重点 §对 Spec 024 的修订声明、§数据模型、边界 B1–B4、B16）。
- 现状代码：`backend/app/platform/ollama.py`
  - `probe_reasoning_capabilities`（约 69-95 行）：5 档串行探测，全空即 `raise RuntimeError("MODEL_CAPABILITIES_UNAVAILABLE")`。
  - `get_reasoning_capabilities`（约 99-107 行）：300s TTL 进程内缓存，过期即丢弃旧值再探测。
  - 第 97 行：`default = "xhigh" if "xhigh" in supported else supported[0]` —— `supported[0]` 恒为 `off`。
- 前置：spec 已转 `已确认`。未确认不得动业务代码。

## 数据、配置与接口

- 本任务只改 `ReasoningCapabilities` 的**构造与缓存语义**，不改 HTTP 接口（接口改动在 Task 03）。
- `source` 新增取值：`stale`、`unknown`。`unavailable` 保留。
- `default_effort` 新算法：`supported` 中按 `REASONING_EFFORTS` 序位最高者（即 `supported[-1]`）。
- 缓存条目需额外保存「上次成功的 `cached_at` 时刻」以支持 `stale`；建议缓存结构由 `(monotonic_ts, caps)` 扩展为保存 `caps`（含其原始 `cached_at`）。

## 实施步骤与文件边界

目标文件：**仅 `backend/app/platform/ollama.py`**（及其单元测试）。

1. 将 `probe_reasoning_capabilities` 的「全空即 raise」改为返回 `supported=()`、`default_effort=None`、`source="unknown"` 的 `ReasoningCapabilities`；**不得**回退为 `('off',)`。
2. 抽出 `default_effort` 计算为独立函数（如 `_highest_supported(supported)`）：按 `REASONING_EFFORTS` 顺序过滤 `supported` 后取最后一个；空集合返回 `None`。
3. `get_reasoning_capabilities` 增加 `refresh` 参数透传；探测失败时：
   - 存在旧缓存条目（不论是否过期）→ 返回 `replace(旧caps, source="stale")`，**保留旧 `cached_at`**；
   - 无任何缓存 → 返回 `unknown` 能力对象。
4. 探测失败**不得**覆盖/清除现有缓存中的有效条目（边界 B16）。
5. 保持 `_capabilities_for_model` 的 `unavailable` 兜底不变。
6. 完成后可观察结果：Ollama 未启动时 `get_reasoning_capabilities(model)` 返回对象而非抛异常；`source` 为 `unknown` 或 `stale`。

## 子代理分派

| 角色 | 模型 | 最小上下文 | 文件范围 | 回读校验 |
|---|---|---|---|---|
| backend-dev | `Deepseek-V4.1-Flash` | spec 026 §数据模型/边界 B1-B4/B16 + `ollama.py` | `backend/app/platform/ollama.py` + 对应测试 | 主会话读回 diff，核对无 raise、无 `('off',)` 回退 |

## 边界与明确不做

- 不做：不改探测为并发、不加预热、不改 5s 超时、不做磁盘持久化（属 spec 027）。
- 不做：不改 HTTP 路由（Task 03）。
- 不做：不新增依赖、不改 `REASONING_EFFORTS` 常量取值与顺序。
- 不得把 `unknown` 的 `supported_efforts` 填成非空。

## 验收、风险与回滚

- 验收：mock httpx 让 5 档全部超时 → 断言返回对象、`source == "unknown"`、`supported_efforts == ()`、`default_effort is None`，且**无异常抛出**。
- 验收：先注入一次成功缓存再让缓存过期、随后探测失败 → 断言 `source == "stale"` 且 `cached_at` 等于旧值。
- 验收：`supported=['off','low','medium']` → `default_effort == "medium"`（不得为 `off`）；`['off','xhigh']` → `xhigh`；`['off']` → `off`。
- 风险：上层 `resolve_reasoning_effort` 可能假设 `default_effort` 非空 → 需同步检查调用方；若发现需在 Task 03 一并处理并记录。
- 回滚：单文件改动，`git checkout -- backend/app/platform/ollama.py` 即可回到 Task 01 状态。

## 产出物、执行结果与变更日志

待执行后填写：真实命令、`pytest` 结果、改动行数、以及调用方假设的检查结论。
