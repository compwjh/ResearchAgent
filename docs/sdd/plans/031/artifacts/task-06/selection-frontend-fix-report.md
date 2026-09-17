# Task06 前端论文选集投影修复报告

## 结果状态和摘要

`完成（前端定向 GO）`。修复候选评估完成、报告尚未生成时“论文选集”区域不出现的问题。前端现在消费安全事件中的选集 ID/数量；当事件只有数量时，通过已有只读 `acquisition-preview` 读取服务器保存的选集快照，并在评估事件与持久化写入之间做最多三次有界重试。

## 根因

前端原先只在报告 `selections` 或事件直接携带 `selected_paper_ids` 时逐条显示；实际评估事件通常只携带 `selected_count`，而持久化选集在报告生成前没有被前端读取。因此页面既没有论文 ID，也没有可操作的候选选集区域。

## 改动文件

- `frontend/research-tasks.js`
  - 增加目录论文 ID 白名单与选集投影归一化。
  - 维护评估阶段选集详情，安全合并事件、快照和报告数据。
  - 复用只读 `acquisition-preview` 获取选集快照；不下载 PDF、不创建新存储。
  - 选集区域在只有 `selected_count` 时也显示“已选 N 篇论文”。
- `tests/test_spec031_frontend.py`
  - 增加 ID、相关性、证据等级、重复项和路径/XSS 边界合同。

## 测试命令、退出码和结果

- `node --check frontend/research-tasks.js` — 退出码 0，通过。
- `.venv/bin/python -m pytest -q tests/test_spec031_frontend.py tests/test_spec029_frontend_acquisition_progress.py tests/test_spec030_frontend.py` — 退出码 0，`8 passed`。
- `git diff --check -- frontend/research-tasks.js tests/test_spec031_frontend.py` — 退出码 0，通过。

## 风险与阻塞

- 该修复复用已有 `acquisition-preview` 端点；如果后端选集尚未写入，前端最多重试三次并保留事件中的数量，不会误报为已获取全文。
- 评估阶段端点仅提供目录论文 ID/状态，相关性和证据等级在报告可用后由报告投影补齐；没有生成模型元数据或敏感字段。
- 未运行 Spec031 Task06 全量回归；全量回归由主 Agent 统一执行。

## 开始、结束和总耗时

- 开始：2026-09-17T10:15:00Z（约）
- 结束：2026-09-17T10:21:50Z
- 总耗时：约 7 分钟

## 模型和统计

- 模型：Luna high（临时分派）
- token / 工具调用统计：当前子 Agent 无可靠统计接口，未伪造。

## 主 Agent 后续动作

1. 检查本报告与 diff，确认仅包含 `frontend/**` 和对应前端合同测试。
2. 将本修复纳入 Task06 的最终收口分支，先运行前端定向测试，再按 Task06 规则运行唯一全量回归。
3. 部署后创建一个已完成候选评估但尚未生成报告的研究任务，确认页面先显示选集 ID/数量，报告完成后补齐相关性与证据等级。

## 变更日志

- 2026-09-17：记录 Task06 前端选集投影修复及定向验证结果。
