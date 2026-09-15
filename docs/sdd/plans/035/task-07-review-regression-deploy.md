> 关联：[spec-035](../../specs/035-online-model-provider.md) ｜ 索引：[README](./README.md)
> 依赖：任务 05、06；当前状态：`待执行`

## 1. 状态与一句话目标

`待执行`。跑通测试与三道评审门禁、执行回归、真实部署并完成复盘，使 spec-035 具备转 `已完成` 的全部条件。

## 2. 背景与前置条件

- 依赖任务 05（后端全部）与 06（前端全部）完成。
- 门禁规则见 `docs/sdd/SDD-GATE-CHECKLIST.md`；三份评审：`035-requirement-review.md`（`architect`）、`035-tech-review.md`（`architect`）、`035-acceptance-review.md`（`tester` 总控 + 架构师签字）。
- **低消耗硬约束（用户明确要求）**：开发/验收阶段**只测连通性**，唯一允许的真实请求是 `max_tokens=1` 的最小 chat completion；无 Key 的环境必须 `skip`，**不得因缺 Key 而 fail**。

## 3. 数据、配置与接口

不适用（本任务不新增接口，只做验证与收口）。

## 4. 实施步骤与文件边界

| 顺序 | 动作 | 负责 |
|---|---|---|
| 1 | 后端定向回归（`tests/test_online_*` + 受影响的对话/KB/ollama 测试） | `backend-tester` |
| 2 | 前端契约核对（`node --check` + 前端契约测试 + DOM/CSS 交叉核对） | `frontend-tester` |
| 3 | **真实连通性人工验证**：在 `.env` 填一个真实 DeepSeek Key，重启服务，打开模型库确认线上卡片状态；**只点一次**，验证完即从 `.env` 移除或置空 | 架构师（主会话） |
| 4 | 需求评审 + 技术评审 | `architect` |
| 5 | 跨端验收评审（汇总单端报告） | `tester` |
| 6 | 全量回归（唯一一次） | `backend-tester` |
| 7 | 部署 + 运行时 smoke | 架构师（主会话） |
| 8 | 复盘落盘 | 架构师（主会话） |

文档产出：`docs/sdd/reviews/035-requirement-review.md`、`035-tech-review.md`、`035-backend-regression.md`、`035-acceptance-review.md`。

## 5. 子代理分派

| 角色 | 模型 | 范围 |
|---|---|---|
| `backend-tester` | `Deepseek-V4.1-Flash` | 只跑后端 pytest |
| `frontend-tester` | `Deepseek-V4.1-Flash` | 只做前端静态核对，**不跑后端 pytest** |
| `tester` | `Deepseek-V4.1-Flash` | 跨端验收总控，产出 `035-acceptance-review.md` |
| `architect` | `Deepseek-V4.1-Flash` | 需求/技术评审 + 签字 |

## 6. 边界与明确不做

- 边界：无 Key 环境 / Key 错误 / 网络不通 / Ollama 不可达 / 只配线上 / 只配端侧。
- 明确不做：不做压力测试；不做计费/用量统计；不把真实 Key 提交进 git（提交前 `git status` 确认 `.env` 未被包含）。

## 7. 验收、风险与回滚

验收（对应 spec 验收场景 A–E）：

- **A**：配置正确 → 模型库分两组、线上卡片「已连通」、选中后对话真实返回。
- **B**：`API_KEY` 置空 → 该线上模型**不出现**，端侧不受影响。
- **C**：Key 错误 → 卡片「连接失败」，对话返回明确错误，服务不崩溃。
- **D**：`ONLINE_MODELS` 非法 → 服务正常启动，非法项跳过并记日志。
- **E**：无线上配置 → 模型库退化为改动前形态，无回归。

```bash
env -u PYTHONPATH .venv/bin/python -m pytest tests -q --basetemp=/tmp/s035full
./deploy/stop.sh && ./deploy/start.sh -d
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/
curl -s "http://127.0.0.1:8000/api/models" | python3 -m json.tool
```

- 风险：全量回归受沙箱影响可能出现 `pytest-of-unknown` EEXIST，**必须换全新 `--basetemp` 重跑**，结论以重跑为准。
- 回滚：卸载 `langchain-openai` + 清空 `.env` 的 `ONLINE_MODELS` 即回到改动前行为（`/api/health` 与 `create_chat_model` 本地分支均未变）。

## 8. 产出物、执行结果与变更日志

待执行后填写。
