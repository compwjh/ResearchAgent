# Task 05 — AI 分析与会话

> 关联：[Spec043](../../specs/043-literature-map-topic-exploration.md) ｜ 索引：[README](./README.md)  
> 依赖：04；被依赖：07；当前状态：**进行中（API 摘要/全文链路真实 PASS；移动真实验收仍待 390/桌面 live 复验）**。

## 一句话目标

对选中论文提供有依据标识的主动总结与问答，不把摘要分析伪装成全文阅读。

## 当前证据与前置条件

- Task03/04真实阶段门禁已通过且保留provider限制。本Task早期候选 `b94717c` 的摘要分析、摘要会话和前端 Chrome smoke 成功；全文 `409 MAP_FULLTEXT_UNAVAILABLE`、`dd616d5` scoped v1 恢复仍被 gate 阻塞、续跑服务不可达等历史证据均保留于 [`api-e2e.md`](artifacts/task-05/api-e2e.md) 及其 run 目录。后续候选 `82c816f` 已真实通过摘要保留、全文来源门禁、全文分析/幂等、全文会话/幂等和全文 QA/SSE；本 Task API 证据现为 PASS，但尚未 Task05 阶段验收签字，不运行 Spec 全量、不 push。
- Spec018 修复集成记录已同步到 [`runtime-e2e.md`](../018/artifacts/2026-10-21-pdf-safety-repair/runtime-e2e.md)：单文档来源安全状态与全文集成 PASS；这不改变 Spec043 仍处于实施中的状态。Task07 最新 375px 详情滚动窄复验已 PASS，390px/桌面完整 live 仍待完成；最终全量回归和最终验收尚未执行。
- 复用代码位置是调研入口，未来实现时需对照实际提交核实，不复制过期实现。后续新增模块/前端文件按前置Task固定报告定位，不猜文件名。
- Spec处于待确认时禁止实现。需求/技术门禁通过及用户明确确认后，先核对工作区/实现分支，保护Spec032暂停快照及其他任务修改。
- 前置Task真实通过后才能执行；若预生成接口尚未冻结，应标阻塞而非自行发明第二套合同。

## 最小上下文

- `docs/sdd/specs/043-literature-map-topic-exploration.md（本Task有关章节）`
- `docs/sdd/plans/043/README.md`
- `backend/app/literature_maps/`
- `backend/app/api/routes_conversations.py`
- `backend/app/api/routes_kb.py`
- `frontend/ 地图组件与既有会话组件（读Task03/04报告定位）`

## 数据、配置与接口增量

- 以Spec数据模型和端点章节为边界；只扩展本Task所需行为，不重定义Task03已冻结身份/事件/迁移合同。
- 地图范围最多200节点；首批默认30可20/50，扩展apply每批最多20。任何测试样例不得暗中改阈值或范围。
- 后端与前端交接固定输入输出、错误码和可观察状态，类型/版本变化先更新接口交接。

## 实施步骤与文件边界

1. 新增MapAnalysis版本和来源绑定，沿用既有模型provider/作业/能力接口；点击触发，记录等待/成功/失败，不在打开详情时自动调用模型。
2. 没有可用索引的全文仅提供摘要级，只有标题且无摘要不生成冒充论文内容的总结；提示获取摘要或导入原文。
3. 全文分析核对真实document/index可用与owner allowlist，复用既有RAG，不把导入metadata等同全文。结果标注source_version/evidence_level。
4. 摘要级旧结果不可静默覆盖；全文就绪只提示可重新分析，用户点击创建新结果，保留旧结果。
5. 从地图打开论文会话：创建/复用map/node对应且project一致的既有conversation；新会话继承当前project，未绑定不使用项目记忆；地图后来解绑不改旧会话。
6. 前端右侧AI面板显示依据和异步状态，问答跳转现有会话页面并携带正确论文上下文，不新建聊天UI框架。
7. 定向验证后真实摘要级和全文级各跑一次请求及会话绑定smoke，保存脱敏证据不保留隐藏推理。

允许范围：地图analysis窄应用适配与既有会话/RAG的明确上下文桥接，前端右侧详情。不得重写对话/记忆系统或恢复032报告生成。

## 子任务拆分与分派

1. backend-dev：只承担本端/本角色步骤，使用上述最小上下文；当前模型从角色配置读取，实际调用遵循当次用户覆盖，不在本Task固化临时型号。
2. frontend-dev：只承担本端/本角色步骤，使用上述最小上下文；当前模型从角色配置读取，实际调用遵循当次用户覆盖，不在本Task固化临时型号。
- 后端完成后由独立 backend-reviewer 复核，backend-tester 运行后端精准验证。
- 前端完成后由独立 frontend-reviewer 复核，frontend-tester 做DOM/版本/XSS/交互契约与浏览器核对；不因前端单端改动运行后端全量。
- 主会话负责依赖接续与裁决；长报告落盘读回，不以口头“改好了”直接接部署。日志按spec/task/角色分层。

