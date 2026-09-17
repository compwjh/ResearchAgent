# Task 06 后端论文选集投影修复报告

## 根因

`evaluate_papers` 已经通过 `ResearchStore.replace_selections()` 把论文选集写入既有 `research_paper_selections` 表，但完成态 `worker` 事件只写入 `selected_count`，没有写入稳定的 `selected_paper_ids`。前端已有按该字段即时显示选集的投影接缝，因此在最终报告生成前无法展示已完成评估的选集。

## 改动文件

- `backend/app/research/application/orchestrator.py`
  - evaluate_papers 完成事件增加 `selected_paper_ids`。
  - 仅传递 `catalog_paper_id`，不复制标题、摘要、关键词或评估推理。
- `backend/app/research/infrastructure/research_store.py`
  - 将 `selected_paper_ids` 加入现有事件安全字段白名单。
- `tests/test_spec031_selection_projection.py`
  - 验证稳定 ID 可通过安全事件投影，标题、摘要、reasoning 等字段不会落盘。

未新建选集存储，仍以 `replace_selections/list_selections` 为权威来源。

## 测试命令、退出码与结果

1. `.venv/bin/python -m pytest -q tests/test_spec031_selection_projection.py tests/test_spec031_shadow_observation.py`
   - 退出码：0
   - 结果：17 passed。
2. `.venv/bin/python -m pytest -q tests/test_spec027_backend_research_slice.py -k 'minimal_loop_completes_with_at_least_two_parallel_searches or report_includes_safe_selection_projection_only or events_stream_is_sse_and_sequence_is_continuous'`
   - 退出码：0
   - 结果：3 passed，54 deselected。
3. `python -m py_compile backend/app/research/application/orchestrator.py backend/app/research/infrastructure/research_store.py tests/test_spec031_selection_projection.py`
   - 退出码：0。

## 风险与阻塞

- 事件仍只暴露目录论文 ID；标题、摘要、关键词继续由既有论文目录读取接缝负责，避免在 Research 事件中复制论文元数据。
- 本次未修改前端；前端已经消费 `selected_paper_ids` 并显示论文选集区域。
- 工作树中存在其他 Agent 的并行修改（会话压缩及 Task02 基准相关文件），本任务未触碰、未提交。
- Spec031 Task06 的全量回归仍由主 Agent 统一处理；本修复不替代全量回归。

## 开始、结束与耗时

- 开始：2026-09-17（本地时区，具体执行时间见 backend-dev 日志）
- 结束：2026-09-17 18:20（本地时区）
- 总耗时：约 10 分钟

## 模型与工具统计

- 模型：Luna high（临时分派）
- 工具调用：文件读取、补丁编辑、pytest、py_compile、git diff/status；未执行 commit/push。
- token 统计：由主 Agent 编排器提供，本子 Agent 未获得可靠计数。

## 主 Agent 后续动作

1. 将本报告纳入 Task06 交接材料。
2. 与并行改动合并后重启服务，运行研究评估 smoke，确认完成事件带 `selected_paper_ids` 且页面在报告生成前显示“论文选集”。
3. 按 Spec031 Task06 规则执行最终全量回归和收口评审。
