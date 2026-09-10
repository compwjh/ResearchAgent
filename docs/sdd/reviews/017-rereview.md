# Spec017 复审（rereview）：后端限界上下文彻底重构

- **复审者**：架构师（Architect，评审总控）
- **评审对象**：`docs/sdd/specs/017-backend-bounded-context-modularization.md`（修订版，提交 `a804cac`）+ `docs/sdd/plans/017/`
- **复审时间**：2026-09-06（Asia/Shanghai）
- **前置打回**：`017-requirement-review.md`（4 项必改）、`017-tech-review.md`（7 项必改）
- **复审方式**：只读评审；对 spec 文字逐条比对，并以 `routes.py` / `article_settings.py` / `paper_import.py` 真实代码做 4 项抽查，未做任何写操作（git 状态未受影响，最后提交仍为 `a804cac`）。

## 结论：通过（附 1 项低级修正 + 2 项任务门禁复述）

11 项必改在 spec 修订版中均已落地为可核验的契约/矩阵/清单/规则，且 4 项代码抽查全部与 spec 文字吻合（非空话）。唯一实质瑕疵是 R3 验收场景 1（`/health` 失败场景）的描述与真实代码不符，需修正以免误导实现方；该项不阻塞 spec 进入用户确认。

> 一句话：此前的「打回」根因（隐式耦合、跨域端口未定、设置整文件覆盖缺陷、契约基线缺失）已在 spec 中系统性消除，可以进入用户确认。

## 代码事实抽查（判定纪律，禁止只读文字）

| 抽查项 | spec 声称 | 代码事实 | 结论 |
|---|---|---|---|
| 端点数量 | 35 个操作 | `routes.py` `@router.*` 装饰器 = **35**（grep 实测） | ✅ 完全一致 |
| 公开别名 | 4 组保留 | `/papers/imports`、`/imports/{batch_id}`、`/imports/{batch_id}/retry`、`/browser-health` 均在 routes（行 807/821/834/964） | ✅ 一致 |
| SSE | 3 处 | 行 1135(`agent/run`)/1349(`chat`)/1580(`kb/ask`)，均 `text/event-stream` + `no-cache` + `X-Accel-Buffering:no` | ✅ 一致 |
| 两类错误体 | `/papers/*` 用 `{code,message,retryable}`；其余用 `{"detail"}` | `_paper_api_error` 37 处（/papers 区段）；`HTTPException` 37 处（其余）；`/agent/articles/download` 404 行1195 返回 `{"download_outcome","user_message","article_url"}` | ✅ 一致 |
| article_settings 四级优先级 | 文件优先→JSON 兜底→环境变量→`PAPER_DISCOVERY_*` 始终覆盖 | `load_article_settings()` 94-123 行逐字吻合；`save` 126-128 为 `model_dump_json` 整文件覆盖（确为缺陷） | ✅ 一致 |
| paper_import→KB 直连 | 直接 import `services.kb.{index,store,tasks}` | `paper_import.py` 行 37/38/49 实测 import 三处 | ✅ 一致（T2 依据成立） |
| 旧目录文件数 | services 24 / kb 11 / domain 5 / agents 2 / graphs 2 | 实测 24 / 11 / 5 / 2 / 2（含各自 `__init__.py`） | ✅ 完全一致 |
| 错误码 vs 环境变量 | `PAPER_DISCOVERY_DISABLED` 等为错误码非变量 | `article_settings.py` env 仅 8 个 `PAPER_DISCOVERY_*` 配置项，无上述错误码 | ✅ 一致 |

## 11 项逐项判定

### 需求评审 4 项

| 编号 | 判定 | 证据（文件:行） |
|---|---|---|
| **R1** 完整 OpenAPI 契约基线 | **已闭环** | spec 54-116：冻结基线、7 条判定规则（路径/方法/参数/字段/状态码/错误体/SSE 介质）、35 端点表带「别名」标注、声明保留全部公开别名、「不保留兼容层仅适用 Python import」。与 routes.py 实测 35 端点/4 别名/3 SSE 一致。 |
| **R2** 环境与数据兼容矩阵 | **已闭环** | spec 118-160：变量清单+归属+默认值、四级优先级（139-144，与代码逐字一致）、拆分读写映射+未知 key 保留+原子写、4 个冲突验收样例（153-160），并点名 `save_article_settings` 整文件覆盖缺陷（151，与代码 126-128 一致）。 |
| **R3** 产品步骤+可执行验收场景 | **部分闭环（1 处低级不准确，需修正）** | spec 283-316：13 项验收场景，每项含成功可观察结果+失败错误码/错误体，覆盖健康/设置读写/任务/登录恢复/会议启停/检索/批量导入重试/浏览器恢复/KB 上传-轮询-重建-删除/SSE 问答/聊天。唯一瑕疵：**场景 1（`/health`）失败场景描述写「返回 `{"detail"}` 结构」，但真实代码 `routes.py:280-291` 在 Ollama 不可达时 `except httpx.HTTPError: models=[]` 仍返回 200 dict，不存在 `{"detail"}`**。该描述会误导实现方为 `/health` 强加 detail 结构，违反「与迁移前一致」。 |
| **R4** 旧目录清理判定边界 | **已闭环** | spec 169-230：`services/`(24)+`services/kb/`(11)+顶层 `domain/`(5)+`agents/`(2)+`graphs/`(2) 逐文件迁移分类（移动/删除/目标），数量与实测完全吻合；import 检查范围 4 类（源码/测试 monkeypatch/脚本 deploy/动态 import 字符串）+ 判定命令 + 白名单例外 + 「待裁决」兜底。 |

