> 关联：[Task04](./task-04-offline-evaluation-delivery.md) ｜ [技术评审](../../reviews/042-tech-review.md)
> 子任务：04-D 报告投影
> 状态：**已完成（仅模块实现与语法/smoke 验证）**
> 执行角色：backend-dev（本次临时 Luna xhigh；不写入长期配置）
> 时间：2026-10-23（Asia/Shanghai）

# Task04-D — 本地 JSON/Markdown 报告模块

## 交付范围

只新增 [`backend/eval_042/report.py`](../../../../backend/eval_042/report.py)，未修改 `config.py`、runner、测试、业务 API、部署或运行时服务。模块无第三方依赖，供后续 runner 接入。

## 冻结接口

```python
class ReportWriter:
    def __init__(
        self,
        output_dir: str | Path,
        metadata: Mapping[str, object] | None = None,
    ) -> None: ...

    document: dict[str, Any]

    def checkpoint(self, document: dict[str, Any]) -> dict[str, Any]: ...

    def finish(
        self,
        status: str,
        *,
        errors: Sequence[object] | None = None,
    ) -> dict[str, Any]: ...

def make_report(metadata: Mapping[str, object] | None = None) -> dict[str, Any]: ...
def render_markdown(document: Mapping[str, object]) -> str: ...
```

构造 `ReportWriter(output_dir, metadata)` 会立即建立并写入 `running` skeleton；`checkpoint(document)` 将同一份安全化 document 原子投影为：

- `<output_dir>/report.json`
- `<output_dir>/report.md`

`output_dir` 必须由调用方显式提供，拒绝 URL 形式，不隐式使用当前目录。`finish(status, errors=...)` 设置结束时间后复用同一 checkpoint。

## 初始 schema

```json
{
  "schema_version": "agent-evaluation-report-v1",
  "status": "running",
  "started_at": "<UTC ISO-8601>",
  "finished_at": null,
  "metadata": {},
  "items": [],
  "errors": [],
  "summary": {
    "scored": 0,
    "skipped": 0,
    "unavailable": 0,
    "written": 0,
    "verified": 0,
    "failed": 0,
    "no_prior_context": 0
  },
  "human_agree_rate": null,
  "constructed_gold_only": true,
  "constructed_gold_note": "Task-03 gold is constructed gold only; human annotation was not run."
}
```

`human_agree_rate` 被固定为 `null`，防止自动判官结果或 Task03 构造 gold 被误报为人工达标。

## 安全与持久化契约

- JSON/Markdown 都从同一个清洗后的 document 生成；先写同目录临时文件、flush/fsync，再 `os.replace`，写盘异常抛 `ReportWriteError`，不返回假成功。
- 构造函数先写 skeleton，runner 可在每条 item 后调用 `checkpoint`，坏输入或中途异常仍有可复核产物。
- 默认移除 trace 原文、input/output、question/answer、prior context、prompt/messages、raw、comment、hidden reasoning/analysis 及 credentials；保留经清洗的安全 judge `reason` 或 `explanation` 作为可审计理由。
- 异常摘要截断并遮蔽 URL userinfo、authorization/API key/password/secret 等值；Markdown 使用 HTML 转义的 `<code>` 内容，不把可控文本当 Markdown。
- 报告只保存 trace ID、score ID、状态、真实 judge model、score、verified 和错误摘要等交接所需字段，不保存 q/a 或原始判官输出。

## 后续 runner 调用示例

```python
from pathlib import Path

from eval_042.report import ReportWriter

writer = ReportWriter(
    Path("/absolute/local/eval-report"),
    metadata={"task": "chat_quality", "judge_model": "qwen3.5:9b"},
)
document = writer.document
document["items"].append(
    {
        "trace_id": "trace-id",
        "status": "scored",
        "judge_model": "qwen3.5:9b",
        "score": 1.0,
        "score_id": "score-id",
        "verified": True,
    }
)
document["summary"].update({"scored": 1, "written": 1, "verified": 1})
writer.checkpoint(document)
writer.finish("completed")
```

runner 若失败，应把安全化错误摘要追加到 `document["errors"]`，调用 `writer.finish("failed", errors=...)`，再将非零退出码交给 CLI；报告模块本身不发起 API 请求、不决定业务状态。