## 可直接使用的分派 Prompt

### backend-dev

```text
角色：backend-dev。模型按本次主会话明确分派；不修改长期配置。Spec043 Task05：AI 分析与会话。
目标：对选中论文提供有依据标识的主动总结与问答，不把摘要分析伪装成全文阅读。
只读取本Task、关联Spec有关章节、前置任务固定交接报告，以及“最小上下文”列出的本端必要文件。角色技能按项目绑定加载，不全仓扫描；前端不要读取后端实现，后端不要扫描前端vendor。
允许范围：backend/** 与 tests/literature_maps/（必要时既有受影响后端领域测试）；不得修改frontend/**。报告例外写本Task artifacts 下固定报告，进展日志写 .codebuddy/agent-logs/spec-043/task-05/backend-dev/。
执行本Task实施步骤中属于本角色的部分；跨端公开契约只以已冻结文档为准，缺失或冲突先报告主会话，不自行猜测。
禁止：未确认就实现、扩大Spec、重写下载/embedding/chat框架、读取或输出.env凭据、保存隐藏推理、篡改旧研究任务、清空数据库、覆盖用户修改、自动push/合并main、伪造验证或提前宣称部署。
完成后可观察状态：本Task验收标准属于本端的条目达到，并明确尚未由真实API/浏览器验证的部分。
验证：运行本Task“验证命令”中属于本端的精确命令，补充实际改动文件ruff/语法或前端静态检查；除Task08最终收口外不跑全量。
返回并落盘：结果状态/摘要；改动文件；命令、退出码、通过数；产物路径；决策依据；风险与阻塞；主会话下一动作；开始/结束/耗时；可取得时记录模型/token/工具次数，不编造缺失指标。
```

### frontend-dev

```text
角色：frontend-dev。模型按本次主会话明确分派；不修改长期配置。Spec043 Task05：AI 分析与会话。
目标：对选中论文提供有依据标识的主动总结与问答，不把摘要分析伪装成全文阅读。
只读取本Task、关联Spec有关章节、前置任务固定交接报告，以及“最小上下文”列出的本端必要文件。角色技能按项目绑定加载，不全仓扫描；前端不要读取后端实现，后端不要扫描前端vendor。
允许范围：frontend/** 与本Task对应的前端契约测试；不得修改backend/**。报告例外写本Task artifacts 下固定报告，进展日志写 .codebuddy/agent-logs/spec-043/task-05/frontend-dev/。
执行本Task实施步骤中属于本角色的部分；跨端公开契约只以已冻结文档为准，缺失或冲突先报告主会话，不自行猜测。
禁止：未确认就实现、扩大Spec、重写下载/embedding/chat框架、读取或输出.env凭据、保存隐藏推理、篡改旧研究任务、清空数据库、覆盖用户修改、自动push/合并main、伪造验证或提前宣称部署。
完成后可观察状态：本Task验收标准属于本端的条目达到，并明确尚未由真实API/浏览器验证的部分。
验证：运行本Task“验证命令”中属于本端的精确命令，补充实际改动文件ruff/语法或前端静态检查；除Task08最终收口外不跑全量。
返回并落盘：结果状态/摘要；改动文件；命令、退出码、通过数；产物路径；决策依据；风险与阻塞；主会话下一动作；开始/结束/耗时；可取得时记录模型/token/工具次数，不编造缺失指标。
```

## 返回后的主会话校验

1. 读取实际diff与固定报告，确认修改范围/引用/产物存在，无占位实现或 unrelated 覆盖。
2. 核对测试命令、退出码、数量及真实/合成/只读重放证据类别；不得把定向测试当真实E2E。
3. 对照Spec逐条核实身份/来源/关系方向/删除边界/密钥脱敏及本Task停止条件。
4. 组织对应端独立复审与集中修复；通过后接依赖Task或部署里程碑，未通过写清阻塞。
5. 同步Task、README和Spec任务索引实际状态；状态变化写统一台账，不能提前填完成。

## 实时监控

- 正常线上子Agent等待其主动回传，不常态轮询日志；具体角色日志位于上文路径。
- 只有用户要求/明确异常才读取一次对应日志定位。
- 实现后通过地图job与events接口观察实际阶段/计数/failed_units；目前接口未实现，不声称可调用。
- 可用只读核对：`git status --short`、`git diff --check`。不得并发启动多个使用同一存储的未评审服务。

## 验证命令与验收

下列新测试路径为本Task计划创建的能力命名测试，不表示文件已存在或已执行；实施时先补红灯测试并落盘真实命令结果。
- `.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_evidence.py tests/literature_maps/test_map_conversation_binding.py`
- `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_analysis_contract.py`

