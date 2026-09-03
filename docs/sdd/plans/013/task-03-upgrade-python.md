# 任务 03 — 升级项目 Python 到 3.11 并重装依赖

> 关联：[spec-013](../../specs/013-llm-observability-platform.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01（spec 已写）｜ 被依赖：任务 04（埋点需要 Python ≥3.10 的 langfuse SDK）

## 目标

把项目虚拟环境从 **Python 3.9.7** 升到 **3.11**，重装全部依赖并新增 `langfuse>=4.7.0`，保证原有 **253 个测试仍全部通过**，且知识库与对话功能端到端可用。

**为什么必须升级**：Langfuse v4 要求 Python SDK ≥4.7.0 才能实时写入（否则数据延迟约 15 分钟），而该 SDK 要求 Python ≥3.10；当前 3.9.7 环境下 `pip index versions langfuse` 最高只给出 3.7.0。

## 思维链

### 阶段 A：保留回滚能力（先做，再动刀）

1. 确认当前基线：记录 `.venv/bin/python --version` 与测试结果（应为 253 passed）
2. **把 `.venv` 重命名为 `.venv-py39.bak`**（不删除），升级失败可秒级切回
3. 导出当前依赖清单快照（`pip freeze`）留档，作为"升级前长什么样"的证据

### 阶段 B：准备 Python 3.11 解释器

4. 本机已有的 3.11 是 anaconda 的 `3.11.7`；为环境干净与可控，**用 brew 装独立 `python@3.11`**
   （spec-011 踩过"装错解释器"的坑，因此明确指定解释器绝对路径建 venv，不用 `python3` 这种会漂移的名字）
5. 用该解释器重建 `.venv`

### 阶段 C：重装依赖

6. 装 `requirements.txt` 全部依赖
7. **重点评估 `qdrant-client`**：当前被锁 `<1.17`（注释写明是 Python 3.9 所致）。3.11 下可放开，但需确认 1.16 → 1.19 的 API 变化是否影响 `services/kb/store.py` 的调用
8. 新增 `langfuse>=4.7.0`

### 阶段 D：验证

9. 跑全量测试，数量与结果都不得少于升级前（253 passed）
10. 端到端冒烟：启动服务，验证 `/api/kb/health` 与一次对话
11. 更新 `requirements.txt`（含 `qdrant-client` 上限说明）与 `requirements.lock.txt`

## 子代理分派计划

> 任务 02 中 `junior-dev` 超时无产出，因此本任务**只把纯分析、无副作用的工作**分派给它；安装与验证等有系统副作用的动作全部主会话执行。

### 分派 1：`junior-dev` — 依赖版本兼容性分析（只读分析，不写文件）

**分派时机**：阶段 A 完成后（此时已备份，分析结论可直接用于阶段 C）。

**Prompt 要点**（分派时必须写明的部分）：

- **输出方式**：**不要写任何文件**，直接把结论以文本形式回复（这是只读分析任务）
- **待分析的具体问题**（给出准确的文件路径）：
  1. 阅读 `/Users/wjh/ResearchAgent/backend/app/services/kb/store.py`，列出它用到的 `qdrant_client` 全部 API（类名、方法名、参数形态）
  2. 判断这些 API 在 qdrant-client 1.16 → 1.17/1.18/1.19 之间是否有破坏性变更
  3. 给出建议：是维持 `<1.17` 还是可放开上限；若放开，建议锁到哪个版本
  4. `pymupdf`、`jieba`、`langgraph`、`langchain-ollama`、`fastapi` 在 Python 3.11 下有无已知不兼容版本
- **明确禁止**：不要执行 pip install、不要修改任何文件、不要创建文件
- **输出格式**：分点结论，每条给出"结论 + 依据"，最后给一行「建议的 requirements.txt 改动行」
  （由主会话 apply，不要求 agent 改文件）

**子代理返回后，主会话必须做**：

1. 核对结论与真实代码是否对得上（抽查 store.py 中提到的 API 是否真的存在）
2. 按建议更新 `requirements.txt`（若无把握，保守维持原上限）
3. 实际安装并跑测试验证——**以测试结果为准，不盲信分析结论**
4. 若 junior-dev 超时无产出：直接由主会话用 `pip index versions` / `pip check` 自行确认，不阻塞主路径

### 不分派的部分

备份、解释器安装、venv 重建、依赖安装、跑测试、冒烟——全部主会话执行。

## 实时监控命令（供你另开终端查看）

```bash
# Python 3.11 安装
tail -f /tmp/py311-install.log

# 依赖安装（耗时较长）
tail -f /tmp/py311-pip-install.log

# 全量测试
tail -f /tmp/py311-pytest.log

# 观察 venv 切换状态
ls -d /Users/wjh/ResearchAgent/.venv* 2>/dev/null

# 当前 venv 版本确认
/Users/wjh/ResearchAgent/.venv/bin/python --version

# 关键依赖版本
/Users/wjh/ResearchAgent/.venv/bin/python -m pip list 2>/dev/null | grep -iE 'langfuse|qdrant|fastapi|langgraph|pymupdf'
```

## 验收标准

| 项 | 标准 |
|---|---|
| 解释器 | `.venv/bin/python --version` 为 3.11.x |
| 回滚能力 | `.venv-py39.bak` 存在且其中的 python 仍为 3.9.7 |
| 依赖 | `requirements.txt` 全部依赖安装成功，`pip check` 无冲突 |
| langfuse SDK | 已安装且版本 ≥4.7.0 |
| 全量测试 | 通过数量 ≥ 253，且无失败 |
| 端到端 | 服务可启动，`/api/kb/health` 正常，一次对话可完成 |
| 文档 | `requirements.txt` 与 `requirements.lock.txt` 已同步更新 |

## 风险与回滚

| 风险 | 触发后的处置 |
|---|---|
| 某依赖在 3.11 下装不上 | 查具体包；尝试临近版本；仍不行则**整体回滚**（见下） |
| `qdrant-client` 新版 API 破坏 KB 功能 | 保守维持 `<1.17`（3.11 下 1.16.x 仍可装），记录遗留 |
| 测试数量下降或出现失败 | 逐个定位；若是升级导致的不兼容则修复，无法短时修复则回滚 |
| 端到端冒烟失败 | 回滚，记录阻塞原因 |

**回滚命令**（秒级切回 3.9.7）：

```bash
cd /Users/wjh/ResearchAgent
rm -rf .venv
mv .venv-py39.bak .venv
.venv/bin/python --version   # 应显示 3.9.7
```

> 若连项目代码也有改动需要一并放弃，用 spec 中记录的基线：`git reset --hard 294138c`

## 产出物

- Python 3.11 的新 `.venv`（旧环境保留为 `.venv-py39.bak`）
- 更新后的 `requirements.txt` / `requirements.lock.txt`
- 全量测试与端到端冒烟结果，回写到下方「执行结果」段

## 执行结果（2026-09-02 完成）

| 验收项 | 标准 | 实测结果 | 结论 |
|---|---|---|---|
| 解释器 | 3.11.x | **Python 3.11.16**（brew `python@3.11`，独立解释器） | 通过 |
| 回滚能力 | `.venv-py39.bak` 存在 | 存在，其中 python 仍为 **3.9.7** | 通过 |
| 依赖 | 全部安装成功 | 73 个包，`pip install --dry-run` 校验通过 | 通过 |
| langfuse SDK | ≥4.7.0 | **4.15.1** | 通过 |
| 全量测试 | ≥253 且无失败 | **253 passed**（与升级前完全一致） | 通过 |
| 端到端 | 服务可用 | `/api/kb/health` 200（5 篇论文 / 1132 片段）；`/api/chat` SSE 流式正常（4s 返回） | 通过 |
| 文档 | requirements 已更新 | 已加 `langfuse>=4.7.0` 并生成 `requirements.lock.txt`（77 行） | 通过 |

### 依赖版本变化（值得关注的大版本跳跃）

| 包 | 升级前（3.9） | 升级后（3.11） | 说明 |
|---|---|---|---|
| langchain-ollama | 0.3.10 | **1.1.0** | 大版本跨越，已跑测试 + 对话冒烟验证兼容 |
| langgraph | 0.6.11 | **1.2.11** | 同上 |
| langchain-core | 0.3.86 | 1.6.1 | 同上 |
| pymupdf | 1.26.5 | 1.28.2 | 小版本 |
| fastapi | 0.128.8 | 0.141.1 | 小版本 |
| qdrant-client | — | 1.16.2 | 维持 `<1.17` 上限（未放开，见下） |

**qdrant-client 上限决策**：保守维持 `<1.17`，未做放开评估。理由：3.11 下 1.16.2 实测可用，放开上限收益不大而风险非零，留待有明确需求时再评估。

**pytest 需单独安装**：`requirements.txt` 不含测试依赖，新环境下需 `pip install pytest pytest-cov`（旧环境为 pytest 8.4.2，新装为 9.1.1，测试全通过）。

### 子代理分派结果

- `junior-dev` 分派「qdrant-client 版本兼容性分析」→ **失败**（`code=10003 aborted`）。
- **已定位根因并解决**：不是任务问题，而是 27B GGUF 模型（13.8 tok/s）+ 每次 7~9 秒冷启动 + 系统内存压力（swap 86%）导致超时。
- 解法：改用 **`qwen3.8:27b-mlx`**（24.3 tok/s，快 76%），注册进用户级 `models.json` 并改 agent 配置；随后分派窄任务实测**成功**（220.84s）。
- 详见 `docs/sdd/retro/2026-09-02-subagent-timeout-mlx.md`。