### 技术评审 7 项

| 编号 | 判定 | 证据（文件:行） |
|---|---|---|
| **T1** 依赖规则与端口形态固定且机械可检 | **已闭环** | spec 32-40：五层依赖允许/禁止表 + Protocol 构造函数注入 + 「platform 不得 import 业务模块」红线。允许/禁止以表格给出，可机械判定；配合 T6 architecture test 可检。 |
| **T2** 论文导入→KB 端口契约与任务顺序 | **已闭环** | spec 234-246：端口输入（候选快照+受信任本地 PDF，禁止传 URL 给 KB 自下载）/输出（稳定 paper_id、索引状态、错误码，不暴露 Qdrant/store/task）/幂等/v1-v2 语义；硬顺序 `03 定义 → 05 实现 → 04 消费`，04 不得早于 05。依据代码 `paper_import.py:37/38/49` 成立。 |
| **T3** 设置拆分前置到 Task03+持久化矩阵 | **已闭环** | spec 248-250 + task-03(16)：`ArticleAssistantSettings`/`PaperDiscoverySettings`/唯一 settings repository 归 Task03 前置，供 04/06 消费；read-modify-write 保留另一域+未知 key+原子写；04/06 不得并行移动同一 repository/数据文件。 |
| **T4** API composition-root 契约补全 | **已闭环** | spec 252-259 + task-03(18)：子路由模块清单/端点归属/前缀保持/schema 归属/生命周期 hook/统一 factory（建议 `platform.bootstrap`）/FastAPI dependency 测试替换点，明确消除 routes.py 模块级单例。 |
| **T5** 全量迁移清单为硬门禁 | **已闭环（spec 层；实产物待 Task02 落盘）** | spec 341 + task-02(20-32)：每行 文件→目标→任务→删除时机；涵盖 .py 实现/测试 patch 点与 monkeypatch 字符串（点名 `tests/test_api_routes_coverage.py`）/脚本/observability/core 两文件/kb facade 全部消费者/动态 import；同一文件只归一个任务；未覆盖=待裁决。门禁明确「未完成不得启动 Task03」。**实产物由 Task02 交付，属任务产出而非 spec 缺陷。** |
| **T6** 静态边界检查机械规则+允许表 | **已闭环（spec 层；脚本待 Task07 落盘）** | spec 261-274 + task-07(13)：6 行禁止/允许表（api 禁 infra、domain 禁外部副作用、业务循环、platform 反向、跨上下文 domain/infra、application protocol/DTO 允许）；明确要求「可执行 architecture test」而非文字承诺。**具体检查脚本/命令由 Task07 交付。** |
| **T7** 外部契约基线比较方式 | **已闭环** | spec 112-116 + task-02(31)：Task02 冻结 `GET /openapi.json`，剔除不稳定字段（server url/openapi 版本/含时间戳描述）+ 记录 FastAPI/Pydantic 版本；Task07 比较 path/method/schema/状态码/错误体；明确「内部模块名/operationId 变化不算不兼容，除非前端实际依赖」。 |

## 新发现问题

| 严重级别 | 位置 | 问题 | 修复方向 |
|---|---|---|---|
| 低 | spec 场景 1，`017-*.md:302` | `/health` 失败场景写成「状态码与 `{"detail": ...}` 结构与迁移前一致」，但 `routes.py:280-291` 实测 Ollama 不可达时仍返回 200 且 `models=[]`，无 `{"detail"}`。描述与迁移前行为不符，可能诱导实现方在 `/health` 强加 detail。 | 改为「Ollama 不可达时仍 200、`models` 为空，其余字段与迁移前一致；不引入新错误体」，与 R1「保持不变」对齐。 |
| 提示 | task-02/07 | T5 全量清单、T6 architecture test 的**实产物**尚未生成（属预期，Task02/07 才交付）。需确保进入实现时这两项真正落盘并跑绿，否则 R4/T1/T5/T6 的「可检」不成立。 | 在 Task02 交付物中落盘逐项清单；Task07 落盘 architecture test 并在 CI 跑通；架构师在 Task07 阶段复核。 |

## 进入用户确认门禁前还必须做的事

1. **修正 R3 场景 1（`/health`）失败描述**：把 `{"detail"}` 改为「200 + 空 models、无新错误体」，以对齐真实行为（低级，10 分钟）。
2. **确认实产物交付门禁**：`017-acceptance-review.md` 标注「未执行」。Task02 全量迁移清单（T5）、Task07 architecture test（T6）须真正落盘并通过，作为进入业务迁移的硬门禁。
3. 完成上述 1 后，本 Spec 可进入用户确认；确认前不得进入业务代码迁移（仍受 spec「明确不做」与任务序 `02→03→05→04→06→07→08` 约束）。

## 复审判定汇总

- **R1 已闭环 / R2 已闭环 / R3 部分闭环（1 处低级修正）/ R4 已闭环**
- **T1～T7 全部已闭环**（T5/T6 实产物为对应任务交付物，spec 与门禁要求已到位）
- **总体：通过（附 1 项低级修正）**。

## 建议

**建议将 Spec017 提交用户确认**，并附带：(a) 修正 `017-*.md:302` 的 `/health` 失败场景描述；(b) 在 Task02/Task07 交付时落实全量迁移清单与 architecture test 实产物并跑绿。两项完成后即可解除「待确认」。