- 摘要/全文有明确依据，缺摘要不编造；全文无索引不宣称可全文分析。
- 旧分析/旧会话保留，跨项目/owner/doc错误拒绝，未绑定不漏用项目记忆。
- 真实分析处理提示和失败恢复可操作，模型不可用不阻塞原地图浏览。
- 测试文件/函数名不含spec/task数字，源码归领域子目录；全量回归只在Task08最终候选。
- 本Task结果不足时标明“不通过/阻塞”，不得记录为“已完成”。

## 风险、停止条件与回滚

正文/记忆越界或结果依据错误是阻塞；不得通过通用总结兜底掩盖证据缺失。
- 保留用户数据和已完成结果；迁移前备份，回滚禁用新增入口/作业，不删共享目录/KB/旧报告，不reset/stash/clean覆盖修改。
- 真实外部API限流/权限失败保留脱敏证据，说明具体下一步，不绕过访问控制。
- Spec范围或公开接口发生实质变化先回架构师/用户确认，不靠实现者自由设计补齐。

## 产出物

- `artifacts/task-05/backend-report.md`（待执行后生成）
- `artifacts/task-05/frontend-report.md`（待执行后生成）
- `artifacts/task-05/analysis-e2e-evidence.json`（待执行后生成）
- 代码/测试/评审与本Task交付应可追溯到同一候选提交；上述固定文件追加修复记录，不重复建多轮报告。
- artifacts路径均相对 `docs/sdd/plans/043/`。目前未产生，不预造结果或真实数据。

## 执行结果

2026-10-20 03:32 +08:00：Task04阶段门禁通过后开始只读复用核实。本Task迁移前已对包含最新刷新结果的地图SQLite生成一致性备份 `data/literature_maps/backups/literature-maps-20261020T0332-task04-passed.sqlite3`；SQLite `.backup` 和备份 `PRAGMA integrity_check` 退出0、结果ok。未将运行数据提交Git；本Task代码尚未开始。

随后复用接缝核实完成，主会话冻结公开JSON/证据/跨库绑定合同，并将前后端分别交由独立开发Agent实现。当前服务暂止以防未复审静态资源暴露；未宣称本Task完成。

### 2026-10-21 最新真实 API 验收与 Spec018 修复集成

候选 `82c816f` 的真实 HTTP 运行已补齐此前缺失的全文链路；完整脱敏证据见 [`api-e2e.md`](artifacts/task-05/api-e2e.md) 末尾及 [`api-e2e.json`](artifacts/task-05/runs/20261021-172344-82c816f-full/api-e2e.json)。Spec018 修复链路的交接说明见 [`runtime-e2e.md`](../018/artifacts/2026-10-21-pdf-safety-repair/runtime-e2e.md)。此前 `b94717c` 全文 409、`dd616d5` source gate BLOCKED 及服务不可达 continuation 记录均未删除或覆盖。

- `/api/ready` 与 `/api/health` 均 HTTP 200，ready=true，模型为 `qwen3.8:27b`；目标 map/node/document ID 与既有验收一致。
- `/api/kb/papers` 的目标 source/index hash 相等、`source_hash_state=verified`，v1 为 `indexed`/100；analyses GET 返回 `fulltext_ready=true`、`available_evidence_levels=["abstract", "full"]`，全文 source version 为 `a253fa60f4d0444592fd52f89e23016e8d437f01335f300b176d610eeefa644c`。
- 既有摘要分析 version 1（analysis `7c63cba835c044859c571dbc87f6a48a`，summary 490 字符）保留。全文分析 POST HTTP 202，analysis `3bb20a9a794d4104b13fc1fe5f581c66`、job `1655a96b6f054c66931260204caaefa4`、version 2，终态 completed、summary 627 字符；source refs 1 条、5 个 citations 均仅指向目标 document。相同幂等请求复用同一 analysis/job/version/source version。
- 全文会话 POST HTTP 200，conversation `cc9f02f3d8184943bee35b4a23aa9481`，evidence_level=full；重放返回 created=false 且 conversation/source version 不变。消息 SSE HTTP 200、`text/event-stream`，718 个事件严格 seq 1..718（meta 1、progress 7、token 708、sources 1、done 1），done=completed；sources 的 5 条引用均为目标 document，随后 messages GET 的 user/assistant 均 completed，assistant 非空（1473 字符）。
- 全文分析与会话前后 graph 均为 revision 17、partial、21 nodes/18 edges；目标节点位置、group ID、布局/分组哈希保持不变。

本节裁决：**PASS（Task05 backend/API 摘要与全文链路）**。这只确认当前候选的真实 API 集成证据，不是 Task05 总体验收签字，也不是 Spec043 完成。Task07 最新真实 375×820 详情触控窄复验已记录 `scrollTop` 0→75→175；此前零间隔触控得到的 P1/BLOCK 属于时序假阴性，历史诊断证据仍保留。390px/桌面完整 live 仍待执行，最终全量回归、Task08 最终验收和部署收口均未执行。

## 变更日志

- 2026-10-19：主会话依据已确认讨论纯文档代行建档，非独立评审；Task保持待执行，未改业务代码。