## 验证记录

```text
python -m py_compile backend/eval_042/report.py
退出码 0

临时目录 smoke（无真实 API）：通过
- 构造即生成 report.json/report.md
- finish("completed") 写入 finished_at 与终态
- trace_id/score_id/model/score/verified 保留
- input/output/raw/comment 与 URL auth 不落盘
- human_agree_rate=null、constructed_gold_only=true
```

未运行全量仓库 pytest、未调用 Langfuse/Ollama、未编造运行时或人工一致率结论；测试覆盖由独立 04-E `backend-tester` 子任务负责。

## backend-dev 修复记录（2026-10-23）

- 先复现：`/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/evaluation/test_evaluation_report.py -q`，退出码 `1`，`12 passed, 2 failed`。失败点为嵌套 `proxyURL`/`auth`/`key` 未被移除，以及安全 judge 理由被全部清除。
- 修复范围：仅修改 `backend/eval_042/report.py`。递归清洗新增 `q`/`a`、proxy/auth/key、header 容器及 hidden-reasoning 变体的字段过滤；保留的文本遮蔽任意 URL scheme 的 userinfo 和敏感 header 值；安全短 `reason`/`explanation` 保留并在 Markdown 以 `Judge rationale` 展示。`ReportWriter` 接口、写盘流程和运行时服务未改动。
- 修复验证：`/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/evaluation/test_evaluation_report.py -q`，退出码 `0`，`14 passed in 0.19s`；`/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/evaluation -q`，退出码 `0`，`90 passed in 0.27s`；`/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/eval_042/report.py`，退出码 `0`。
- 领域测试文件为 `test_agent_evaluation.py`、`test_evaluation_report.py`、`test_memory_probe.py`、`test_offline_transport.py`；未发现需另行注明的新增 runner 测试失败。未调用真实 API、Langfuse、Ollama 或写入 score。
- 本记录是 backend-dev 修复交接，不是独立评审；请原 `backend-tester` 按交接内容独立复验。

## backend-dev 集成 P1 修复记录（2026-10-23）

本次只修改 [`backend/eval_042/report.py`](../../../../backend/eval_042/report.py)，修复 `task-04-integration-review.md` 指定的两组 report P1；未修改 runner、测试、服务或数据库。

- **人工/gold 声明旁路**：递归清洗会移除 `human_agree_rate`、`human_agree_rate_note`、`constructed_gold`、`constructed_gold_only`、`constructed_gold_note`、`gold_only`、`gold_note` 等审计声明字段；顶层仍规范为 `human_agree_rate=null`、`constructed_gold_only=true` 与固定未人工标注说明，嵌套 metadata 不能覆盖或伪造结论。
- **双文件失败回滚**：JSON/Markdown 临时文件均完成后才发布；第二次发布失败时恢复已替换目标的上一份快照并抛出 `ReportWriteError`，不声称存在跨文件原子事务。补偿本身失败时错误明确包含 `rollback incomplete`，不会更新内存 document 为成功。
- **审计字段 Markdown 投影**：保留 JSON 模型不变，并在 item 表投影 `requested`、`expected_value`、`post_status`（兼容 `post`/`written`）与 `verified_value`，连同既有 `verified` 可读核对。

### 修复前复现

- 无网络 metadata fake：`metadata` 仍出现 `human_agree_rate=0.99`、`constructed_gold_only=false` 与错误人工 note。
- 无网络第二次 `os.replace` fake：抛 `ReportWriteError`，但 `report.json` 含 `new-trace`、`report.md` 不含，旧 JSON/Markdown 不一致；审计字段也未出现在 Markdown。

### 修复后验证

```text
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/evaluation/test_evaluation_report.py -q
退出码 0；16 passed in 0.22s（最终收紧声明键后复验为 16 passed in 0.20s）

/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/eval_042/report.py
退出码 0

无网络内联 fake smoke
退出码 0；嵌套人工/gold 声明已清除，审计列已投影，回滚失败返回 ReportWriteError 且包含 rollback incomplete。
```

未调用真实 API、Langfuse、Ollama，未写 score 或数据库。本节是 backend-dev 修复记录，不是独立 reviewer 结论；交由独立 tester 复验后再更新门禁结论。
