# Spec 状态变更记录

## 2026-10-23

- **Spec042 Task04**：`本地领域124项通过` → `集成复审打回，同范围集中修复`。独立runner/report复审发现审计字段、来源异常脱敏、嵌套人工真值声明及双报告替换失败一致性四组P1；已分别分派runner/report修复与独立红绿测试。暂停真实score回写，Spec保持实施中；Spec043现有8000服务无改动。

- **Spec042 Task04**：`续作审查` → `分组实现与精确验证`。需求/技术独立评审通过后分派04-A/B/D；统一离线传输和上下文数据契约已实现，新44项与原28项合计72项领域测试通过，独立复审中。报告模块完成实现，运行器接续；Langfuse使用既有组件恢复且仅loopback监听，无安装/迁移/真实trace读取或score写回。尚未完成Task/Spec验收，不跑全量、不push或合main。

- **Spec042 OpenEval接入：本地离线Agent评测闭环**：`已确认/Task02、03已完成` → `实施中（续作）`。用户明确要求继续；核对历史可行性与记忆探针资产，先独立审查正式运行入口、JSON/Markdown报告、离线及错误退出合同，沿原已确认范围补齐，不新增业务API或在线评测。独立分支codex/spec042-offline-evaluation，不push或合main。

## 2026-10-22

- **Spec043 交互式文献地图与自动主题探索**：`实施中` → `已完成`。最终候选a328932完整回归退出0（3224 passed/0 failed/2合法skip/67 subtests/5 warnings），真实建图与扩展、stop/restart、全文问答、PNG/JSON、桌面/手机视口及当前部署均有证据；独立tester与architect签READY_FOR_USER，准备度10/10。服务8000，文档与复盘同步，仅本地提交，不push或合main。
- **Spec018 知识文档切片检查器**：`实施中（同范围修复）` → `已完成（追加修复验收）`。仅关闭用户授权的PDF安全分类/发布接缝修复，保留2026-10-06历史验收；真实全文链路、最终全量及独立双签通过，不外推为所有历史版本完成。

- **Spec043 Task08**：`最终候选待部署` → `a328932已部署并通过真实接口smoke，最终全量进行中`。旧PID29261确认退出后启动PID55445/8000，ready与资源版本均正确；真实全文消息以completed结束且仅引用目标文档。最终完整回归、当前页面复核和独立验收尚待完成，Spec维持实施中，不push或合main。

- **Spec043 Task08 / Spec018 同范围修复**：`首轮全量BLOCK` → `定向修复与独立复审通过，等待最终全量重跑`。API分层及真实绑定门面18项精准测试通过，独立复审GO，本地8b0cde1；KB canonical夹具75项通过，冻结清单经入口/纯helper分类、双向refs、路径及八文件指纹核验后架构签为verified，本地5f883d3。压缩阈值失败定位为测试期间异步记忆写入竞态，仅隔离测试副作用，生产阈值不改。Spec043/018均未标完成，服务仍为已验证1a3ff26，未push或合main。

## 2026-10-21

- **Spec043 Task05/Task07/Task08**：Task05、Task07 `阶段验证中` → `阶段已完成（PASS_WITH_LIMITATIONS）`，Task08 `API BLOCK` → `核心真实API恢复PASS、最终回归/补验中`。1a3ff26真实375/390/桌面交互通过；原限流job受控恢复后取得20节点11引用5相似，确认扩展后21节点17边，幂等/CAS/项目与删除隔离通过。阶段架构签字见Task07 acceptance-report；保留partial外部限制和历史失败。开始最终隔离全量及重启补验，Spec仍实施中，未push。

- **Spec043 Task07/Task08**：Task07 `独立复审GO` → `真实全局导航关闭阻塞、继续同范围修复`；Task08 `待执行` → `验证实施中（API BLOCK，未全量）`。候选134dce4真实375px地图列表关闭通过，但导航打开后的close仍被toggle拦截；fresh map创建被S2外部429限流，0节点，不计成功。已核实配置密钥存在与有限退避，保留失败证据、暂停8000；准备原job的一次受控恢复，不改频率、不伪造数据、不推送。

- **Spec043 Task05/Task07**：Task05 `全文来源阻塞` → `摘要/全文真实API PASS，待最终验收`；Task07 `真实界面验证` → `同范围手机导航遮挡修复`。候选82c816f通过全文分析、幂等、全文问答及单文档引用；375px滚动旧失败经持续触控证明为测试时序误报，但正常点击详情关闭按钮确被全局导航遮挡，已暂停8000并分派最小前端修复。Spec仍实施中，未启动全量、未push或合main。主会话纯文档同步，非验收签字。

- **Spec018 知识文档切片检查器**：`已完成（历史）` → `实施中（同范围PDF安全分类/发布状态修复）`。用户明确授权解除Spec043全文验收的既有KB流程阻塞；先被动诊断实际触发对象，再精确分类及同步真实manifest/目录状态，危险或未知特征仍fail-closed，不放宽全文门禁、不全库重建。历史验收不覆盖。

- **Spec043 Task06/Task07**：Task06 `实施中` → `阶段已完成（PASS）`；Task07 `待执行` → `手机适配实施中`。独立双端复审、真实27请求及浏览器PNG/JSON导出通过，阶段架构签字已记录；Task05界面/摘要可用但全文KB partial阻塞独立保留。手机适配不放宽其门禁，Spec未完成，不跑全量、不push。

- **Spec043 Task06 整理与导出**：`待执行` → `合同冻结、分端实现`。依赖Task04已阶段通过，按原计划独立推进；Task05全文因真实KB manifest `partial/HOSTILE_FEATURES_NOT_EXECUTED`仍阻塞，不放宽门禁、不扩大KB修复范围。已冻结分组/CAS/JSON/PNG合同，开发前暂停8000，后续复审通过再部署。

- **Spec043 Task05 AI分析与会话**：`独立复审` → `已部署、真实全文验收阻塞`。双端复审GO，本地候选b94717c启动8000且ready=true；真实摘要分析/幂等/会话问答和Chrome smoke成功。全文因验收文档缺v1可信manifest返回409，v2partial不可替代；保留失败证据，使用既有单文档v1重建API作一次有界恢复，不改门禁或全KB重建。

- **Spec043 交互式文献地图与自动主题探索**：`暂停（主会话，在途子代理继续）` → `实施中（Task05修复独立复审）`。用户明确要求继续；后端六项修复已交接，正在独立窄复审，前端GO和生命周期结果保留。8000未启动，真实模型/API验收尚未执行，不push或合main。

## 2026-10-20

- **Spec043 交互式文献地图与自动主题探索**：`实施中（Task05独立评审与修复）` → `暂停（主会话，在途子代理继续）`。用户明确因额度要求暂停，允许尚未完成子代理完成当前任务；后端继续已分派六项P1修复与精准测试，前端独立复审GO、生命周期5项通过。下次先读Task05固定报告并复审后端，再部署和真实API验收；8000保持停止，未push或合main，未宣称Task05完成。

- **Spec043 Task05 AI分析与会话**：`分端实现` → `独立评审与修复，未部署`，18:50 +08:00。前后端实现已交接；前端独立评审发现三项问题并退回集中修复，后端评审额度失败后按原指定模型重试。证据隔离、真实模型/API与浏览器验证尚未通过，保持实施中，不部署未复审候选。

- **Spec043 Task05 AI分析与会话**：`复用核实及合同冻结` → `分端实现`。实际复用合同与精确API/证据版本/会话绑定合同已落盘，前后端已独立分派；采用既有模型和单文档RAG窄桥接。8000测试实例在静态开发前暂停，未部署未复审代码；不变更Spec总体范围，不push。

- **Spec043 交互式文献地图与自动主题探索**：`实施中（Task04）` → `实施中（Task04阶段通过，Task05）`，03:32 +08:00。Task04独立验收PASS_WITH_LIMITATIONS，真实预览/加入/刷新写入/幂等/CAS/墓碑恢复及新浏览器会话重开有据；108项地图域、13项前端及3项可行性测试通过。provider部分失败、UI原幂等key未暴露的边界保留；无全量回归或Spec最终签字。开始Task05实际复用接缝核实，不push、不合main。

## 2026-10-19

- **Spec043 交互式文献地图与自动主题探索**：`实施中（Task03）` → `实施中（Task03阶段通过，Task04）`，2026-10-19 23:00 +08:00。Task03独立阶段验收PASS_WITH_LIMITATIONS，真实图20节点、12引用、5相似，保存重开和默认v1知识库57分块导入有据。引用provider partial、异步v2失败及当前浏览器导入成功态待补证均保留；非Spec最终验收、不推送、不合并main。Task04开始冻结扩展与恢复增量合同。

- **Spec043 交互式文献地图与自动主题探索**：`实施中（Task02）` → `实施中（Task03）`（Asia/Shanghai）。Task02独立复核Go，真实引用与身份/数量边界、embedding可用性及合成200节点620边交互有据；8项精准测试通过。冻结v1合同并开始桌面MVP分端实现，未宣称已部署。

- **Spec043 交互式文献地图与自动主题探索**：`待确认` → `已确认` → `实施中`（Asia/Shanghai）。用户明确要求实现，独立需求/技术评审通过；启动Task02真实API/身份/引用/向量/200节点可行性验证，地图代码尚未实现。项目删除失败关闭与Task03合同先行纳入实施门禁。

- **Spec043 交互式文献地图与自动主题探索**：`新建` → `待确认`（Asia/Shanghai）。用户确认Grilling共同理解与截图布局参考后，按要求仅落盘Spec、README和Task02–08；明确自动有界主题建图、引用/相似分层、项目绑定、AI/导出/手机分阶段及复用边界。主会话纯文档代行，三份独立评审未执行，不包含业务代码、迁移、部署或API调用。

- **Spec032 Research Task 数据源与安全会议扩展**：`实施中` → `暂停，待下次继续`（Asia/Shanghai）。用户切换任务，已验证功能、已写完但独立复审/真实 E2E 未通过的正式报告转换修复及下次验收范围记录于 `docs/sdd/plans/032/RESUME.md`。保留全部失败证据，不标完成，不 push 或合并 main。

## 2026-10-06

- **Spec018 知识文档切片检查器**：`补充验收中` → `已完成`（22:15 +0800）。恢复 marker 与严格 schema 冲突已修复，新 PDF/Markdown 真实 API E2E、2893 项全量测试、独立验收签字及端口 8000 部署检查通过；旧库未验证边界、Langfuse 环境告警与清单预取性能债务如实保留。

- **Spec018 知识文档切片检查器**：`已完成` → `补充验收中`。用户授权完成遗留验收；保留历史 PASS，重新验证整合版本的上传闭环、双格式检查、性能、全量回归与部署，不清空既有知识库。

本文件记录所有 spec 的状态变化。每条含：spec 编号与标题、变更前 → 变更后状态、变更时间，以及一两句话说明本次变动的原因或内容。

> **收口纪律**（见 `docs/sdd/SDD-GATE-CHECKLIST.md` §3）：状态流转须与本文件同步；
> 转 `已完成` 前必须满足——三份评审有真实结论、验收签字栏已填、本文件已追加、变更日志补齐、引用路径真实存在、复盘已落盘。

## 2026-09-17

- **030 跨论文证据矩阵与深度研究报告 — Task06 收口** ｜ 实施中 → 实施中（P1 阻塞） ｜ 2026-09-17：唯一全量回归完成（2495 passed、5 failed、67 subtests、退出码 1），固定矩阵/manifest/三格式/前端安全与浏览器工作台 smoke 通过；真实未知报告请求因 `EvidenceReportError.message` 缺失返回 500（应 404），不得签字或标记 Spec030 已完成，等待业务修复后复验。

## 2026-09-13

- **034 会话式深度研究与真实子 Agent Runtime** ｜ 新建 → 待确认 ｜ 2026-09-13T03:13:41+08:00：经多轮 Grilling 冻结普通会话意图识别、Deep Research Skill 多轮 Intake、计划版本与前端审批、真实 `ResearchAgentRunner` 子 Agent、Registry 授权与资源扩容、论文目录真实接线、`processing_steps` 一至三级树、报告 Artifact/通知/会话写回、Research Tab 复用及旧未绑定 Task 直接清理；Spec 与 Task02–10 已落盘。确认前不修改业务代码。本次研发会话的临时模型选择不写入长期规则、记忆或产品 Runtime。
- **034 会话式深度研究与真实子 Agent Runtime** ｜ 待确认 → 待确认（评审打回/修订中） ｜ 2026-09-13T04:06:27+08:00：需求评审结论 REVISE、技术评审结论 NO-GO；发现产品使用步骤占位、Task/Q 断链、Session/Approval/AgentRun/Artifact/Notification 状态与唯一性、Spec023 Tool 映射、真实目录来源注入及 ProcessingStep v2 投影契约不足。已暂停实现，补齐文档后重新评审。
- **034 会话式深度研究与真实子 Agent Runtime** ｜ 待确认（修订完成） → 已确认、实施中 ｜ 2026-09-13T04:29:00+08:00：第二轮需求评审 APPROVE、技术评审 GO，上一轮 P0/P1 已关闭。用户此前明确要求“然后再开发034”，据此确认 Spec034，启动 Task02；临时研发模型选择不写入规范、产品 Runtime 或长期规则。
- **034 会话式深度研究与真实子 Agent Runtime — Task02** ｜ 待执行 → 实施中 ｜ 2026-09-13T04:30:00+08:00：Spec034 已确认且双评审通过，启动数据模型、状态机、迁移与兼容门禁；业务实现由 Luna high 子 Agent 执行，Task 阶段只跑定向测试。
- **027 Research Task 动态编排 MVP — Task05** ｜ 实施中 → 已完成（固定样本通过；真实 Ollama/外部来源环境延期） ｜ 2026-09-13T03:40:43+08:00：固定真实 `ModelRouter` fast→fast 重试→strong 路由、`MODEL_ESCALATED` 安全事件和真实 Spec015 `CatalogSearchAdapter`/`CatalogSearchGraph` 装配与诚实降级样本通过；真实 Ollama `/api/tags`/`/api/chat` 因当前环境 `Operation not permitted` 阻断，未伪造成功。定向后端回归 95 passed、5 subtests；真实外部 smoke、全量回归、部署和最终 Spec027 验收交 Task06。
- **027 Research Task 动态编排 MVP — Task06/Spec027** ｜ 已确认（Task05 完成） → 已完成（最终回归通过；真实 Ollama chat/USENIX/DBLP 环境延期） ｜ 2026-09-13T03:54:38+08:00：完成复用审计、双端静态/契约核对、固定样本、真实 source/Ollama 探测和部署 smoke；最终全量 pytest 1700 passed、1 skipped、52 subtests，退出码 0。首轮冻结清单 SHA 漂移已按既有惯例修复并定向复验 2 passed；服务在 `127.0.0.1:18081` 完成 health/home/Research Task 入口验证后正常停止。真实 Ollama tags 可达但 chat 超时，USENIX/DBLP 分别不可用/网络错误，均如实记录并保留复验步骤，未伪造成功。

## 2026-09-12

- **024 可见推理过程与会话级推理档位** ｜ 待确认 → 已确认 ｜ 用户明确要求 pull 后继续开发；需求最终复审与技术复审均通过，允许启动 Task02。
- **024 可见推理过程与会话级推理档位** ｜ 已确认 → 实施中 ｜ 完成首条消息、SSE 耗时/终态和 PATCH `updated_at` 合同收紧；启动 Task02 真实 Ollama/临时数据库 Go/No-Go，业务代码暂不修改。
- **024 Task02 运行时协议与迁移验证** ｜ 进行中 → 已完成（条件 GO） ｜ 三模型 provider 探针、临时 SQLite v7 清理与 8 个异常回滚点、event_seq/过滤合同测试通过；xhigh 保持 pending-evidence，应用接缝与生产迁移交由 Task03 实现并复测。
- **024 Task03 后端推理流与持久化** ｜ 待执行 → 实施中 ｜ Task02 条件 GO；启动后端统一档位解析、推理事件、schema v7 迁移、过滤与隔离实现，暂不执行全量回归。
- **024 Task03 xhigh 能力证据口径** ｜ 评审修订 ｜ 结合局域网 Ollama 实测：显式 `think=true` 且响应含非空 reasoning 与 evidence_id 即可判定 provider 支持；server 日志改为可选审计证据，缺响应证据仍保持 pending/unavailable，避免环境日志不可读阻塞功能实现。
- **024 Task03 后端推理流与持久化** ｜ 实施中 → 已完成（条件通过） ｜ 后端实现、独立 backend-reviewer/tester 复核及 81 个定向用例通过；未执行全量回归，Task04 前端实现继续推进。
- **026 推理档位反馈与首屏响应修复** ｜ 新建 → 待确认 ｜ 2026-09-12：用户报出「提问后无对话卡片」「不支持的档位仍能选并报 409」「所有错误都叫连接失败」三个缺陷；经两轮 Grilling 收敛 Q1–Q12 全部决策（Q5 由用户指定为「支持 xhigh 用 xhigh，否则取支持的最高档」）后落盘 spec 与 `plans/026/` 全部 task 文件；**确认前不修改业务代码**。同时声明修订 024「探针失败返回 503」一条为「返回 200 + source=stale/unknown」。
- **024 可见推理过程与会话级推理档位** ｜ 已完成（环境延期） → 合同登记修订 ｜ 2026-09-12：三个用户可见缺陷移交 Spec 026 修复；024 合同本身不改，仅在其变更日志登记「探针失败返回 503」被 026 修订，避免两份 spec 口径冲突。
- **026 推理档位反馈与首屏响应修复** ｜ 待确认 → 已确认 ｜ 2026-09-12：用户回复「你改吧」视为明确确认；子代理模型由用户临时指定为 `hy3`（一次性偏差，§执行配置 模型列保持 `Deepseek-V4.1-Flash` 不修改），按 Task 02 → 06 顺序实施。
- **026 推理档位反馈与首屏响应修复** ｜ 已确认 → 实施中 ｜ 2026-09-12：Task 02/03 后端完成（探测不再抛异常、`default_effort` 改取最高档、接口新增 `source`/`refresh`、`unknown` 时 `off` 放行非 off 返 503），Task 04/05 前端完成（乐观建卡 31–68ms、错误文案按 `code` 分流、选择器四态与选中值校正）。后端评审 P0/P1=0（3 条 P2 已修，含重复探测 2 轮→1 轮）；前端评审首轮打回（P0=1、P1=2）后修复。
- **026 推理档位反馈与首屏响应修复** ｜ 已完成 → 已完成（合并期修订，新增 B17） ｜ 2026-09-12：并入 `origin/main` 时 spec-025 的 4 个用例暴露真实回归 —— 请求未显式带档位时后端默认取 `xhigh`，能力 `unknown` 即返 503，使「任何没手动选档位的首发消息在探测抖动时被拒」，正是本 spec 原本要修掉的报错。经用户拍板「修产品：未指定则回落 off」，新增边界 B17：未显式指定 + 能力未知 → 回落 `off` 放行；仅显式非 `off` + 未知才 503。判定口径按「本轮是否显式给出档位」而非「值是否为空」（`get_last_reasoning_effort` 无记录时填 `xhigh`）。`_resolve_request_effort` 加 `explicit` 参数，两处调用点传入 `payload.reasoning_effort is not None`；原锁定旧行为的测试拆为「未指定→回落 off」与「显式非 off→503」两条。修复后 spec-025 4 个失败用例与 026 全部用例共 71 项通过。
- **026 推理档位反馈与首屏响应修复** ｜ 实施中 → 已完成 ｜ 2026-09-12：Task 02–06 全部收口。需求/技术/验收三份评审均通过；边界 B1–B16 全 16 条通过；后端全量回归 1028 passed（1 既有失败、395 沙箱环境噪音）、前端 148 passed、真实 Chromium Playwright 22/22；真实浏览器验收发现并修复 B9 校准提示缺失（静默降档，违反 024 红线）。三个用户缺陷均以「真实浏览器 + 真实 HTTP」双证据验证修复：卡片 68/47/31ms 出现；409 卡片为「该模型不支持『极高』推理档位，可选：关闭」且不含「连接失败」；`deepseek-coder:33b`+xhigh → 503 `MODEL_CAPABILITIES_UNAVAILABLE`、`deepseek-coder-v2:16b`+xhigh → 409 `REASONING_EFFORT_UNSUPPORTED`（「没查清」与「确实不支持」已正确区分）。服务已部署于 `http://127.0.0.1:8000`，Ollama 走局域网 `http://192.168.31.180:11434`（11 个模型）。遗留：能力探测结果非确定性（同模型同参数随环境变化且被缓存 300s）已移交 spec 027；B13/B14/B15 仅静态断言；`app.js:2244` 时间线仍按 `retryable` 判断（非阻塞 P2）。

## 2026-09-11

- **023 / 023.1 分支合并入 main** ｜ 合并完成（merge commit `60f5bae`） ｜ 2026-09-11：将 `fix/spec-023.1-p1-fixes` 合并入 `main`。因两侧并行改动产生 5 处冲突，手工整合如下——① `routes.py`：保留 main 的 `routes_conversations` 并并入 `routes_skills`/`routes_tools`；② `routes_chat.py`（真实集成冲突）：采用本分支 Skill 识别 + Tool 执行编排，叠加 main 的记忆库 system-rule 与可观测性（`build_role_aware_messages` 组装 messages、`observation_messages`/`observation_metadata` 埋点含 `extra_metadata`）；③ `index.html`：以 main 为基础补入 “Skill 与 Tool” 导航/视图/详情对话框，版本 `?v=32→33`；④ 冻结清单 `upload-closure-matrix.json` 按合并后工作树重算 sha256 与 `inventory_digest`；⑤ `test_frontend_paper_contract.py` 取 main 版。合并后定向回归 **219 passed / 1 failed**（`test_conversations_api` 的 durable worker 用例，经 worktree 复核为 **main 合并前即存在的存量失败**，非本次引入）；运行时冒烟 `/`、`/api/skills`、`/api/tools`、`/api/memories?scope=global` 均 200
- **023 Skill 与 Tool 管理模块** ｜ 新建 → 待确认 ｜ 2026-09-11：用 `grill-with-docs`（已安装 `grilling` / `domain-modeling`）三轮访谈冻结 Q1–Q10 全部根决策——Skill=编排层（SKILL.md 协议）/Tool=执行层（后端原子动作）、只管 `.agents/skills/` 并迁移废弃 `~/.codex/skills/download-paper` 硬编码、网页仅只读+启停、规则匹配与 LLM 意图双触发（27B 实测 `GO/NO-GO`）、Agent 读正文自编排且不改 SKILL.md 正文（仅 frontmatter 加 `tools:`）、状态落 `data/kb/skill-state.json`、Tool 交给模型采用「原生 function calling 优先 / 降级计划 JSON」混合策略。已落盘 spec 与 `plans/023/README.md`；**确认前不修改业务代码，task 文件待确认后创建**。
- **023.1 Skill/Tool 评审遗留 P1 修复** ｜ 新建 → 已确认 → 实施中 → **已完成（已合并入 main）** ｜ 2026-09-11：用户指示「接着修」并建立派生分支 `fix/spec-023.1-p1-fixes`。后端修 B1（删除 `conferences[0]` 静默退化、`all` USENIX 优先、`dblp` 无匹配返回可读错误、`except` 收窄）、B2（多 tool_calls 聚合为单条 assistant 消息 + id 配对，并修掉"边校验边执行"的部分执行缺陷）、B3（全禁用时明确提示）；前端修 F1（序号 + AbortController 防 stale write）、F2（`stFetchJson` 区分网络/业务错误给中文提示）、F3（失败态三字段统一），`?v=26→27`。合并验证 **149 passed**，ruff 零新增；运行时 B3 复验通过
- **023 Skill 与 Tool 管理模块** ｜ 待确认 → 实施中 → **已完成** ｜ 2026-09-11：Task02 可行性 GO（原生 tool call 5/6、意图识别误判 5%、发现 Ollama 静默忽略非法 tools）后，Task03/04/05/06/07/08 由子代理完成（注册表、启停 API、迁移废弃硬编码、规则+LLM 双触发识别、原生优先/降级计划 JSON 的执行、前端管理页）；Task09 三份评审**均为真实独立评审且通过、P0=0**，验收实测对话四路径端到端通过且模型真实编排 `search_paper_catalog` 返回 USENIX 2024 真实标题，回归 98 passed；架构师已签字，复盘落盘 `docs/sdd/retro/2026-09-11-spec023-skill-tool-management.md`。遗留 2 条后端 P1（选源静默退化、多 tool_calls 消息复制）已书面降级为「已知限制」，转已完成后排期修复
- **020 零碎 bug 解决** ｜ 已完成（容器保持开放） → 待确认 → **已完成（第 3 批 BUG-05；主模型代行）** ｜ 2026-09-11：新缺陷——首次部署到新机器后上传即报 `INDEX_REBUILD_REQUIRED`。实测 `data/kb` 目录完全不存在（无 `papers.json` / `index-generation.json` / `rebuild-runs`）；根因为 `manifest_store.py:599-603` 的 `require_generation()` 只判断 marker 是否存在、缺失即抛 409，把「空库首次部署（无索引可重建）」与「已有旧索引但代际不符（需停服全库重建）」两种状态混为一谈（`routes_kb.py:310-324` 统一过这道门；`main.py:34-40` 启动时仅打印日志不初始化；同函数内 `papers.json` 缺失却走 503 `INDEX_FINALIZE_REQUIRED`，说明语义本就区别对待）。修复方案：空库自动 bootstrap 初始代际 marker，非空库保持 fail-closed 仍返回 409。纳入第 3 批 **BUG-05 / Task07**（仅后端）；**确认前不修改业务代码**。

## 2026-09-08

- **017 后端限界上下文彻底重构** ｜ 已完成 → 实施中 ｜ Luna xhigh 独立审计发现旧 `agents/article_agent.py`、`core/config.py`、`api/routes.py` 兼容转发和未接线 `PaperImportPort` 仍不符合原 Spec 的“旧结构清零/跨域 port 接线”要求；保留历史验收证据，退回修复与重新验收。
- **017 后端限界上下文彻底重构** ｜ 实施中 → 已完成 ｜ 完成旧 Agent/config/routes 清理、PaperImportPort factory 接线与回归；定向 `131 passed`，全量 `653 passed / 38 subtests`，修复轮验收见 `017-remediation-acceptance-review.md`。
- **018 知识文档切片检查器与双向原文定位** ｜ 新建 → 待确认 ｜ 用户要求在个人知识库新增切片检查 Tab；经 Grill with Docs 访谈确认 PDF + Markdown、文本块级双向映射、单版本切换、只读检查、旧文档零 embedding 自动补建和窄屏切换。Spec 与 Task 02–07 已落盘；用户产品方向确认已收到，仍待需求/技术评审门禁通过后转已确认。
- **018 知识文档切片检查器与双向原文定位** ｜ 待确认 → 已确认 ｜ 需求评审修订轮与技术复审最终通过；用户明确要求开始 Spec018。已补齐 provenance、迁移、Markdown、manifest/API、安全依赖和 A/B/C/D 交接门禁。
- **018 知识文档切片检查器与双向原文定位** ｜ 已确认 → 实施中 ｜ 启动 Task02 来源锚点 Go/No-Go；当前只允许固定样本和只读可行性验证，No-Go 自动停止后续任务，不修改业务代码。
- **015 Task15–17 继续开发** ｜ Task15/16 待执行 → 实施中 ｜ 用户明确要求接续已有部分实现并开发 Task15–17；已核对 Task13/14 落盘证据，分别分派 backend-dev 与 frontend-dev 实现异步目录检索、LangGraph/RAG、来源进度和分页。模型仅本轮临时使用 Luna high，不写入长期规则；Task17 将在实现完成后执行验收与部署。
- **015 USENIX-only 目录检索阶段** ｜ Task15/16 实施中、Task17 待执行 → Task15/16/17 已完成（USENIX-only） ｜ 完成 LangGraph/RAG、双源进度、固定分页、增量缓存、并发租约恢复、权威合并、失败释放和旧同步路由删除；QA 与后端复审通过，Spec 总状态保持实施中，ACM/IEEE、自定义会议、排序质量与真实 PDF/GUI 证据明确 deferred。
- **015 USENIX-only 本地部署** ｜ 实现完成 → 已部署验证 ｜ 8000 被沙箱外进程占用且无法停止，改用 8001 启动本版本；首页与 `/api/health` 返回 200，最小 USENIX 异步检索入口返回 202。Qdrant 并发占用按降级语义记录，未宣称 RAG 在线健康。

## 2026-09-06

- **017 后端限界上下文彻底重构** ｜ 待确认（评审打回） → 待确认（已修订，待复审） ｜ 需求评审与技术评审结论均为「打回」；已按需求 4 项必改与技术 7 项必改修订 Spec017 与 Task02/03/04/06：补齐对外契约基线（35 个端点、4 组公开别名、三类 SSE、两类错误体）、环境与数据兼容性矩阵（含配置四级优先级与 read-modify-write 要求）、旧目录逐文件迁移分类与四类 import 检查范围、跨上下文端口契约、静态边界检查规则，并补齐产品使用步骤与 13 项验收场景；执行顺序改为 02→03→05→04→06→07→08。状态仍为待确认，需复审通过后才进入用户确认。
- **015 USENIX accepted-papers 修复补丁** ｜ 评审结论 Warning → 整改闭环 ｜ 补齐 `_listing_for` 与显式 cycle 分支回归测试，并实现受控年份下界 `USENIX_MIN_YEAR = 2022`，消除默认窗口内 2021 年的常驻 `USENIX_UNAVAILABLE` 告警；全量回归 626 passed / 0 failed，提交 `8a26e29`。
- **017 后端限界上下文彻底重构** ｜ 待确认（复审通过） → **已确认** ｜ 用户明确授权开发顺序：先 017 → 全量回归 → 再 015。复审已通过（`docs/sdd/reviews/017-rereview.md`），按 `02→03→05→04→06→07→08` 执行，子 agent 与模型沿用 `AGENTS.md` 角色分配表。
- **017 后端限界上下文彻底重构** ｜ 待确认（已修订，待复审） → 待确认（复审通过，待用户确认） ｜ architect 复审（`docs/sdd/reviews/017-rereview.md`）判定需求 4 项与技术 7 项必改**全部闭环**（R3 原「部分闭环」已修正：`/health` 在 Ollama 不可达时恒返回 200 且 `models: []`，不产生错误体，见 `routes.py:280-291`）；抽查 4 项代码事实与 spec 描述一致。状态仍为 `待确认`，等待用户明确确认后进入实现。

## 2026-09-05

- **015 安全顶会论文检索与知识库导入** ｜ 待确认 → 已确认 ｜ Task13–17 需求/技术复审已落盘（结论通过，见 `docs/sdd/reviews/015-catalog-requirement-review.md` / `015-catalog-tech-review.md`）；用户明确"调用子 agent 进行开发"，授权实现 Task14–17；Task14 由 junior-dev（qwen3.8:27b-mlx）启动。
- **015 安全顶会论文检索与知识库导入** ｜ 实施中 → 待确认 ｜ 用户将当前检索调整为 USENIX 官网优先、DBLP 辅助、SQLite 增量目录、LangGraph 并行工作流、独立目录 RAG、来源进度卡片和每页 10 篇冻结结果。已完整更新 Spec015 并新增 Task13–17；按用户要求本轮只落盘文档，暂停代码实现，等待后续安排。
- **015 Task13–17 增量目录流程** ｜ 新建 → 待执行 ｜ 已把现有代码复用清单固化为实现硬约束，写明 schema v2、接口、工作流节点、缓存/租约/恢复、固定样本、完整子 Agent Prompt、返回字段、评审验收和回滚；需求/技术复审与用户再次确认前不得执行。
- **015 Task12 USENIX Skill** ｜ 单一混合版 → 下载版 + 目录元数据检索版 ｜ 为避免搜索阶段误触发 PDF 探测，拆分 `.agents/skills/usenix-accepted-papers`（下载/验证/导入）与 `.agents/skills/usenix-paper-catalog-search`（目录/增量/LangGraph/RAG），并让 Task13–17 全部指向目录版；两个 CodeBuddy 适配器同步落盘。
- **017 后端限界上下文彻底重构** ｜ 新建 → 待确认 ｜ 用户要求彻底整理整个后端：按论文发现、知识库、文章助手、聊天和平台能力重组；明确不保留旧内部 import 兼容层，对外 HTTP/JSON/环境变量与数据位置保持不变。已建立 Spec017 与 Task02–08，等待评审与确认门禁。
- **015 Task06 浏览器运行时依赖** ｜ 环境阻塞 → 条件解除 ｜ 因项目目录由 `PyCharmMiscProject` 改名为 `ResearchAgent`，`.venv` 脚本指向旧绝对路径；已修复 Python 3.11 虚拟环境，安装并锁定 Playwright 1.52.0 与对应 Chromium，运行时浏览器健康接口恢复 `available=true`。真实 ACM/IEEE 登录仍需用户合法账号参与。

## 2026-09-03

- **016 可移植 Task 账本与自动执行协议** ｜ 新建 → 待确认 ｜ 为跨 Codex、CodeBuddy 和其他 Agent IDE 的研发交接建立“Git 跟踪 Markdown 为长期事实源、SQLite 为可重建运行层”的流程；Task 将包含机器元数据、完整子 Agent Prompt、统一结果协议、执行轨迹和指标。已按 spec-013 格式建立 spec 与 `docs/sdd/plans/016/` Task 02–09；当前只落盘文档，不执行实现，等待用户确认。
- **015 安全顶会论文检索与知识库导入** ｜ 新建 → 待确认 ｜ 新增独立论文检索 Tab 的规划：默认检索 CCS、USENIX Security、IEEE S&P、NDSS 最近五个完整年份，支持搜索添加会议、语义排序、单篇/批量实际下载并按“年份-会议-标题”命名后导入知识库；ACM Digital Library 与 IEEE Xplore 采用项目内 Playwright 完成合法登录续传。已按 spec-014 格式建立 spec 与 `docs/sdd/plans/015/` 任务 02–09；当前只落盘文档，不执行任务，且必须等待 spec-013/014 形成稳定基线。

## 2026-09-02

- **014 知识库本地 Rerank 重排** ｜ 新建 → 待确认 ｜ 为个人知识库增加本地 Qwen3-Reranker 批量重排；现有 Ollama 包实测不适合专用 rerank，计划改用 llama.cpp `/v1/rerank` 与兼容 Q8_0 模型。已按 spec-013 格式建立完整 spec，并在 `docs/sdd/plans/014/` 拆分任务 02–09；当前仅文档落盘，等待用户确认。
- **014 知识库本地 Rerank 重排** ｜ 待确认 → 已确认 ｜ 用户授权“当前未提交代码能运行则进行 spec-014”。已先创建 `/tmp` 安全快照并在不回滚、不 stash、不清理工作树的前提下验证：FastAPI 首页/health/KB health、Langfuse 正常，全量测试 `253 passed`；需求与技术评审均通过（附意见），条件满足，进入实施门禁。
- **014 知识库本地 Rerank 重排** ｜ 已确认 → 实施中 ｜ 已在隔离 worktree 完成 Task 02 的兼容模型与排序质量 Go/No-Go，并继续实现本地 reranker 生命周期、客户端、检索和健康状态；等待与 Spec 013 的观测整合和最终验收。
- **012 知识库召回质量与切分 v2** ｜ 状态不变（已完成） ｜ **交付后缺陷修复**（同功能范围，不新建编号）：用户反馈论文卡片「标题展示不完全、重建/删除按钮看不到」。根因是纯前端布局——标题 `nowrap+ellipsis` 被截断；卡片因 spec-012 新增双版本徽章与进度条而增高，在固定高度侧栏的滚动区里把 `actions` 裁掉。修复：标题独占一行完整换行、meta 独立成行、侧栏 320→360px；`actions` 移入徽章行右对齐、进度条独占一行，单卡高度 110px→约 80px；按钮补边框。静态资源 `?v=13`，全量回归 `253 passed`。复盘见 `docs/sdd/retro/2026-09-02-kb-card-layout-retro.md`（教训：固定高度容器内新增内容须核算容量；DOM 契约校验需升级为可见性校验）。

## 2026-09-01

- **012 知识库召回质量与切分 v2** ｜ 新建 → 已完成 ｜ 验收通过 + 开发主管签字（`tech-lead` 子代理，27B，已成功；任务收窄后 27B 可用）。三项需求全部实现：参考文献入库但默认不召回（仅自动意图识别）、PDF 排版噪声清洗（断词合并 + 软换行转空格）、切分 v2（规则预筛 + `qwen3.8-27b-q4` 结构分析 + 固定上限，异步带百分比进度、提问时可选版本）。全量回归 `253 passed`（新增 `test_kb_normalize.py`/`test_kb_chunkers.py`/`test_kb_tasks.py`）。验收中发现并修复 3 项：R1 显存竞争未落实、跨页引用未显示 `p.3-4`、旧记录状态误标 failed；另补做旧索引点迁移（345 点补齐 `chunker` 字段）。前端 `?v=12`。
- **子代理可用性（跨 spec 流程风险）** ｜ 记录 ｜ `junior-dev`（27B 量化）与 `tester`（9b）在本次长流程任务中均中途失效：前者两次分派零产出且超时后仍在后台写文件覆盖他人代码，后者 18 分钟仅跑完测试即中断。编码与验收最终由主会话承担。详见 `docs/sdd/retro/2026-09-01-subagent-model-naming.md`。

## 2026-08-30

- **011 本地个人论文知识库（RAG）** ｜ 新建 → 实施中 ｜ 实现已完成（后端 kb 服务包 + `/api/kb/*` + 知识库前端视图 `?v=6`；150 用例全绿、覆盖率 90%；端到端实测上传 20 页 PDF→125 片段→混合检索→带引用生成→删除全链路通过），验收报告结论通过但**开发主管签字栏为空**，按 `AGENTS.md` 硬规则第 6 条**保持 `实施中`，不转 `已完成`**。同日做流程复盘：本轮存在需求评审缺失、`pm`/`junior-dev`/`tester` 未分派、技术/验收评审由主模型代行等流程退化，已新建 `SDD-GATE-CHECKLIST.md`、修订模板与 `AGENTS.md`、回填 007/008/010 共 6 处「结论：/」占位；复盘见 `docs/sdd/retro/2026-08-30-spec-011-process-retro.md`。
- **007 / 008 / 010** ｜ 状态不变（已完成） ｜ 回填各自 spec「评审记录」中残留的「结论：/」占位（共 6 处），统一为评审文档中的真实结论；纯台账校正，无代码改动。

## 2026-08-29

- **010 后端测试覆盖率提升至 80%** ｜ 新建 → 已完成 ｜ 起因：spec-008/009 的 PR 合并门禁中"覆盖率 ≥80%"未通过（当前 69%）。经用户拍板选「B 先补测试」，另开 spec-010 补后端测试；实测覆盖 routes.py（49%→94%）、graphs/chat.py（25%→100%），TOTAL 69%→87%，85 passed，零业务改动，离线可重复（已停 Ollama 验证）。验收通过。

## 2026-08-28

- **008 模型别名展示与设置** ｜ 已完成 → 实施中 ｜ 用户反馈 v1"列表外统一编辑弹层"不符合预期，要求别名**在模型自己的卡片内**修改。spec-008 交互重做为卡片内行内编辑（✎ 图标触发、原地变输入框、Enter/失焦保存、Esc 取消），展示改为"别名大标题 + 真实名灰色小字（仅设别名时显示）"；移除顶部"编辑别名"按钮与"重置全部"批量入口。属同一功能范围变更，不新建编号。
- **008 模型别名展示与设置** ｜ 实施中 → 已完成 ｜ 行内编辑实现完成，首次以**新建的 tester 子代理（带 tools + sdd-acceptance skill + 本地模型 local-qwen38-27b-tools）**执行验收评审，A1–A9 全部通过；子代理发现的 R1（隐私模式未降级内存 Map，§5 强制约束）、R2（✎ 默认不可见）、R3（innerHTML 清空）三项风险已由架构师修复并复验，静态资源升 `?v=4`，服务在 8000 端口运行时验证通过。本地模型 function call 实测结论见 `docs/sdd/TOOLCALL_BENCHMARK.md`。

## 2026-08-27

- **006 修复左侧"模型库"Tab 点击无反应** ｜ 已确认 → 实施中 ｜ 子模型 oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU 产出草稿（为占位骨架，未直接采用）；架构师基于真实文件做最小增量实现：index.html 加 data-view/nav 与 #models-view 容器，app.js 加 showView/renderModelList（用 hidden toggle 防抖、不重建 #chat）。JS 语法校验通过，无 lint 错误。待验收评审。

## 2026-08-26

- **003 集成 download-paper Skill** ｜ 已确认 → 已完成 ｜ 补齐 `use_skill` 记录与 `skill` 状态（version/路径）读取，新增 `build_download_plan` 单测；本地服务验证公开 PDF 计划生成通过。
- **004 完全由 download-paper Skill 主导下载** ｜ 待确认 → 已完成 ｜ skill 主导下载编排与后端执行，放宽 003 约束允许 Cookie/浏览器/科研通；保留 Crossref/OpenAlex 发现链路；新增 `decide_download_method`/`fetch_cookies_via_opencli`/`download_under_skill`/`build_skill_plan`。
- **005 前端候选展示限制与 Skill 选取提示** ｜ 待确认 → 已完成 ｜ 后端候选过滤为 confidence>0.5 且 ≤3、intent 事件对 download_paper 携带 skill；前端在意图识别后显示灰色"已选取 download_paper 技能"提示。
- **001 文章检索与下载 Agent** ｜ 已完成（意图识别缺陷，Errata 待确认） → 已完成（意图识别修订 Errata 已实施） ｜ 19:37 确认；20:30 实施完成 ｜ 意图识别由脆弱的关键词匹配改为大模型判断（`classify_intent` LLM 路径 + `qwen3.5:9b`，强下载词短路跳过模型），`chat` 作为兜底分支，移除 `unsupported` 路由；修复"生成一个300字的小故事"被误判为"无法识别"的问题，已在运行时经 `/api/agent/run` 验证 chat 兜底与 download_paper+skill。
| 2026-09-03 | Spec 013 本地 LLM 调用观测与性能评估平台 | 待确认 → 已确认 | 用户明确要求修复阻塞并继续后续开发；MinIO/OTLP 上报阻塞已定位，采用 v4 events_only 验收口径。 |
| 2026-09-03 | Spec 013 本地 LLM 调用观测与性能评估平台 | 实施中 → 实施中 | Task 07 继续推进：补齐全量聚合、model/route/cold-hot 维度、chain_type 生产字段和默认折叠详情脱敏；前端依赖下的类型、组件测试和验收仍待执行。 |

## 2026-09-04

- **015 安全顶会论文检索与知识库导入** ｜ 待确认 → 已确认 ｜ 用户明确要求“spec014 已由其他 Agent 收尾后继续开发 spec015”；当前 `main@c17c7f4` 已包含 Spec014 收口提交，开始执行 Task02 Go/No-Go。
- **015 安全顶会论文检索与知识库导入** ｜ 已确认 → 实施中 ｜ 创建并切换至 `feature/spec-015-security-paper-discovery`，启动 tester 执行 Task02 基线、数据源、Reranker 与 Playwright 验证；业务代码暂不修改。
- **015 安全顶会论文检索与知识库导入** ｜ 实施中 → 实施中 ｜ 用户授权跳过 Spec013/014 基线核对与 Reranker 判断，Task02 收窄为 DBLP/OpenAlex 数据源、降级策略与 Playwright 桥接验证；跳过项记录为 deferred，不阻塞后续。
- **015 安全顶会论文检索与知识库导入** ｜ 实施中 → 实施中 ｜ Task02 tester/tech-lead 条件放行内置会议 publication search 与 OpenAlex 补全；DBLP Venue Search 因 429/503 无成功样本保持 blocked，Task03 收窄启动内置会议与 OpenAlex 实现。
- **015 安全顶会论文检索与知识库导入** ｜ 实施中 → 实施中 ｜ Task03 内置会议召回、OpenAlex 补全、SQLite 持久化和搜索 API 已完成并通过最终验收/技术签核（41 个定向测试通过）；Venue Search/custom conference 保持 blocked，导入 FK/TTL 移交 Task05。
- **015 Task05 安全下载、规范命名与知识库导入** ｜ 实施中 → 已完成 ｜ 固定服务端 allowlist、失败补偿、DBLP key 和 Content-Type 安全修复通过 Tech Lead 复核与 tester 验收；定向回归 150 passed，修复项精确回归 11 passed，并发幂等 10/10 轮，批量/登录续传移交 Task06。
- **015 Task06 批量任务与登录续传** ｜ 待执行 → 实施中 ｜ Task05 收口后启动批次/条目 SQLite 状态机实现，先建立可条件迁移、可租约恢复的持久化基础。
- **015 Task06 批量状态机切片** ｜ 实施中 → 实施中 ｜ 批次/条目持久化、批量编排、登录项隔离、租约恢复和并发幂等通过 Tech Lead/tester 最终切片复核；指定测试连续 3 次均 22 passed，继续进入浏览器与站点解析切片。
- **015 Task06 浏览器管理器切片** ｜ 实施中 → 实施中 ｜ headed persistent profile、单 profile/站点锁、ACM/IEEE exact origin allowlist、敏感产物禁用和健康契约完成；10 项 fake Playwright 测试通过，继续实现 ACM/IEEE 解析与登录续传 API。
- **015 Task06 ACM/IEEE 解析切片** ｜ 实施中 → 实施中 ｜ ACM 解析 7 passed、IEEE 解析 10 passed；均拒绝非受控 origin、认证参数和 Cookie/Authorization，登录/resume API 继续实现。
- **015 安全顶会论文检索与知识库导入** ｜ 实施中 → 实施中 ｜ Task05 已启动：安全 URL 校验切片完成并通过 6 项安全边界测试，开始规范命名与论文身份去重；实际下载和知识库导入尚未开始。
- **015 安全顶会论文检索与知识库导入** ｜ 实施中 → 实施中 ｜ Task05 规范命名与论文身份去重已完成，开始实际 HTTP 安全下载适配；知识库导入、批量任务和登录续传仍待执行。
- **014 知识库本地 Rerank 重排** ｜ 实施中 → 实施中 ｜ 收口验收补充了四组合运行对账、真实成功/降级 `kb.rerank` 事件、`--ubatch-size 1024` 长输入修复和禁用组合真实问答尝试；tester 仍判定不通过，tech-lead 尚不可签字，故保持实施中。
- **014 知识库本地 Rerank 重排** ｜ 实施中 → 实施中 ｜ 定位收口 Bug：`/api/kb/ask` 未关闭回答模型 thinking，导致 qwen3.5 真实 SSE 长时间无 `done`；已补入 Spec014 的复现、根因和修复验收条件，进入窄范围代码修复。
- **013 本地 LLM 调用观测与性能评估平台** ｜ 实施中 → 已完成 ｜ Task 07 前端依赖与环境阻塞修复（补齐 lockfile + 离线安装 + .env），前端 37 用例全绿；5 项实质缺陷（散点丢点误判、脱敏覆盖、聚合守卫、截断提示、router 测试）闭环；C8 埋点 safe_call 包裹完成。验收由主模型代行（非独立评审）。详见 `docs/sdd/plans/013/task-07-stats-custom-view.md` 修复轮次执行结果与 `docs/sdd/reviews/013-task07-acceptance-review.md` 复核结论。
- **013 Task 07 验收** ｜ 不通过 → 通过（代行） ｜ 见上。
- **014 知识库本地 Rerank 重排** ｜ 实施中 → 实施中 ｜ 修复 `8c1c3ae`（KB ask 显式 `think=False`、LangChain `reasoning=False`）后，四组合真实 KB ask 均以完整 SSE `done` 收口，tester 最终判定通过；仍缺 tech-lead 签字与复盘，故暂不转完成。
- **014 知识库本地 Rerank 重排** ｜ 实施中 → 已完成 ｜ 发现并修复 `8c1c3ae` 引入的回归：`create_chat_model` 默认 `reasoning=True`，使所有仅传模型名的调用方（`article_agent`、`download_paper_skill`、`kb/retrieve.py`、langchain 聊天链路）被强制下发 `think=true`；`6daa498` 将默认值改回 `None` 并补 2 条契约测试，全量 `351 passed`。以 `deepseek-coder-v2:16b` 复测：KB ask HTTP 200 且 SSE 完整到 `done`（259 token、0 error），普通聊天同样完整收口，关键阻塞第 2 项（citations 后 HTTP 400）解除。Task 08/09 全部完成，tech-lead 签字已填（主会话代行，非独立评审，已在验收报告与复盘中标注），复盘落盘 `docs/sdd/retro/2026-09-04-spec-014-reranker-retro.md`。
- **014 Task 08 / Task 09** ｜ 部分完成 / 阻塞 → 完成 ｜ 见上。
- **015 Task06 真实登录验收** ｜ 实施中 → 实施中 ｜ 最新离线安全复核通过（Tech Lead/tester；定向 212、全量 502），但当前虚拟环境未安装 Playwright 且无合法 ACM/IEEE 账号样本，真实 headed 登录续传暂保持环境阻塞；继续推进不依赖真实账号的 Task07。
- **015 Task07 论文检索 Tab** ｜ 实施中 → 实施中 ｜ HTML/JS/CSS、会议搜索 API、开关竞态、稳定去重排序与批次隔离已完成；Tech Lead/QA 离线复核通过。A3 自定义会议仍受 DBLP Venue Search 前置阻塞，真实 GUI/窄屏和 ACM/IEEE 登录需受控环境，继续推进 Task08。
- **015 Task08 测试与安全回归** ｜ 待执行 → 实施中 ｜ QA 盘点完成；已补齐 SSRF/PDF 安全矩阵、加密 PDF 拒绝和回归稳定性，当前全量 521 passed。冻结排序集/nDCG、Task04 质量证据及真实 GUI/公开 PDF/ACM-IEEE 登录仍待受控环境。
- **015 Task09 收口与部署** ｜ 待执行 → 实施中 ｜ 本地服务在受控权限下启动并验证首页/健康/会议接口成功，Reranker 按既定策略降级；全量回归通过。外部数据源、自定义会议、真实 GUI/登录和排序质量证据仍阻塞，等待 QA/Tech Lead 收口报告。
- **015 Task09 收口复核** ｜ 实施中 → 实施中 ｜ Tech Lead 与 QA 报告已落盘，离线回归和受控部署证据通过；A3/A4/A10/A11/A14、真实 GUI/公开 PDF/旧 KB 端到端仍无可复核证据，Spec015 保持实施中并完成阶段复盘。
- **015 Task08 旧 KB 兼容补测** ｜ 实施中 → 实施中 ｜ 新增真实旧 JSON/PDF/FakeQdrant 集成测试，覆盖列表、检索、重建、删除及异常隔离；全量回归升至 525 passed，排序质量与真实外部证据仍阻塞。
- **015 论文发现目录架构变更** ｜ 实施中 → 待确认 ｜ 用户指出论文相关实现散落在 `domain/` 与 `services/`；已提出统一迁移到 `backend/app/paper_discovery/` 的限界上下文方案，暂停代码移动和后续实现，等待确认。
- **015 USENIX accepted papers 第二来源** ｜ 待确认 → 待确认 ｜ 用户要求不新建 Spec，将 USENIX Security accepted-papers 官网检索、USENIX PDF/prepublication PDF 和 arXiv 严格匹配兜底纳入 Spec015；已完成官方页面/API 调研并新增 Task11–12，等待用户确认补充范围。
- **015 USENIX accepted papers 第二来源** ｜ 待确认 → 实施中 ｜ 用户确认按补充后的 Spec015 执行；Task11/12 开始实现，主 Agent 与子 Agent 临时使用 gpt-5.6-luna high。
- **015 Task11 USENIX accepted + arXiv** ｜ 待执行 → 已完成 ｜ 来源解析、严格匹配、缓存/节流、PDF 安全探测、候选字段/SQLite、搜索/API 接线和跨来源去重均通过 Tech Lead 最终复评与 QA 验收；全仓回归 552 passed。
- **015 Task12 项目级 USENIX Skill** ｜ 待执行 → 已完成 ｜ 创建 `.agents/skills/usenix-accepted-papers/SKILL.md`、CodeBuddy 适配器，并将适用角色明确为 ResearchAgent 主 Agent、项目 Agent、PM、Tech Lead、QA、调度器和执行 Agent；静态与跨 IDE 验收通过。
- **015 Task12 Skill 适用范围澄清** ｜ 已完成 → 已完成 ｜ 用户明确“项目的 agent”指 ResearchAgent 本身；已在 Skill 与 `AGENTS.md` 中固定主 Agent/项目级 Agent 的触发和执行协议，保持本次临时 Luna high 模型选择不进入长期模型规则。
- **015 Task13 全局目录协议与复用审计** ｜ 待执行 → 实施中（约 60%）｜ 2026-09-07 收口回填：`search_source_progress`、`search_results` 表与 `get_search_results_page()` 已落地（见 `reviews/015-task13-store-implementation.md`）；协议固化与复用审计未收口。此前任务表长期写「待执行」，与代码脱节，本次一并修正。
- **015 Task14 USENIX 增量目录同步** ｜ 待执行 → 已完成 ｜ 2026-09-07 收口回填：USENIX 增量目录同步与 `/accepted` 只读端点已落地；按年份解析 slug 的修复经 `reviews/015-backend-review.md` 评审，结论 WARNING（1 项 HIGH：`_listing_for` 新正则无回归测试，列为下一提交强制项）。
- **015 安全顶会论文检索与知识库导入** ｜ 已确认 → 实施中（收口核对，维持实施中）｜ 2026-09-07 收口核对：验收评审（`reviews/015-acceptance-review.md`）结论为「整体验收不通过（阻塞）」且 Tech Lead 待签字，Task15–17 从未分派、无实现（A17 来源进度卡、A18 RAG 分页、A16 增量目录端到端均无证据），Task04 待执行，A3/A10/A11/A14 仍受外部与环境阻塞。**不满足转 `已完成` 的 DoD，保持 `实施中`**。按用户既定顺序：先完成 Spec017 后端重构与全量回归，再回来做 Task15/16。
- **017 Task02 建立迁移清单与契约基线** ｜ 待执行 → 已完成 ｜ 2026-09-07 收口回填：`plans/017/migration-inventory.md` 与 `openapi-baseline.json` 已冻结落盘，此前任务表长期写「待执行」，与代码脱节。
- **017 Task03 拆分 API 与平台装配** ｜ 待执行 → 已完成 ｜ 2026-09-07：路由拆分两批（system/chat/kb、paper/article）完成，`routes.py` 缩为 37 行纯注册入口；设置拆分、跨域 port（`platform/ports.py`）、composition root（`platform/bootstrap.py`）已落地；路由依赖改经注册表解析，3 处死 `TaskStore` 单例已删并新增架构测试锁定。端点归属清单落盘 `plans/017/api-module-inventory.md`。OpenAPI 与基线逐项一致（35 个 /api 操作，0 差异），全量 628 passed。
- **017 Task05 迁移知识库限界上下文** ｜ 待执行 → 已完成 ｜ 2026-09-08：10 个实现模块迁入 `knowledge_base/infrastructure/`；受控入口 `knowledge_base/application.py` 以显式 `__all__` 承接全部对外契约；`services/kb` 包（含 43 成员 facade）已删除，跨层 facade 通道不复存在。消费方按边界分流：api/脚本/论文发现走 application 入口，测试走 infrastructure。OpenAPI 与基线逐项一致，全量 629 passed。
- **017 Task06 迁移文章助手与聊天** ｜ 待执行 → 已完成 ｜ 2026-09-08：article_assistant/ 与 chat/ 建立；ollama*.py 迁 platform；run_chat 因依赖 graphs.chat（业务模块）下沉到 chat/application/chat_runner.py。
- **017 Task07 删除旧结构并验证模块边界** ｜ 待执行 → 已完成 ｜ 2026-09-08：observability 迁 platform、chat graph 迁 chat/application；删除 services/domain/graphs/observability 四个旧包；架构测试扩到 5 条可执行断言。
- **017 Task08 评审、部署与复盘** ｜ 待执行 → 已完成 ｜ 2026-09-08：验收评审通过（QA 与 Tech Lead 签字均由主模型代行，用户临时要求）；服务实际启动，首页/health/kb-health/conferences/kb-papers 均 200；复盘落盘。
- **017 后端限界上下文模块化** ｜ 已确认 → 已完成 ｜ 2026-09-08：Task02–08 全部完成。全量 631 passed；OpenAPI 与基线逐项一致；ruff 与迁移前持平。遗留：Reranker 降级运行、PaperImportPort 未实现、knowledge_base 受控入口待收窄。
- **018 知识文档切片检查器与双向原文定位** ｜ 实施中 → 待确认 ｜ 2026-09-08：Task02 只读 Go/No-Go 完成，严格结论 `NO-GO`。现有 PDF parser 仅返回 `(page, text)`，无法证明同源 bbox/line/word provenance DTO；hostile PDF 浏览器零网络请求证据未建立。固定 fixture、expected JSON、schema、审计报告和层级日志已落盘，Task03–07 暂停，待修订契约后重新确认。
- **018 知识文档切片检查器与双向原文定位（自动重建修订）** ｜ 待确认 → 待确认 ｜ 2026-09-08：经 Grill with Docs 确认旧 PDF 首次打开自动重建已有 v1/v2、原地替换前保存完整 point/vector 快照、失败恢复、首次失败后仅手动重试、块级 bbox、partial 可切换及 v2 不降级；hostile 浏览器网络硬门移至 Task05。新增 Task02A/02B，上一版评审不覆盖本修订，等待重新评审与确认；未修改业务代码。
- **018 知识文档切片检查器与双向原文定位（自动重建修订）** ｜ 待确认 → 已确认 ｜ 2026-09-08：独立需求复审通过；独立技术复审首轮打回四项 P0，补齐 hybrid_search 排除、文档级 operation/恢复、snapshot schema 和 bundle→manifest 边界后复审通过。用户明确要求开始执行。
- **018 知识文档切片检查器与双向原文定位（自动重建修订）** ｜ 已确认 → 实施中 ｜ 2026-09-08：仅放行 Task02A 生产级来源定位与旧索引安全升级基础；Task02B `GO` 前继续阻塞 Task03–07。
- **018 知识文档切片检查器与双向原文定位（全库索引替换修订）** ｜ 实施中 → 待确认 ｜ 2026-09-09 03:43 +0800：用户确认旧 Qdrant vectors 与旧 manifest 可丢弃，改为停服期间构建独立候选 Collection、严格验证、alias 切换和 finalize；原件、元数据和 ID 保留且原件不可原位修改。Task02A-A～C 保留，未提交 D1 snapshot 草稿废弃；业务代码暂停，等待重新需求/技术评审及用户确认。
- **018 知识文档切片检查器与双向原文定位（全库索引替换修订）** ｜ 待确认 → 已确认 ｜ 2026-09-09 10:50 +0800：独立需求评审通过；技术复审确认 P0-1～P0-7 和 upload-closure baseline 设计门全部关闭。用户明确要求“继续开发…开始执行”，确认本修订；Task04/06 的实际实现门仍保持未放行。
- **018 知识文档切片检查器与双向原文定位（全库索引替换修订）** ｜ 已确认 → 实施中 ｜ 2026-09-09 10:50 +0800：仅放行 Task02A-D 的候选索引重建基础实现与固定样本/FakeQdrant 验证；不操作真实用户索引，Task02B `GO` 前继续阻塞 Task03–07。
- **018 功能优先与生产安全债务分层** ｜ 实施中 → 实施中 ｜ 2026-09-09：用户要求先完成功能，安全问题记录后续完善。Task02A/02B 改为功能门与生产切换安全门双结论：功能通过可继续 Task03–05；候选删除授权、恢复拓扑、防篡改与 fsync 等债务全部转为 Task06 前置硬门，关闭前禁止真实 Qdrant 与任何真实 Collection 写删。
- **018 Task02A 生产级 provenance 与候选重建基础** ｜ 实施中 → 已完成（功能门） ｜ 2026-09-09：CandidateIndexPort、rebuild CLI/FSM、拓扑与验证 schema 完成四轮加固；候选测试 37 passed、独立探针 16/16 passed，tester/reviewer 均给出功能 GO。真实 Qdrant 与生产切换结论保留为 `DEFERRED_TO_TASK06`。
- **018 Task02B 来源锚点与候选协议重验证** ｜ 待执行 → 实施中 ｜ 2026-09-09：Task02A 功能门通过，开始以首轮固定样本和正式入口重放 PDF/Markdown block/chunk/anchor oracle；本 Task 仍禁止真实数据和真实 Qdrant。
- **018 Task02B 来源锚点与候选协议重验证** ｜ 实施中 → 已完成（功能 GO） ｜ 2026-09-09：修复 PDF-v2 同页 block 拼接导致 LLM 未调用的问题后，22/22 证据哈希、7/7 固定样本与 100 项联合测试通过；bbox 误差 0、Markdown 行号 100%。tester/Tech Lead 放行 Task03–05，生产切换仍延期至 Task06。
- **018 Task03 通用文档、Manifest 与迁移协议** ｜ 待执行 → 实施中 ｜ 2026-09-09：Task02B 功能 GO 后开始冻结 KnowledgeDocument/InspectionManifest/FinalizeBundle 契约与旧 metadata 迁移边界。
- **018 Task03 通用文档、Manifest 与迁移协议** ｜ 实施中 → 已完成（功能 GO） ｜ 2026-09-09：四份 schema、CONTEXT/ADR、幂等迁移与 canonical application 边界完成；30 项定向、370 项回归和 8/8 独立探针通过。旧 upload/delete/durability 问题留账转 Task04/06。
- **018 Task04 后端文档 Manifest 与检查接口** ｜ 待执行 → 实施中 ｜ 2026-09-09：Task03 功能门通过，开始实现通用文档 API、只读 source、真实索引 manifest、旧上传入口迁移与 generation/finalize 门禁。
- **018 Task04 后端文档 Manifest 与检查接口** ｜ 实施中 → 已完成（功能门） ｜ 2026-09-09 19:14 +0800：两轮修复后，检查、上传、原件读取、reindex 与删除的功能契约获 backend-reviewer `GO` 与 backend-tester `PASS`；定向 54 passed、相关回归 394 passed。closure matrix 仍为 baseline_frozen，生产切换债务继续阻塞 Task06。
- **018 Task05 前端双栏切片检查器** ｜ 待执行 → 实施中 ｜ 2026-09-09 19:14 +0800：Task04 功能门双签通过，放行本地 PDF.js、Markdown 块渲染、切片分页与双向定位实现；不触发全库重建或真实 Qdrant 变更。
- **018 Task05 前端双栏切片检查器** ｜ 实施中 → 已完成（功能门） ｜ 2026-09-10：四套 Node 前端契约测试、Schema/资源版本/vendor hash/path 检查和真实浏览器 hostile fixture（Markdown/PDF PASS、remoteRequests=0、Console 为空）通过；frontend-tester `PASS`、frontend-reviewer `GO`。worker 运行时 hash 加固、真实索引替换和恢复仍移交 Task06，Spec018 整体继续实施中。
- **018 Task06 真实全库索引替换、恢复与性能验收** ｜ 待执行 → 实施中（06-A 完成；06-B 前置门禁阻塞） ｜ 2026-09-10：FakeQdrant/临时目录故障矩阵 32/32、定向 pytest 44 passed，dry-run 写入 spy=0；真实 Qdrant、用户索引、原件和服务均未触碰。Task04 closure matrix 仍为 baseline/open/pending，生产切换保持 NO-GO。
- **018 Task06-B 前置审计与 FinalizeBundle 主链修复** ｜ 实施中 ｜ 2026-09-10：审计确认 closure matrix 17 open/12 pending，生产门继续 NO-GO；默认 rebuild 已接入 run-scoped FinalizeBundle stage、marker-last commit 与新进程 resume，相关定向测试 47 passed。弱 retire capability、legacy closure 测试和真实 Qdrant 行为仍阻塞 06-C。
- **018 Task06-B Retire fail-closed 修复** ｜ 实施中 ｜ 2026-09-10：旧 Collection 删除后新增 fresh-topology 后置条件，no-op 返回 `RETIRE_EFFECT_NOT_OBSERVED`、拓扑未知返回 `ACTION_RESULT_UNKNOWN`，均不得继续 finalize；49 项定向回归、9/9 独立探针、backend-tester `PASS` 与 backend-reviewer `GO`。真实 Qdrant 和 closure matrix 仍未放行。
- **018 Task06-B Closure-core 旁路收口** ｜ 实施中 → 实施中 ｜ 2026-09-10：修复旧固定 Collection 写入旁路、候选绑定、generation marker 绕过、reindex digest 漂移、paper-import 默认索引旁路与启动边界证据；8 个 core 门禁、378 项 KB 回归通过，独立 tester/reviewer 判定隔离 GO/PASS。论文导入、浏览器边界和真实生产切换仍未放行。
- **018 Task06-B 论文导入、批量补偿与浏览器边界** ｜ 实施中 → 实施中 ｜ 2026-09-10：批次 attempt owner/token、资源补偿、重启快照、immutable adapter composition 和 browser 零知识库写入边界完成；独立 reviewer/tester 对 T-IMMUTABLE-CREATE、T-PAPER-IMPORT、T-IMPORT-COMPENSATION、T-BROWSER-BOUNDARY 给出 GO/PASS，closure matrix 更新为 `implementation_ready`。真实 Qdrant、真实登录、generation topology 和生产维护窗口仍 NO-GO。
- **018 Task06-B generation-bound 补偿与导入** ｜ 实施中 → 实施中 ｜ 2026-09-10：补偿 ledger 纳入 `destination_collection`，默认 indexer/deleter 对缺绑定 capability fail-closed，marker drift 不会错误标记 `indexed`；独立 tester 63 项通过，首轮 reviewer 的问题已由下一轮修复。
- **018 Task06-B generation refresh/commit TOCTOU** ｜ 实施中 → 实施中 ｜ 2026-09-10：refresh 与 FinalizeBundle commit 共用 manifest-store 锁，expected collection 在锁内 compare-before-write；独立 reviewer 给出 generation-bound 隔离门 GO。真实 Qdrant、跨进程锁和生产切换仍未放行。
- **018 Task06-B 浏览器会话生命周期** ｜ 实施中 → 实施中 ｜ 2026-09-10：首轮 reviewer 发现请求期间 TTL 过期导入、并发 reopen/idle cleanup 两个 P1；已通过 daemon TTL 回收、import boundary 最终检查和 state-lock 注册边界修复，85 项隔离测试通过，独立 reviewer v2 判定 browser 子门禁 GO。真实浏览器、跨进程与生产 Qdrant 仍未验收。
- **018 Task06-B 历史旧索引测试迁移** ｜ 实施中 → 实施中 ｜ 2026-09-10：3 项历史失败测试已迁移到 canonical document/generation-bound API，未恢复退休入口；历史文件 5 passed、相关集 30 passed、全量回归 902 passed，独立 reviewer 判定迁移范围 GO。真实 Qdrant、跨进程和生产切换仍未验收。
- **018 Task06-B rebuild 锁与 stale recovery** ｜ 实施中 → 实施中 ｜ 2026-09-10：首轮 stale unlink/recreate 与 token TOCTOU 评审为 NO-GO；改为固定 inode + POSIX flock 持有式协议并补齐跨进程/异常退出接管测试，candidate+CLI 50 passed、全量回归 905 passed/1 skipped，独立 reviewer v2 判定隔离门 GO。真实 Qdrant、生产维护窗口和多机边界仍未验收。
- **018 Task06-B 真实源文件解析与 ID 安全门** ｜ 实施中 → 实施中（隔离 GO；真实 dry-run 阻塞） ｜ 2026-09-10：复用既有 `resolve_paper_path` 兼容旧 metadata 展示名与 `{document_id}.pdf` 原件布局，并收紧 basename/Unicode 控制字符校验；独立复评 GO，候选重建 59 passed、全量回归 916 passed/1 skipped。真实 dry-run 继续发现 4 个 42-byte `PDF_EMPTY` 原件；按 Spec018 权威 metadata 全集规则未执行 Qdrant 切换，等待数据处置决定。
- **018 Task06-B 空壳失败原件清理授权** ｜ 实施中 → 实施中 ｜ 2026-09-10：用户明确授权一次性删除已核对的 4 条 `status=failed`、42-byte、`PDF_EMPTY` 原件及对应 metadata 行；执行前需生成可恢复备份并逐项核对固定 ID/大小/hash，其他原件、metadata、Qdrant 和代码范围不变。
- **018 Task06-B 单文档 metadata 迁移与上传验证** ｜ 实施中 → 实施中 ｜ 2026-09-10：对当前保留的 1 条旧格式 metadata 完成 `018-document-v1` 原子迁移并生成备份；服务重启后健康/文档列表 HTTP 200，使用现有 PDF 做去重式上传返回 HTTP 201。真实 Qdrant 代际切换仍未放行。
- **018 Task06 真实候选索引重建与运行时验证** ｜ 实施中 → 实施中 ｜ 2026-09-10：修复 manifest schema 投影、默认 v2 LLM 注入、scroll 顺序、Qdrant cosine dense 指纹量化及早期失败候选清理；真实 run `fa5b0ce87f3e4e549409c65401c33e0c` 已完成当前 1 条权威 metadata 的 402-point 重建，alias/finalize/generation marker 一致，服务健康、知识库健康与文档列表均 HTTP 200。完整双格式与性能验收仍待执行，Spec018 保持实施中。
- **018 Task06-B 第二代真实重建与 finalize 恢复** ｜ 实施中 → 实施中 ｜ 2026-09-10：修复旧 generation marker 阻止后续合法发布的问题，并以显式替换授权保持文件仓储 fail-closed；run `38efa91a33154fd097c61d1c745d408f` 经 `resume-finalize` 完成 415-point 重建，metadata 统计/源哈希已验证，alias 与 generation marker 一致。服务三个健康/文档接口 HTTP 200，全量回归 927 passed、1 skipped；完整双格式与性能验收仍待执行。
- **018 知识文档切片检查器与双向原文定位** ｜ 实施中 → 已完成 ｜ 2026-09-10：用户验证功能无问题并同意收口；最终验收通过，唯一最终全量回归为 `956 passed / 0 failed / 1 skipped / 38 subtests passed`，服务与 HTTP smoke 通过。Task 开发阶段按长期规则只跑定向测试；已知后台 v2 indexing 与 reranker disabled 遗留已记录，不影响已验证路径。
- **022 项目会话管理与自进化长期记忆** ｜ 新建 → 待确认 ｜ 2026-09-11：经 Grill with Docs 多轮确认，落盘项目/持久会话、全局与项目记忆、动态两屏消息加载、真实处理过程、RAG 编号来源、手机端和能力方法建议的完整边界；Task02 为桌面纵向 MVP，Task02–08 均保持待执行，确认前不修改业务代码。
- **022 项目会话管理与自进化长期记忆** ｜ 待确认 → 已确认 ｜ 2026-09-11：用户明确要求继续开发 Spec022，确认进入 Task02 桌面端项目记忆 MVP；其余 Task 仍按依赖顺序等待。

## 2026-09-09

- **015 安全顶会论文检索与知识库导入** ｜ 实施中 → 实施中（范围扩展）｜ 确认 catalog→import 架构割裂（新表 `search_jobs`/`search_results` 与旧表 `search_sessions`/`paper_candidates` 不互通，导致 catalog `search_id` 导入报 `SEARCH_NOT_FOUND`）与摘要缺失（USENIX 列表页无 abstract，894 篇 `abstract` 全空）两个真实缺陷；用户选 C：本轮回接通导入（含补 PDF 来源 + `usenix.org` 白名单），摘要抓取作为后续任务单独排期，不遗忘。
- **015 安全顶会论文检索与知识库导入** ｜ 实施中 → 实施中（缺陷修复）｜ 修复年份检索误报与错误提示不可读两类缺陷：后端 `INVALID_YEARS` 下发 `min_year/max_year`、前端年份上界对齐当前年并补六类错误码映射、失败态不再残留“正在检索…”、错误提示升级为告警条并加状态语义色与中性来源占位；异步全量 768 passed、ruff 156 无新增，spec 不标记已完成（验收签字未达成）。
- **015 安全顶会论文检索与知识库导入** ｜ 实施中 → 实施中（缺陷修复）｜ 2026-09-09：修复论文下载被 SSRF 对端复核误杀的根因——`_peer_from_response` 只查 `peername`，而 httpcore 以 `server_addr` 暴露远端地址，导致每次真实下载在拿到 HTTP 200 之后仍被判“无法复核实际连接地址”而以 `DOWNLOAD_BLOCKED` 拒绝；改为按 `peername` → `server_addr` 顺序取值（决策见 ADR-0003）。实测两篇 USENIX PDF 下载成功（3.34MB/21 页、19.6MB/18 页）；`test_paper_download.py` 23 passed（新增 4 条针对 httpcore 真实形状的回归）。既有 KB/API 用例失败与收集错误为环境缺 `jieba`/`fastapi`，与本次无关；spec 不标记已完成。
- **015 安全顶会论文检索与知识库导入** ｜ 实施中 → 实施中（缺陷修复）｜ 2026-09-09：修复下载放行后暴露的第二个真实缺陷——`tasks._guarded_run` 调用 runner 却不返回其结果，使 `run_index_task_sync` 恒为 None，导入/上传把**已经成功**的索引读成失败并报 `KB_IMPORT_FAILED`；改为传递 runner 返回值，异常时返回带 `error` 的字典。根因链：服务未重启导致旧代码仍在内存（无 `--reload`，须重启才生效）。实测批次 `25733b60` 重试后两篇均 `completed` 并落盘；补 2 条同步索引结果传播回归（原上传测试 mock 掉 `run_index_task_sync` 致其漏网）。全量 774 passed；spec 不标记已完成。
- **019 论文导入状态反馈一致性** ｜ 新建 → 待确认 ｜ 2026-09-09：用户反馈导入连贯性差（先弹"导入服务暂时不可用"、随后又显示"导入完成"；点"添加到知识库"报"搜索会话不存在，请重新检索"）。只读定位三类根因：①`paperImportStatus` 同一状态栏被单篇结果/异常/轮询进度三处覆写；②导入按 `search_id` 分组循环，一组失败即跳出致已成功批次状态被错误文案顶掉；③后端五处 `except Exception` 兜底把任何未预期异常统一报 503 `IMPORT_BATCH_UNAVAILABLE`，掩盖真实原因。另实测 `search_jobs` 均未过期、`search_sessions` 为空，故"搜索会话不存在"并非过期所致，其真实触发路径交由 Task02 只读定位。已建 spec 与 plans/019（Task02–05），等待用户确认后再动业务代码。
- **019 论文导入状态反馈一致性** ｜ 待确认 → 已确认 → 实施中 ｜ 2026-09-09：用户"处理吧"确认本 spec 并要求"主 agent 主导、子代理调用 0.00 倍率 hy3 模型执行"，随即启动 Task02（只读定位"搜索会话不存在"真实触发路径）。
- **019 论文导入状态反馈一致性** ｜ 实施中 → 已完成 ｜ 2026-09-09/10：Task02 判定结论 C——单篇导入只查 `search_sessions`（catalog 检索恒空）而误报 `SEARCH_NOT_FOUND`，已回退 `search_jobs` 与批量路径同构；Task04 将 5 处 `except Exception` 的 503 `IMPORT_BATCH_UNAVAILABLE` 兜底改为 `logger.exception` + 424 `IMPORT_BATCH_ERROR`（`DATABASE_LOCKED` 仍 503 retryable），并补齐 `SEARCH_NOT_READY` 使三类上下文错误互斥；Task03 以 `renderImportSummary()` 作为状态栏唯一入口、分组独立 try/catch、静默路径补反馈、`partial_success` 可区分，并修复评审 P1（计数累加器每轮重置、`currentRoundBatchIds` 限定本轮汇总）。需求/技术/验收三份评审通过（P0=0，遗留 P2 四项非阻塞）；运行时三类场景验收通过（单篇导入 `200 status=indexed`）；全量 786 passed。复盘落盘 `docs/sdd/retro/2026-09-09-import-status-feedback-and-503-masking.md`。
## 2026-09-10

- **020 零碎 bug 解决** ｜ 实施中 → 已完成 ｜ 2026-09-10：第 1 批两项（BUG-01 导入即时反馈与 0 批次文案、BUG-02 导入未提交 v2 索引）均经 hy3 子代理实现、两端评审通过（P0=P1=0）并运行时验收通过（导入新论文后 v2 由 indexing→indexed，进度 16→100）；全量 791 passed。复盘落盘 `docs/sdd/retro/2026-09-10-misc-bug-fixes-batch1.md`。容器 spec 保持开放，后续零碎 bug 可继续追加批次。"点批量导入没反应、点两次才提示且显示 0 个批次、卡片应立刻出现并带动画、导入论文 v2 恒为待索引"。只读定位：①前端 `setImportPhase('submitting')` 后未调用 `renderImportSummary()`，直到请求全部完成才渲染，且提交阶段用已创建批次数（本轮集合为空）故恒显 0；②导入路径 `KnowledgeBasePaperImportAdapter._default_indexer` 只建 v1 未提交 v2，而上传路径（`routes_kb.py:131`）会异步提交 v2，两条入口不一致——v2 并非"后台在构建"而是根本没提交。已建 spec 与 plans/020（Task02–04），等待用户确认后再动业务代码。
- **020 零碎 bug 解决** ｜ 已完成 → 实施中（追加 BUG-03）｜ 2026-09-10：用户反馈新回归——勾选 1 篇点"批量导入"后**自动跳转**到知识库，且该篇在"导入进度"面板**没有任何记录**（只剩计数）。经 grill with docs 定位：`app.js:1042-1044` 单篇发 `{search_id, candidate_id}`，后端 `routes_paper.py:725-730` 走 `_import_single_paper` 返回 `paper_id` 而非 `batch_id`；`app.js:1049-1052` directSuccess 分支**无条件** `jumpToKnowledgeBase(data.paper_id)`（内部 `showView('kb')` 隐藏 `#papers-view`），且该分支**从不调用任何渲染函数**。该行为非 BUG-01 引入（`git diff 60e71f3~1 60e71f3 -- frontend/app.js` 未触碰 1051 行），是 BUG-01 打通即时反馈后暴露的既有路径。用户确认修复边界（移除自动跳转、direct 论文入面板且不伪造批次号、保持未完成项可见、**仅改前端**）。已建 Task05 并实现：`paperState.directImports` + `renderDirectImports()`（`data-direct="1"` 容器、复用既有 class、点击式"在知识库中查看"为唯一跳转入口）、`?v=21→22`、新增 2 条契约测试。自测 `node --check` 通过、契约测试 13 passed；8000 端口被另一项目目录 `/Users/wjh/ResearchAgent` 的残留服务占用，改用 **8123** 启动并验证线上 HTML 为 `?v=22`、旧自动跳转写法 0 处。hy3 子代理连续 429 限流，改由主会话实现，评审（Task04）待限流恢复后补。
- **020 零碎 bug 解决** ｜ 实施中（追加 BUG-04）｜ 2026-09-10：用户报告批次 `61621ad2` 显示"失败"但状态栏永久停在"正在提交 1 个导入批次…"，点"重试失败项"长时间无反应。grill with docs 定位三处：①`app.js:947` 的 `paperState.importPhase !== 'submitting'` 守卫与 `setImportPhase`（908/950）互锁，使成功数为 0 时相位永远算不出 `failed`；②`app.js:1147-1151` 重试成功分支不刷新状态栏、无中间态；③后端 `retry_batch`（`paper_import_batch_service.py:434-439`）在请求线程内同步跑完整批，实测 ~120s，日志可见 3 次 retry 均为 200 但**没有任何 `GET /api/papers/imports/{id}`** 轮询请求。用户 Round1 五项全采纳推荐。已追加第 2 批 BUG-04 与 `plans/020/task-06-import-phase-and-retry-feedback.md`（**仅前端**，待用户确认后实施）。
- **021 论文导入异步化与进度反馈** ｜ 新建 → 待确认 ｜ 2026-09-10：BUG-04 只能止损相位与可见性，"进度为什么全程空白"与"为什么查不出失败原因"指向同一结构性问题，故单独立项。实测根因：②导入在 HTTP 请求线程内同步执行 → 轮询永不触发、UI 承诺的进度物理上不成立；②`data/kb/qdrant` 被**另一个同项目 uvicorn 实例（8002）独占**（本机另开客户端直接抛 `RuntimeError: ... already accessed by another instance`），KB 写入/索引全失败并被压成无差别 `KB_IMPORT_FAILED`，用户看到的是不可行动的"论文导入失败"。spec 已建并配套 `plans/021/`（Task02 后端异步执行器 / Task03 `KB_STORAGE_LOCKED` + 单条目重试路由 / Task04 前端真实轮询·取消·软超时 / Task05 评审部署复盘），等待用户确认。同期按用户要求把全部角色子代理（`architect`/`planner`/`doc-updater`，其余已是）模型统一为 `hy3` 并同步 `AGENTS.md` 选型表。
- **020 零碎 bug 解决** ｜ 实施中（BUG-04 已确认 → 实施）｜ 2026-09-10：用户"1 确认，2 停掉"确认第 2 批 BUG-04；Task06 转 `进行中` 并分派 `frontend-dev`（hy3）实施。
- **021 论文导入异步化与进度反馈** ｜ 待确认 → 已确认 ｜ 2026-09-10：用户同批确认。并已停掉占用 `data/kb/qdrant` 的多余实例（原端口 8002，PID 28591），重启 8123 后 `health=200`、启动日志**不再出现** `already accessed by another instance` 告警，本机另开 Qdrant 客户端亦可正常打开（`OPEN OK: ['papers','paper-discovery-catalog']`）——即导入失败的近因已解除，为运行时验收扫清环境阻塞。实施顺序：spec-020/Task06 → 021 Task02 → 03 → 04 → 05。
- **020 零碎 bug 解决** ｜ 实施中 → 已完成 ｜ 2026-09-10：第 2 批 BUG-04 由 `frontend-dev`（hy3）实现（相位改为 `submitInflight`/事实重算、重试全程可见）；`frontend-reviewer` 首轮打回 P1（提交期误显红色"导入未完成"）→ 修复后复审通过；`node --check` OK、契约测试 22 passed；验收通过（因 `tester` 429 由主会话代行并留痕）。复盘 `docs/sdd/retro/2026-09-10-import-sync-and-qdrant-lock.md`。容器 spec 保持开放。
- **021 论文导入异步化与进度反馈** ｜ 已确认 → 实施中 → 已完成 ｜ 2026-09-10：Task02 入队即返回 + 后台单飞执行 + 恢复（`POST` 0–1 秒返回 `queued`，轮询到 `completed`）；Task03 `KB_STORAGE_LOCKED` / `DUPLICATE_IMPORT` 两类可行动错误 + `POST /api/papers/import-items/{id}/retry`（含重试路径唯一索引冲突可读化，424→409）；Task04 前端逐条进度 + 单条重试 + 取消 + "仍在导入"软提示（`?v=24→25`）。后端 819 passed、前端契约 22 passed；技术评审通过（3 LOW + 1 INFO）、前端评审通过、验收通过（tester 429 → 主会话代行留痕）。遗留：失败条目是否释放 `import_item_title` 唯一性，待另行评审。
- **021 论文导入异步化与进度反馈** ｜ 已完成 → 已完成（追加 Task06）｜ 2026-09-10：用户就遗留语义拍板"**释放**"，Task06 由 `backend-dev`（`Deepseek-V4.1-Flash`）实施完成——`paper_import_schema_meta` v1→v2 幂等迁移（受事务保护、失败可回滚），`import_item_title` 等 5 个身份索引的 WHERE 收缩为**仅活跃态**，CAS/租约未动。全量 **830 passed, 0 failed**；相关三文件 54 passed。运行时（8123）：真实库 version 1→2、索引 WHERE 仅活跃态；已入库论文重新导入由 409 变为 **200 queued → completed**，item 复用既有 `paper_id`，`papers.json` 同名条目仍为 1（无重复落盘）；同一候选连续提交仍 200 + **409 `DUPLICATE_IMPORT`**（活跃态互斥保留）。需求评审（`architect`）**打回 3 P1**（边界口径/find_existing 适用范围缺区分、评审记录与状态矛盾、Task06 缺产品级验收）→ 架构师已按 R1-1/R1-2/R1-3 修订 spec 与 task 文本，待复审。同期按用户要求把全部子 agent 模型由 `hy3` 改为 **`Deepseek-V4.1-Flash`** 并同步 `AGENTS.md`。
- **021 论文导入异步化与进度反馈** ｜ 已完成（Task06 收口）｜ 2026-09-11：`backend-tester` 单端回归通过（全量 **830 passed** 3 连跑 0 failed、ruff 无新增、Task06 新增用例 11/11 稳定）；顺带定位并修复**既有 flaky**（非本次引入，在父提交 `1ec85eb` 上 15 次复现 10 次）：`test_batch_status_and_resume_use_server_snapshot` 只等条目状态、未等批次聚合态 → 改为"条目 + 批次聚合双条件"等待（`_wait_for_batch_status`），同文件 10 处同类轮询一并收敛，修复后全量 3 连跑均 830 passed。需求评审复审**通过（APPROVE）**；`tester` Task06 补充跨端验收**通过**（5/5）。spec-021 全任务（01–06）完成。
- **022 项目会话管理与自进化长期记忆** ｜ Task02 实施中 → Task02 已完成、Spec 实施中 ｜ 2026-09-11：桌面端项目/会话/项目记忆纵向 MVP 通过 35 项精确测试、旧聊天兼容回归与受控部署 smoke；全量回归保留至 Task08，进入 Task03。
- **022 项目会话管理与自进化长期记忆** ｜ Task03 实施中 → Task03 已完成、Spec 实施中 ｜ 2026-09-11：项目/会话生命周期、全局/项目记忆治理、移动确认与删除边界通过后端/前端复审、跨端 API smoke 和定向测试；全量回归保留至 Task08，进入 Task04。
- **022 项目会话管理与自进化长期记忆** ｜ Task04 待执行 → Task04 实施中 ｜ 2026-09-11：Task03 已收口，启动异步记忆整理、候选/摘要 checkpoint 与跨会话预算受控召回；前端仅在需要候选确认时追加。
- **022 项目会话管理与自进化长期记忆** ｜ Task04 实施中 → Task04 已完成、Spec 实施中 ｜ 2026-09-11：SQLite v3 事件/摘要/checkpoint、Map/Reduce、stale 恢复、候选证据门和预算召回通过 backend-reviewer GO 与 backend-tester PASS；保留 worker 重启扫描 P2，进入 Task05/Task07。
- **022 项目会话管理与自进化长期记忆** ｜ Task05 待执行 → Task05 实施中 ｜ 2026-09-11：Task04 已收口，启动项目文档关联、既有 RAG 来源和完整处理过程展示；严格复用知识库 facade 与真实 progress 事件。
- **022 项目会话管理与自进化长期记忆** ｜ Task05 实施中 → Task05 已完成、Spec 实施中 ｜ 2026-09-11：项目文档关联、项目隔离 RAG、真实处理步骤和延迟来源展示完成；后端 130 项、前端 44 项定向测试通过，双端复审与跨端验收通过，部署 smoke 已验证，进入 Task06。
- **022 项目会话管理与自进化长期记忆** ｜ 已确认 / Task05 已完成 → 待确认 / Task05 修复轮待确认 ｜ 2026-09-11：部署后用户确认消息 turn 顺序、处理过程位置/折叠/永久动画及项目侧栏存在缺陷；经 Grilling 确认稳定 parent turn、真实步骤原位状态机、回答后异步无限条目记忆分析（默认独立 `qwen3.5:9b`）、分页确认区和 ChatGPT 式项目/会话侧栏。数据模型、接口与用户行为已更新，确认前暂停业务代码和 Task06。
- **022 项目会话与长期记忆** ｜ 待确认 / Task05 修复轮 → 实施中 ｜ 2026-09-11：用户确认共同理解并授权主 Agent 调度 Luna high 子 Agent 开始后端、前端修复实现，进入接口对齐、评审和针对性验收。
- **022 项目会话与长期记忆** ｜ Task05 修复轮实施中 → Task05 已完成、Spec 实施中 ｜ 2026-09-11：后端/前端 reviewer 均 GO，tester 跨端验收 PASS；主环境 health/home smoke 通过，修复相关定向测试 121 passed。Task06 仍待执行，Spec022 不提前收口。
- **022 项目会话与长期记忆** ｜ 实施中 → 待确认（Task09 增量） ｜ 2026-09-11：用户现场截图确认 Task05 侧栏仍存在双项目标题、常驻创建表单、菜单裁剪、平级会话和手输项目名称问题。经 Grilling 冻结 ChatGPT 式项目树、可搜索已有项目选择、统一弹窗及归档视图，并按用户要求拆为独立 Task09；确认前暂停业务代码和 Task06。
- **022 项目会话与长期记忆** ｜ 待确认（Task09 增量） → 实施中（Task09） ｜ 2026-09-11：Task09 需求评审与技术评审均 GO，用户明确授权实施；冻结 `last_activity_at DESC, project_id DESC` 与同键 cursor，临时采用 Terra medium 总控和 Luna high 子 Agent 开发。
- **022 项目会话与长期记忆** ｜ 实施中（Task09） → 实施中（Task09 已完成） ｜ 2026-09-11：单一桌面项目树、项目内会话归属、可搜索已有项目选择、浮层菜单、归档筛选和项目活动排序完成；后端/前端复审均 GO、tester 定向验收 PASS（47 passed），主 Agent 扩展受影响测试 81 passed，并完成 Chromium 交互 smoke（含取消弹窗修复）。全量回归明确留待 Task08，Spec 不提前收口。
- **022 项目会话与长期记忆** ｜ 实施中（Task09 已完成） → 待确认（Task10 增量） ｜ 2026-09-11：用户现场验证发现管理页点击会话不切回对话、展开项目时名称被旧双列布局挤压，并提出项目文件夹状态图标、project-first 记忆与最高优先级用户系统规则。经 Grilling 确认无历史版本、不做全局记忆降级、真正 system-role 注入及失败关闭；Task10 已落盘，确认前不改业务代码。
- **022 Task10 技术门禁** ｜ NO-GO → 待复审 ｜ 2026-09-11：技术评审指出统一 role-aware 接缝、原文 global 门禁、SystemRule v6/fail-closed、管理页状态快照和 SVG 可访问性契约不足；已将 T1–T6、入口清单、fixture 矩阵、稳定错误语义和文件白名单补入 Task10，等待复审。
- **022 Task10 技术门禁** ｜ 待复审 → 复审通过、待用户确认 ｜ 2026-09-11：临时 Luna high 技术复审确认 T1–T6 已具体冻结，四类用户可见入口、原文 global 门禁、SystemRule v6/Unicode/稳定错误体/fail-closed/快照、桌面状态恢复、单列 SVG aria 及文件白名单均可实现且可测；当前业务代码仍保持实施前基线，须用户明确确认后进入实现。
- **022 项目会话与长期记忆** ｜ 待确认（Task10 增量） → 实施中（Task10） ｜ 2026-09-11：用户明确要求继续开发；需求评审 GO、技术复审 GO，按 Task10 T1–T6 契约分派 Luna high 后端与前端实现。Task06–Task08 保持待执行，全量回归仍留在 Task08。
- **022 项目会话与长期记忆** ｜ 实施中（Task10） → 实施中（Task10 已完成） ｜ 2026-09-11：Task10 后端/前端实现、双端 reviewer GO、定向验收 PASS（64 项后端、44 项前端、5 个 Node 合同），受控服务 health/home/system-rule smoke 与 Chromium 无头 DOM 检查通过；Task06–Task08 继续等待，未执行全量回归。
- **022 项目会话与长期记忆** ｜ Task06 待执行 → Task06 实施中 ｜ 2026-09-11：Task10 已完成并提交，Task06 依赖满足；按既定范围启动手机端前端适配，仅分派 frontend-dev，不新增后端接口。
- **022 项目会话与长期记忆** ｜ Task06 实施中 → Task06 已完成 ｜ 2026-09-11：Task06 前端适配及 P1/P2 修复完成，reviewer GO、tester 定向验收 PASS（49 项合同、5 个 Node 合同），主 Agent 390×844 Chromium DOM smoke 通过；Task08 仍负责全量回归与最终交互。
- **022 项目会话与长期记忆** ｜ Task07 待执行 → Task07 实施中 ｜ 2026-09-11：Task06 已提交并收口，Task07 依赖满足；按既定范围启动能力方法记忆与只读 Skill 改进建议实现，不授予运行时文件写权限。
- **022 项目会话与长期记忆** ｜ Task07 实施中 → Task07 已完成 ｜ 2026-09-11：Task07 后端实现及两轮 P1 修复完成，reviewer GO、backend-tester PASS（12 项 Task07、43 项受影响回归、worker smoke 1 项、综合边界探针），Task08 继续负责全量回归、部署与 Spec 收口。
- **022 项目会话与长期记忆** ｜ Task08 待执行 → Task08 实施中 ｜ 2026-09-11：Task02–Task07、Task09–Task10 均已完成并提交，启动最终前后端范围审计、全量回归、部署与收口验收；此前各 Task 均未运行全量回归。
- **022 项目会话与长期记忆** ｜ Task08 实施中 → Task08 已完成 ｜ 2026-09-11：后端/前端最终复审 GO；修复 SSRF 共享边界、SystemRule fail-closed、记忆门禁测试基线、KB inventory digest 与资源合同后，唯一最终全量回归 1168 passed、1 skipped、5 warnings、41 subtests，退出码 0；8001 部署与桌面/手机 DOM smoke 通过。
- **022 项目会话与长期记忆** ｜ 实施中（Task08） → 已完成 ｜ 2026-09-11：Task02–Task10 全部收口，验收报告与复盘已落盘；本机 Ollama `models=[]` 导致成功对话 SSE/RAG 仅保留为环境待复验，不伪造成功证据。
- **024 可见推理过程与会话级推理档位** ｜ 新建 → 待确认 ｜ 2026-09-11：经 Grilling 确认默认 xhigh、会话级五档选择、过滤后推理流、自动折叠、一次性删除旧会话及预热模型 20 秒验收边界；Spec 与 Task02–05 已落盘，确认前不修改业务代码。
- **025 会话上下文压缩与 Token 预算管理** ｜ 新建 → 待确认（占位待调研） ｜ 2026-09-11：登记当前缺少历史摘要替换、上下文压缩和 token 预算管理；按用户要求仅创建占位 Spec，不创建 Task、不实施，也不作为 Spec024 依赖。
- **024 可见推理过程与会话级推理档位** ｜ 待确认 → 待确认（评审打回） ｜ 2026-09-11：临时 Luna high 需求评审发现 8 项 P1，技术评审发现 4 项 P0、5 项 P1；暂停代码开发，补充能力映射、schema v7 清理矩阵、SSE event_seq/终态、历史字段、LangChain/direct 一致性和观测隔离后重新评审。
- **024 可见推理过程与会话级推理档位** ｜ 待确认（修订后复审） → 待确认（再次打回） ｜ 2026-09-11：需求复审仍有 2 项 P1（能力接口失败体、SSE 完整字段/计时/中间失败序列），技术复审仍有 3 项 P0（五档双路径映射、schema v7 marker/Preference DDL/回滚、逐事件 event_seq 状态映射）；继续暂停业务开发，补齐最后合同后再复审。
- **024 Task04 前端推理档位与思考面板** ｜ 待执行 → 进行中 ｜ Task03 后端定向测试、独立评审和验收通过（条件）；启动五档选择器、SSE 思考面板、终态折叠与历史恢复实现，Task05 前不运行全量回归。
- **024 Task04 前端推理档位与思考面板** ｜ 进行中 → 已完成（定向通过）；Task05 进行中 ｜ frontend-reviewer GO、frontend-tester PASS，24 个前端合同用例通过；真实 SSE 浏览器 smoke 因服务/Ollama 不可用留给最终收口，不提前声称全功能验证。
- **024 Task05 最终评审、全量回归与部署** ｜ 待执行 → 进行中 ｜ Task04 定向评审 GO、前端验收 PASS 后启动双端复审、唯一全量回归、真实 Ollama 三档 smoke、部署和 Spec024 收口；Task05 前不声称完成。
- **024 可见推理过程与会话级推理档位** ｜ 实施中 → 已完成（环境延期） ｜ Task05 完成双端 GO、全量回归 1341 passed/1 skipped/47 subtests、部署 health/home、Chromium 资源与 fake adapter 终态验收；真实 Ollama chat 的 xhigh/low/off telemetry 因固定通道 20 秒超时延期，复验步骤已写入验收报告，不以超时阻塞代码收口。

## 2026-09-12

- **027 Research Task 动态编排 MVP** ｜ 已确认（Task03 完成） → 已确认（Task04 实施中） ｜ 2026-09-12：Task03 后端纵向切片已完成并复审通过，按用户继续开发指示启动 Task04；本轮只推进前端研究工作台、SSE 恢复与会话入口，临时使用主会话 Luna xhigh / 子代理 Luna high，不改写长期模型规则。
- **027 Research Task 动态编排 MVP** ｜ 已确认（Task04 实施中） → 已确认（Task04 完成，Task05 待执行） ｜ 2026-09-12：Task04 研究入口、独立工作台、SSE event_seq 去重/重连、取消与安全报告展示完成；补齐 report selections 白名单投影及 Worker 模型/槽位事件字段。前端验收 PASS（101 个 Python 合同、5 个 Node 合同、20/20 静态断言），后端定向回归 90 passed + 5 subtests，复审 GO；本地备用端口桌面入口 smoke 通过，390px 运行时 smoke 延 Task06。临时模型选择仅用于本轮分派，不写入长期规则或模型注册。
- **027 Research Task 动态编排 MVP** ｜ 已确认（Task04 完成，Task05 待执行） → 已确认（Task05 实施中） ｜ 2026-09-12：Task04 依赖已满足，启动 Task05 的 Re-plan、报告、模型升级与集成；按前后端分端并行分派，临时使用 Luna high，不修改长期模型规则或记忆。
- **027 Research Task 动态编排 MVP** ｜ 已确认（Task05 实施中） → 已确认（Task05 实施中） ｜ 2026-09-12：完成第二阶段后端接线与 focused 验证：软预算阶段闸门、`budget_exhausted` partial 收敛、`MODEL_ESCALATED` 安全 model 事件（含 search-worker 路径）；后端 95 passed + 5 subtests，未修改 Spec 范围或长期模型配置。

- **020 零碎 bug 解决** ｜ 已完成（第 3 批） → 实施中（第 4 批 BUG-06） ｜ 2026-09-12：追加第 4 批 **BUG-06**——从「模型库」等视图点「新建对话」不切回对话视图。根因：`beginDraft()`（`app.js:1102-1110`）只重置会话内容、**从不调用 `showView()`**，而视图切换依赖原生 `hidden` 属性（`app.js:2831-2836`），故 `#chat.hidden` 一直为 `true`；对照 `openConversation()`（`app.js:1063`）首行即有 `showView('chat')`。用户经 grill with docs 确认边界后批准实施。
- **020 零碎 bug 解决** ｜ 实施中（第 4 批 BUG-06） → **已完成（第 4 批）** ｜ 2026-09-12：`frontend-dev` 实现——① `app.js:1103` 在 `beginDraft()` 首行前置 `showView('chat')`（覆盖 `1589`/`1651`/`1170` 三个调用点）；② 7 处「新会话」→「新对话」（`app.js:879/880/882/1105/1106`、`index.html:52/74`）；③ `index.html:492` `app.js?v=33`→`?v=34`、491 行兼容注释追加 `v33`。`frontend-tester` 验收通过：`node --check` OK、前端契约 pytest **35 passed / 0 failed**、`grep "新会话"` 0 命中、`git diff` 无夹带。架构师另用 Playwright+Chromium 在 127.0.0.1:8300 做真实点击验证：模型库 → 新建对话 后 `#chat.hidden=false`、`#models-view.hidden=true`、`activeNav=['chat']`、`page_errors=[]`、加载 `app.js?v=34`。**未跑全量回归**（单端改动，按规则只跑前端回归）。
- **020 零碎 bug 解决** ｜ 已完成（第 4 批） → 实施中（第 5 批 BUG-07） ｜ 2026-09-12：追加第 5 批 **BUG-07**（创建项目后的多余灰色提示常驻不消失；「在此项目中新建对话」点击不跳转）。用户确认修复边界后实施。
- **020 零碎 bug 解决** ｜ 已完成（第 5 批） → 实施中（第 6 批 BUG-08） ｜ 2026-09-12：追加第 6 批 **BUG-08**（侧边栏分区标题颜色/对齐不一致、`requirements.txt` 缺 3 个运行时依赖、静态资源无缓存头）。经 grill with docs 确定边界并由用户裁决后实施。
- **020 零碎 bug 解决** ｜ 实施中（第 6 批 BUG-08） → **已完成（第 6 批）** ｜ 2026-09-12：A 侧边栏三标题统一为 `--muted` 色 + 左侧顶格（`styles.css:8/140`，实测 `color` 全 `rgb(139,142,150)`、`left` 全 18px，「项目」仍可展开）；B `requirements.txt` 补 `jsonschema`/`PyYAML`/`pydantic`，`jsonschema` 从 dev 移出，lock 补 `jsonschema==4.26.0`；C `main.py` 加 `NoCacheStaticFiles`（`Cache-Control: no-cache`，ETag 协商 304，13 条 `?v` 断言 79 passed / 0 failed），并按惯例联动刷新 spec-018 冻结清单（`main.py` sha256 与 `inventory_digest`，diff 仅 2 行，`test_kb_upload_closure_matrix.py` 2 passed）。**注**：全量回归受沙箱影响（`pytest-of-unknown` EEXIST）出现 403 errors，已改用 `--basetemp` 重跑，结论以重跑结果为准。
- **020 零碎 bug 解决** ｜ 实施中（第 5 批 BUG-07） → **已完成（第 5 批）** ｜ 2026-09-12：① 删除创建项目后的 `setConversationStatus('已创建项目：…')`；② `setConversationStatus()` 加超时自动清除（非 error/loading 4 秒清空，error/loading 常驻，含定时器抢占）；③ 「在此项目中新建对话」回调补 `beginDraft()`（复用 BUG-06 的 `showView('chat')`）；④ 补 `155`/`1084` 两处 loading 显式标记。验收：`node --check` OK、契约 pytest 35 passed / 0 failed（交叉 `-k frontend` 84 passed）、Playwright 实跑 8 项全 PASS、测试数据已清理。**未跑全量回归**（单端改动）。
- **025 会话上下文压缩与 Token 预算管理** ｜ 待确认（占位待调研） → 待确认（正式设计已落盘） ｜ 2026-09-11：两轮 Grilling 收敛后重写 Spec——立项理由由"防窗口溢出"改为"输入 token 预算与首 token 延迟"，冻结装配预算 8000 估算 token、达 80%（6400）触发后台异步压缩（本次不阻塞、下一条消息生效）、输入框占比指示与一键手动压缩、messages append-only + 读时装配、规则化分段摘要与统一 `chars/1.6` 计量；新增 `plans/025/README.md` 与 Task02–06。状态仍为待确认，未确认前不实施；用户已裁定不修订 Spec024、不与其耦合。
- **025 会话上下文压缩与 Token 预算管理** ｜ 待确认（正式设计已落盘） → 已确认（进入实施） ｜ 2026-09-12：技术评审复审通过（P0×3、P1×6 全部关闭，无新增 P0），用户明确指示开始实施；按 Task02（计量与预算配置）→ Task06（评审回归部署）顺序执行，实施前已完成 pull。
- **025 会话上下文压缩与 Token 预算管理** ｜ 已确认 → 实施中（Task02–Task05） ｜ 2026-09-12：完成计量与预算配置、两张新表与迁移、装配消费改造与异步 worker、context-usage/compactions 端点与 80% 自动触发、前端占比条与一键压缩按钮（`?v=33→34`）；新增测试 52 项。
- **025 会话上下文压缩与 Token 预算管理** ｜ 实施中 → 已完成 ｜ 2026-09-12：需求/技术/后端/前端/验收五份评审全部落盘并通过；唯一最终全量回归 1345 passed、1 skipped、47 subtests（唯一失败 `test_import_compensation` 已用 git stash 在干净树复现，属存量）；服务部署于 http://127.0.0.1:8000 并通过运行时 smoke；真实对话触发自动压缩因本机 Ollama 无可用模型未端到端验证，列为环境待复验，不伪造证据。

## 2026-09-12

- **027 Research Task 动态编排 MVP** ｜ 新建 → 待确认 ｜ 经 Grilling 共同确认深度研究入口、稳定 LangGraph 控制骨架、运行时 Task Graph、USENIX/DBLP 并行搜索、有界 Re-plan、动态模型路由、内存感知 9B Worker、初步报告和实时任务工作台；Spec 与 Task02–06 已落盘，确认前不实施。
- **028 Research Task 可靠调度、计划版本与恢复** ｜ 新建 → 待确认 ｜ 登记全局公平调度、唯一租约、checkpoint、计划版本、暂停/取消/审批和单机多进程恢复；依赖 Spec027，Spec 与 Task02–06 已落盘。
- **029 Research Task 全文获取与知识库联动** ｜ 新建 → 待确认 ｜ 登记用户确认后的安全下载、既有批量导入、全文 RAG 和可定位证据升级；硬性禁止复制下载、安全、导入、解析和索引实现，Spec 与 Task02–06 已落盘。
- **030 跨论文证据矩阵与深度研究报告** ｜ 新建 → 待确认 ｜ 登记 Claim/Evidence、冲突与缺口矩阵、版本化只读报告、引用 manifest 及 Markdown/HTML/JSON 产物；Spec 与 Task02–06 已落盘。
- **031 动态模型路由与资源调度优化** ｜ 新建 → 待确认 ｜ 登记 Langfuse 指标反馈、shadow policy、内存感知 Worker 扩缩和单/多 Ollama 实例基准；多实例只有实测 GO 才实现，Spec 与 Task02–06 已落盘。
- **032 Research Task 数据源与安全会议扩展** ｜ 新建 → 待确认 ｜ 登记统一 Source Adapter、字段 provenance、OpenAlex/Crossref 以及 IEEE S&P、ACM CCS、NDSS 官方目录；搜索阶段不下载 PDF，Spec 与 Task02–06 已落盘。
- **032.1 USENIX Skill 解耦与详情页摘要补齐** ｜ 新建 → **已确认** ｜ 2026-09-12：经 `grill-with-docs` 三轮访谈冻结 Q1–Q6 后确立 Skill（编排层）/ Tool（执行层）分层。本次落地三条互不耦合的改动线——① **新增两个编排 Skill** `usenix-catalog-orchestration` / `usenix-download-orchestration`（只写适用范围、输入契约、编排决策点、固定发现链/下载链、领域边界、停止条件），**旧 Skill `usenix-accepted-papers` / `usenix-paper-catalog-search` 原样保留并加遗留标记**，待论文检索模块迁移后再废弃；② 在确定性代码中补齐 presentation **详情页摘要**抓取与 `fetch_paper_detail` Tool，摘要走 fill-if-missing（仅填补缺失、不覆盖列表页已有值），使结果卡片展示真实摘要而非 `abstract_status: missing`；③ **非领域规则归位与 Skill 编写边界**（Task06）——逐条核对确认「每次 ≤2 代码文件/≤150 行、回传字段清单、进展日志路径、先回传代码后回传说明、Git 禁止项、子模型指挥与编排」**在 `AGENTS.md` 中早已存在**，`.sdd/runtime/task-ledger.sqlite3` 回填因能力未实现（spec-016 task-04 待执行）**不迁移**，`junior-dev` 引用因角色不存在**删除**，故本次**不是搬家**；真正缺口已补上——`AGENTS.md` 新增 `## Skill 编写边界（防污染）` 小节，明确 Skill 只写领域编排协议、四类禁止写入内容（研发分派纪律 / 研发台账回填 / Git 操作禁止项 / 不存在的角色名与 spec·plan 过程文档引用）、唯一落点分层归属，并列出真实存在的 10 个角色且注明**不存在 `junior-dev`**。`.codebuddy/agents/*.md` 经核对无 `junior-dev` 引用、与 `AGENTS.md` 不矛盾，**未作改动**。三份评审仍为「待评审（未执行）」，收口阶段补齐后本 spec 才可转 `已完成`。
- **033 USENIX 解析器与真实页面结构对齐** ｜ 新建 → **已确认** ｜ 2026-09-12：用户排查「USENIX 检索降级是否由另一个 agent 的 spec-032.1 改动引起」，结论为**无关**——把 spec-032.1 对 `usenix_paper_parser.py` 的在途改动 `git stash` 掉后，同一真实页面**仍**抛 `USENIX_PARSE_FAILED`。实测两条独立断链：① **列表页** `_Blocks`（`usenix_paper_parser.py:255-260`）只在 `tag == "p"` 时匹配字段类名，而真实 USENIX 列表页把类名放在**外层 `<div class="field field-name-field-paper-people-text …">`** 上、内层 `<p>` 无 class → 4 个真实列表页（2022 technical-sessions 256 篇 / 2022 summer 97 篇 / 2024 summer 82 篇 / 2025 cycle1 245 篇）**全部 0 作者 0 摘要**，目录库 `catalog_papers` 894 行中 **894 行 `authors_json` 为空（100%）**，摘要仅缺 17 行；② **详情页** `parse_usenix_detail`（`:194`）硬性要求 `citation_author` 与 4 位年份，而 USENIX 的 `citation_*` meta 块**按页条件输出**（挂 PDF/会议录才有），无该块的页面字段在 `<h1 id="page-title">`、`.field-name-field-paper-people-text`、URL 会议代号里，解析器都不看 → `usenixsecurity22/presentation/maia`、`usenixsecurity24/presentation/{xie-xiang,liu-fengrun}` 全部失败（对照 `zhang-qingzhao` 有 21 个 `citation_author` → 解析成功）。**只要求 1 个 detail 单元失败，整个检索任务即标 `degraded=True`（status=partial）**。用户选择「新建 bug spec 再分派修复」，并认可修复范围：列表页字段匹配放宽到任意元素、详情页补三级回退、fixture 换成真实 DOM。已落盘 spec 与 `plans/033/README.md` + 三个 task 文件（Task02 列表页 / Task03 详情页 / Task04 评审回归验收）。**并发送风险提示**：`usenix_paper_parser.py` 工作区已有 spec-032.1 未提交改动，本 spec 只允许在其之上追加分支，禁止整文件重写与 `git checkout`。
- **033 USENIX 解析器与真实页面结构对齐** ｜ 已确认 → **已完成** ｜ 2026-09-12：三道门禁全部走完并签字放行。**实现**（`backend-dev` 三轮，只改 `usenix_paper_parser.py` 单文件、只在其上追加）：① 列表页字段匹配由「`tag == "p"` + 子串包含」改为「任意元素的 class **token 交集**」（`_field_kind()` + 开标签深度栈 `_pop_open_tag`），并只取 people 字段**首个 `<p>`**（`_open_people_paragraph`/`_close_people_paragraph`）、排除 `<em>` 单位文本、把 `,` / `, and ` 归一为 `;` 后再交给函数体未改的 `_split_authors`；② 详情页标题链补 `citation_title → og:title → h1 → <title>`（`_Page` 把 `meta["h1"]` 从 `meta["title"]` 拆出）并加受保护的 `_without_site_suffix()`，作者回退**复用列表页 `_Blocks`**（`_DETAIL_ARTICLE_CLASSES = ("node-paper","view-mode-full")`），年份补 URL 会议代号，fail-closed 判定与 `USENIX_PARSE_FAILED`/`retryable` 未动；③ fixture 换成真实 DOM（类名在外层 `<div>`、内层 `<p>` 无 class），保留一条 `<p class=…>` 简写用例。**评审**：`backend-reviewer` 技术评审 **通过**（0 CRITICAL / 0 HIGH，2 MEDIUM + 2 LOW），两条 MEDIUM 经 `backend-dev` 整改并由主会话**独立探针**复现——摘要跨块级元素补分隔符（`'A.B.'` → `'A. B.'`，原 `in` 弱断言替换为 `==` 精确断言；`<em>` 内 `state-of-the-art` 不被切碎）、详情页作者块按 `presentation URL → title → [0]` 绑定（侧栏块在前不再静默取到 `Sidebar Person`）；parser 测试 42 → **47**。`architect` 需求评审 **通过（附意见）**（4 MEDIUM + 6 LOW + 1 INFO，含「承重行为未在 spec 授权」「验收场景 A 因缓存不可达」「执行配置模型名不在 `MODEL_REGISTRY`」等），本 spec 已按 P-01～P-11 回填（措辞、边界授权、验收口径、执行配置改为登记名 `qwen3.8:27b-mlx` / `qwen3.5:9b`）。**回归**：`backend-tester` 5 批 16 文件 **311 passed / 0 failed**。**端到端**：主会话失效化 2022 全部 178 个 fetch unit 并清空目录摘要以**强制真实重抓**（备份 `/tmp/fetch_units_backup_20260912-223229.json`、`/tmp/catalog_2022_backup_20260912-223346.json`）→ 检索 176 条、**失败事件 0**、`catalog_papers` 2022 作者 **176/176**、摘要 **176/176**、可疑作者 0、获奖标记 0（修复前为 894/894 作者为空）。`tester` 独立验收评审 **通过**（0/0/0，并覆盖了主会话草稿、纠正其对 `degraded` 机制的错误引述），`architect` 抽查复跑后**签字放行**。**关键归因**：`degraded=true` 并非解析器所致——10/10 结果 `rerank_score` 全为 `NULL`、事件流失败事件 0，且服务启动日志为 `Reranker 模型不存在：data/models/qwen3-reranker-0.6b-q8_0.gguf` / `将以 RRF 降级模式继续启动`；该 reranker 缺失属**独立环境缺口**，建议另立运维项，本 spec 按边界不改 `degraded` 判定策略。**未推送**：按用户裁决「先不推」，全部改动留在工作区，未做 `git commit`/`push`，以免与另一 agent 的 spec-032.1 在途改动交错。
- **027 Research Task 动态编排 MVP** ｜ 待确认 → 已确认（进入实施） ｜ 2026-09-12：技术评审（含需求维度）复审通过——移除 `paused` 并把暂停/恢复 defer 到 Spec028、钉死 `CatalogSearchGraph`/`CatalogRagAdapter` 复用接缝、补齐状态机/错误码词表/event_seq 原子领号/崩溃审计/独立库与应用层级联/ResourceProbe 冻结/论文不可信断言/OWNER_ID 隔离；用户指示开始开发，按 Task02→Task06 执行。
- **027 Research Task 动态编排 MVP** ｜ 已确认（Task02 完成） → 已确认（Task03 完成，实施中） ｜ 2026-09-12：Task03「持久化 Research Task 后端纵向切片」完成。新增 `backend/app/research/**` 限界上下文（domain/application/infrastructure 约 3530 行）+ `backend/app/api/routes_research.py` 9 端点 + 独立库 `data/research/research.sqlite3`（5 张业务表、幂等迁移、`event_seq` 同事务原子领号、外键全 RESTRICT + 应用层级联、崩溃收敛 `interrupted`）+ `platform/ollama.py` 的 `ResourceProbe`/`_GlobalWorkerScheduler` + `remove_project` 级联接线；`search_catalog` 严格复用 Spec015 `CatalogSearchGraph`/`CatalogRagAdapter`，未建第二套实现。Task 级评审：首轮**打回**（P0-1 Worker 额度 acquire/release 不配对致全局额度泄漏、P1-1 POST/GET 缺 spec 明文的会话/项目 404 校验与项目继承、P1-2 `data/research/` 未入 `.gitignore`、P1-3 交付报告缺失、P2×9），批量修复后**复审通过（附意见）**，复审新增 P2-A（memory 依赖故障裸 500）/P2-C（断言可静默失效）亦已关闭。定向测试 50 passed + Task02 门禁 38 passed（合计 88），ruff 干净，未碰 `frontend/**`。同时**追认** Task02 门禁复用接缝断言的精化（原「research 目录不得有任何 `.py`」与 spec 明文新增该上下文互斥，已改为更强的源码内容扫描）。延期交 Task05/Task06：新增码登记（`TASK_DELETED`/`RESEARCH_CASCADE_FAILED`/`INTERNAL_ERROR`）、`update_plan_status` 死代码（计划状态恒 `proposed`）、真实 1–4 个 9B 并发吞吐未实测。spec 状态不变（仍 `已确认`），待 Task04–06 完成后由 Task06 收口转 `已完成`。
## 2026-09-13

- **034 会话式深度研究与真实子 Agent Runtime** ｜ Task02 实施中 → Task02 实施中（后端实现完成，待评审/验收） ｜ 2026-09-13：完成研究库 schema v2（Session/Intake/Approval/AgentRun/Artifact/Notification）、状态机/稳定错误码/owner 隔离与幂等约束；MemoryRepository 在公开 v7 上加性升级 ProcessingStep v2（node/source-event 唯一索引、canonical `research-event:{task}:{seq}`、三级父链校验、投影重试标记），旧行保持 v1 可读。Task02 合同与 Spec027 受影响回归共 99 passed、5 subtests passed；ruff 未安装，已记录为环境限制，待 reviewer/tester 门禁后转已完成。
- **034 会话式深度研究与真实子 Agent Runtime** ｜ Task02 实施中（后端实现完成，待评审/验收） → Task02 实施中（P1 修复完成，待复审/验收） ｜ 2026-09-13：按 backend-review 关闭 P1：Session 创建强制既有 MemoryRepository 交叉校验并校验 draft ID；Task/WorkItem/continued Run owner/session 关系 fail-closed；ProcessingStep v2 多同 kind 子节点不再撞 v1 logical_sequence 唯一索引；Notification 先按 owner+idempotency_key 比 payload；补齐 parent-first replay seam 与 retry marker 语义。第二轮补齐未批准 Session 的 Task 绑定拒绝、Notification session-task 关系/完整身份幂等、ResearchStore/Memory replay canonical source_event_id 与跨 Task 拒绝。合同/受影响后端测试 146 passed、5 subtests，py_compile 与新增代码聚焦 Ruff 检查通过；全量 Ruff 仍仅报告 HEAD 已存在的 14 条 MemoryRepository 风格告警。
- **034 会话式深度研究与真实子 Agent Runtime — Task02** ｜ 实施中（P1 修复完成，待复审/验收） → 已完成 ｜ 2026-09-13：backend-reviewer 复审 GO、backend-tester 验收 GO；合同测试 12 passed，受影响后端回归 146 passed、5 subtests，运行时探针 5/5，py_compile、diff-check 和新增代码聚焦 Ruff 通过。全量 Ruff 仍仅有基线 14 条风格告警；Task03 可开始。
- **034 会话式深度研究与真实子 Agent Runtime — Task03** ｜ 待执行 → 实施中 ｜ 2026-09-13：Task02 已通过后端复审与验收，启动会话意图、Deep Research Skill 激活和多轮 Intake 实现；本阶段只跑 Task03 定向测试，不提前运行全量回归。
- **034 会话式深度研究与真实子 Agent Runtime — Task03** ｜ 实施中 → 实施中（后端实现完成，待评审/验收） ｜ 2026-09-13：完成 `deep-research-orchestration` Skill、主会话两阶段激活与可恢复 Intake；明确/含糊/普通请求、阻塞字段 provenance、重复消息幂等和活跃 Session 冲突合同通过 4 项定向测试，待独立后端评审与验收。
- **034 会话式深度研究与真实子 Agent Runtime — Task03** ｜ 实施中（后端实现完成，待评审/验收） → 实施中（P1 修复完成，待复审/验收） ｜ 2026-09-13：关闭 backend-review 5 项 P1：冲突交互 SSE、普通聊天依赖故障回退、消息先落库后模型预检、固定 Skill/Tool 授权校验、项目删除稳定异常体；新增合同覆盖并通过 Task03/会话/Skill 定向测试。
- **034 会话式深度研究与真实子 Agent Runtime — Task03** ｜ 实施中（P1 修复完成，待复审/验收） → 实施中（双端实现完成，待双端复审/跨端验收） ｜ 2026-09-13：前端复用既有会话消息流接入 `skill_activation`/`intake` SSE，安全展示 Skill 快照、字段 provenance、阻塞澄清和 active Session 三选一；done/error 终态可折叠，资源版本升至 v44。前端合同与全套静态回归 176 passed，报告落盘至 `docs/sdd/plans/034/artifacts/task-03/frontend-report.md`。
- **034 会话式深度研究与真实子 Agent Runtime — Task03** ｜ 实施中（双端实现完成，待双端复审/跨端验收） → 实施中（后端 P1-06 修复完成，待双端复审/跨端验收） ｜ 2026-09-13：消息查询从既有 MemoryRepository `processing_steps.detail_json` 恢复脱敏 Intake 投影（含 status/fields/missing/choices/question/skill 快照），补刷新恢复与普通消息无字段合同；后端定向回归 106 passed、6 subtests，py_compile/diff-check 通过，Ruff 仍仅有既存 5 条基线诊断。未新增存储或 ResearchTask/AgentRun。
- **034 会话式深度研究与真实子 Agent Runtime — Task03** ｜ 实施中（后端 P1-06 修复完成，待双端复审/跨端验收） → 已完成 ｜ 2026-09-13：backend-reviewer/backend-tester/frontend-reviewer/frontend-tester 全部 GO；后端 106 passed、6 subtests，前端 178 passed，跨端探针覆盖 Intake 分流、模型失败保留消息、Skill/Tool fail-closed、冲突三选一、历史投影恢复和终态折叠。未创建 ResearchTask、AgentRun 或计划；Task04 可开始。
- **034 会话式深度研究与真实子 Agent Runtime — Task04** ｜ 待执行 → 实施中 ｜ 2026-09-13：Task03 双端门禁全部通过，启动计划版本、统一审批命令与会话/Research Tab 审批卡；本阶段只运行后端/前端定向测试，不提前运行全量回归。
- **034 会话式深度研究与真实子 Agent Runtime — Task04** ｜ 实施中 → 双端实现完成、待双端评审/总验收 ｜ 2026-09-13：前端复用既有 assistant message/SSE 与 Research Tab，新增计划目标/范围排除/研究方向/来源能力/Agent/预算/结构/降级白名单卡片，三类审批及 revise/cancel/decline 统一提交 `/api/research-sessions/{id}/commands`；按钮支持 loading/success/error/stale/conflict 可观察与恢复。前端合同和全套前端静态回归 183 passed，node 语法、DOM/XSS/class/version、diff-check 均通过；报告落盘至 `docs/sdd/plans/034/artifacts/task-04/frontend-report.md`。
- **034 会话式深度研究与真实子 Agent Runtime — Task04** ｜ 实施中 → 已完成 ｜ 2026-09-13：backend-reviewer/frontend-reviewer 与 backend-tester/frontend-tester 全部 GO；后端 116 passed、6 subtests，activation/outbox/消息幂等 4/4 故障探针通过；前端合同 28 passed、全前端回归 186 passed、Fake-DOM/HTTP 探针 5/5。Task05 可开始。
- **034 会话式深度研究与真实子 Agent Runtime — Task05** ｜ 待执行 → 实施中 ｜ 2026-09-13：Task04 双端门禁通过，启动 ResearchAgentRunner、真实模型/Tool 接线、预算与 checkpoint 合同；本阶段只运行 Fake Runtime 与后端定向测试，不提前运行全量回归。
- **034 会话式深度研究与真实子 Agent Runtime — Task05** ｜ 实施中 → 已完成 ｜ 2026-09-13：backend-reviewer/backend-tester 均 GO；定向回归 211 passed、6 subtests，Fake/Store 探针 29 passed，覆盖能力快照、递归安全、checkpoint 绑定/续跑、取消 CAS、Tool 异常、扩容 hard caps、四次独立 attempt、Router metadata、唯一 Orchestrator 和 ResourceProbe lease。真实 Ollama HTTP 探针受沙箱限制，已如实延期记录；Task06 可开始。
- **034 会话式深度研究与真实子 Agent Runtime — Task06** ｜ 待执行 → 实施中 ｜ 2026-09-13：Task05 已通过后端复审与验收，启动论文目录接线、评估、Critic 与覆盖补偿；本阶段只运行 Fake/目录定向测试，不提前运行全量回归。
- **034 会话式深度研究与真实子 Agent Runtime — Task06** ｜ 实施中 → 实施中（后端实现完成，待评审/验收） ｜ 2026-09-13：新增唯一 `CatalogSourceFactory`，默认接入既有 Store、USENIX/DBLP source、`CatalogSearchGraph`/`CatalogRagAdapter` 与真实缓存路径；本地优先、不足增量刷新，Search Worker/Evaluator/Critic 结构化输出和严格 Tool 参数映射完成。Task06 及 Task05/02–04、Spec015/027/032.1/033 相关定向回归 232 passed、6 subtests；真实外部来源 smoke 留 Task10。
- **034 会话式深度研究与真实子 Agent Runtime — Task06** ｜ 实施中（后端实现完成，待评审/验收） → 实施中（P1 修复完成，待复审/验收） ｜ 2026-09-13：按 backend-review 关闭 source scope P1：`usenix` 只走 USENIX、`dblp` 只走 DBLP、`all` 才允许双源；DBLP-only SearchJob/候选按来源隔离，补合同测试并通过 233 passed、6 subtests，py_compile/Ruff/diff-check 均通过；真实外部 smoke 仍留 Task10。
- **034 会话式深度研究与真实子 Agent Runtime — Task06** ｜ 实施中（P1 修复完成，待复审/验收） → 已完成 ｜ 2026-09-13：backend-reviewer 与 backend-tester 均 GO；修复旧 `CatalogSearchGraph.__new__` fixture 缺少 `source_scope` 的兼容回归。Task06 与 Spec015/027/032/033、Skill/Tool 定向回归 384 passed、11 subtests，py_compile、Ruff、diff-check 全部通过；真实目录/Ollama/Qdrant smoke 留 Task10。
- **034 会话式深度研究与真实子 Agent Runtime — Task07** ｜ 待执行 → 实施中 ｜ 2026-09-13：Task06 后端复审与验收均 GO，启动 processing_steps 三级树与实时投影；先冻结后端 additive 迁移、父链校验、canonical event 幂等和 projector retry，再接前端树组件，阶段只运行定向测试。
- **034 会话式深度研究与真实子 Agent Runtime — Task07** ｜ 实施中（后端实现中） → 实施中（前端实现中） ｜ 2026-09-13：后端完成 Projector 真实接线、三级树严格校验、Skill/Tool 事件、SSE 安全与有界 retry drain；backend-reviewer/backend-tester 均 GO，定向回归 227 passed、5 subtests。冻结后端契约，转入前端树组件与实时交互。
- **034 会话式深度研究与真实子 Agent Runtime — Task07** ｜ 实施中（前端实现中） → 已完成 ｜ 2026-09-13：前端完成三级 ProcessingTree、乱序/upsert、终态屏障、滚动保护、Research Tab 复用、SSE raw/upsert 分流、XSS/ARIA/reduced-motion；frontend-reviewer/frontend-tester 均 GO，前端 193 passed、JS/DOM/diff-check 通过。真实浏览器跨端 smoke 因服务未启动留 Task10，不以 Fake-DOM 冒充成功。
- **034 会话式深度研究与真实子 Agent Runtime — Task08** ｜ 待执行 → 实施中 ｜ 2026-09-13：Task06/07 已通过双端门禁，启动 Synthesizer 报告 Artifact、会话幂等写回与应用内通知；先实现后端不可变版本/引用 manifest/安全 HTML/游标补发，再接前端报告与通知 UI，阶段只运行定向测试。
- **034 会话式深度研究与真实子 Agent Runtime — Task08** ｜ 实施中（后端实现中） → 实施中（前端实现中） ｜ 2026-09-13：后端完成唯一 Orchestrator→Synthesizer→Artifact/最终消息/通知接线，验证来源 allowlist、重试 Run 归因、空证据 partial、SSE 游标与安全下载；backend-reviewer/backend-tester 均 GO，定向回归 246 passed、5 subtests。转入前端报告与通知 UI。
- **034 会话式深度研究与真实子 Agent Runtime — Task08** ｜ 实施中（前端实现中） → 已完成 ｜ 2026-09-13：前端接入历史报告投影、Artifact 下载/HTML inline、五类通知、SSE 游标/read CAS 与跳转；backend/frontend reviewer 与 tester 自动化均 GO，后端 246+ 定向通过、前端 198 passed。真实浏览器 smoke 因服务未启动留 Task10，不以 Fake-DOM 冒充成功。
- **034 会话式深度研究与真实子 Agent Runtime — Task09** ｜ 待执行 → 实施中 ｜ 2026-09-13：Task08 双端自动化门禁通过，启动 Research Tab 统一 Session/ProcessingTree/报告组件、旧旁路入口移除与未绑定旧 ResearchTask 精确 dry-run 清理；阶段只运行双端定向测试，不提前全量回归。
- **034 会话式深度研究与真实子 Agent Runtime — Task09** ｜ 实施中 → 已完成 ｜ 2026-09-15：后端/前端最终复审均 GO。修复 Session→Task 项目绑定、创建幂等与消息去重、Session 游标分页、cleanup dry-run token 与跨库快照 fail-closed 回滚，以及真实会话标题和嵌套 Agent/Tool 摘要；后端 Task09 14 passed、相关回归 178 passed，前端 Task09 合同 8 passed、相关合同 20 passed，静态检查通过。真实浏览器/Ollama smoke 留 Task10，不以自动化替代。
- **034 会话式深度研究与真实子 Agent Runtime — Task10** ｜ 待执行 → 实施中 ｜ 2026-09-15：Task09 双端最终复审 GO，启动最终独立评审、唯一全量回归、真实 Ollama/浏览器 Smoke、部署和 Spec 收口复盘；只允许修复已确认范围内的 P0/P1，不新增 Spec028/030 范围。
- **034 会话式深度研究与真实子 Agent Runtime — Task10** ｜ 实施中 → 实施中（自动化通过，真实 Smoke 阻塞） ｜ 2026-09-15：修复未知 reasoning capability 503 契约和 Spec027 旧入口幂等消息兼容后，最终全量回归 `1863 passed、52 subtests`；真实服务与浏览器页面 HTTP 200，Intake→Plan→Approval→Runner→三级事件流可复现，但默认/临时 Ollama 模型均未返回 Runtime 所需结构化 Tool/JSON，任务真实以 `MODEL_UNAVAILABLE → partial` 结束、无 Artifact。证据落盘于 Task10 smoke/acceptance-final 报告，Spec034 保持未完成。
- **034 会话式深度研究与真实子 Agent Runtime — Task05** ｜ 实施中 → 实现完成、待评审/验收 ｜ 2026-09-13：完成后端最小闭环：冻结 AgentRun 输入/输出与 Fake 合同，复用 Spec023 Tool Registry/Executor 和既有 ResourceProbe，加入能力快照/Schema hash fail-closed、批量工具校验、预算/取消/checkpoint 写屏障；Task05 定向及 Task02–04/Spec027/Skill/Tool 受影响回归 156 passed、6 subtests，真实 Ollama 探针因沙箱 Operation not permitted 记录环境延期。
- **034 会话式深度研究与真实子 Agent Runtime — Task10** ｜ 实施中（自动化通过，真实 Smoke 阻塞） → 已完成 ｜ 2026-09-15：修复目录 RAG 降级排序、Search Worker 事实恢复和 WorkItem 绑定归一化；最终全量回归 `1878 passed, 1 skipped, 5 warnings, 52 subtests`。真实端口 18083 使用本机 Ollama 与 USENIX 目录完成 Intake→Plan→Approval→Search→Evaluator→Synthesizer，Session/Task 均 completed，生成 Markdown/HTML/citation manifest，部署与验收通过。
- **034 会话式深度研究与真实子 Agent Runtime** ｜ 已确认 → 已完成 ｜ 2026-09-15：Task02–10 全部收口，验收评审 GO，复盘与变更日志已落盘；真实失败仍保持 fail-closed，不伪造论文证据或 Artifact。
## 2026-09-13

- **036 Tool 入口源码只读查看** ｜ 已确认 → **已完成** ｜ 2026-09-13：Task02/03 由子代理实现（后端 `GET /api/tools/{name}/code`、前端 Tool 列表「代码」按钮与只读弹窗）；Task04 评审/回归/验收由主会话直评（frontend-reviewer / tester 子代理分派连续遇 502/429 网络错误无法派发，改为主会话对源码 + 真实服务 + 真实测试做非采信式复核）。三评审结论：需求评审通过（P0=0，M-01～M-08 回填）、后端技术评审通过（M-01/M-03/M-04/M-06/M-07 全 PASS，11 类解析终点探针无整文件/整类泄漏）、前端技术评审通过（M-02①②③④ 全 PASS，防串台 / codeBtn 边界 / M-06 编码对齐契约测试）。验收场景 A/B/C 全部达成，运行时 E2E 5/5 200、错误路径 4xx、响应体无 `/Users`/`.venv` 泄漏；后端定向 **38 passed**、前端契约 **18 passed**、`node --check` OK。文档层 952 写死问题（M-036-01，MEDIUM）已修正为 953 并加「行号随源码漂移、验收以接口返回值为准」说明。**未推送**：按用户裁决「先不推」，全部改动留工作区；另一 agent 的 spec-035 在途改动使 `kb_ask` 装饰器行由 952→953，本任务实现/测试均为动态取值，不受影响且未触碰 spec-035 文件。复盘见 `docs/sdd/retro/2026-09-13-spec-036-tool-source-code-viewer.md`。
- **035 线上模型接入与模型库端侧/线上分组** ｜ 新建 → 待确认 ｜ 经 grill with docs 两轮质询（10 个决策点）与用户裁决后落盘：以 `create_chat_model()` 为唯一收口点按模型名分发 provider（线上→`ChatOpenAI`，本地→`ChatOllama`），使对话/知识库/文章助手/技能调用**全部模块无缝支持线上模型**；新增 `GET /api/models`（`/api/health` 的 `models` 字段**一字不动**，零回归）；线上模型 Key/地址/清单在 `.env` 静态声明；模型库按「端侧模型 / 线上模型」分组展示；开发测试仅验连通性、极低消耗（`max_tokens=1`）。已同步建 `docs/sdd/plans/035/README.md` 与 Task02–07。编号按用户指定为 035（036 空缺）。**确认前不实施**。
- **035 线上模型接入与模型库端侧/线上分组** ｜ 待确认 → **已确认** ｜ 2026-09-13：用户指示「现在开工」。已建分支 `feature/spec-035-online-model-provider`；**临时决策**：子代理模型由 `Deepseek-V4.1-Flash` 改为 **`hy3`**（0.00 倍率），会话结束前恢复原值；**流程偏离**：按用户「开工」指示先行实现，需求/技术评审并入 Task07 执行。
- **035 线上模型接入与模型库端侧/线上分组** ｜ 已确认 → **已完成** ｜ 2026-09-13：Task02–07 全部完成。实现要点：新增 `model_catalog.py`（`.env` 解析 + `is_online_model` 纯函数 + `max_tokens=1` 探测）、`routes_models.py`（`GET /api/models` 分组端点）；`create_chat_model()` 内部按模型名分发 `ChatOpenAI`/`ChatOllama`（**签名与本地分支逐字节不变**）；4 个路由改为「模块级 `get_available_models()` + `is_online_model` 并集」以保留 44 处测试 patch 目标；前端模型库分组 + `optgroup` + 状态徽标（`?v=45`）。**回归**：全量 1702 passed / 2 failed（后者经 `git worktree` 基线验证为存量）；前端 184 passed。**修复的 3 个真实引入回归**：`test_api_routes_coverage` 2 个（patch 目标失效）、`test_kb_upload_closure_matrix` 1 个（spec-018 冻结清单 hash，按 spec-020 惯例刷新）。**部署**：服务已启动于 http://127.0.0.1:8000，`/api/health` 结构不变、`/api/models` 返回两组结构。**环境缺口**：本机 Ollama 不可达且未配线上 Key，端侧渲染与线上真实连通未端到端验证。**复盘**：`docs/sdd/retro/2026-09-13-spec035-online-model-provider.md`。**未提交**：工作树含 spec-034 在途改动，提交须限定文件范围。
- **035 体验与稳定性优化合集** ｜ building → **已完成** ｜ 2026-09-15：5 项全部落地并验证——Bug1 批次自洽跳过会话门禁（`a10abc5`）、Bug2 上传后立即可见（前端 `0e75391` + 后端契约测试 `f0096c4`）、Bug3 模型能力每日定时探测入库（`206b9a1`）、Bug4 Skill/Tool 标题复数与 eyebrow 去重（`2e9afb7`）、Bug5 模型选择器移入 composer-footer（`dc58125`），另有 `c72e483` 同步前端资源版本断言 `v=46`。后端定向 163 passed / 0 failed，全量 1764 passed（3 个失败为既有项，与本 spec 无关），前端 8 个 JS `node --check` 全通过。**部署运行时验证未完成**：旧进程 31766 未真正退出、仍持有 `data/kb/qdrant/.lock`，导致新服务无法写入向量库；需 `kill -9` 后干净重启再验收 Bug2/Bug3 运行时行为，属运维残留进程问题，与 5 项改动无因果关系。
- **035 体验与稳定性优化合集** ｜ 已完成（部署验证前） → **已完成（部署验证通过）** ｜ 2026-09-15：重新部署 8400 服务并完成运行时验收。`kill -9` 残留旧进程 31766 后 Qdrant 本地锁释放，894 篇目录全部重建索引（pending 0 / indexed 894 / failed 0），检索 `total_results` 由 0 恢复为 649+245 且结果带作者。Bug3 验收通过：`reasoning-options` 返回 `source=cache`、读 `data/model_capabilities.sqlite3`，切模型不再实时探测。Bug2 验收通过：上传 PDF 后计数立即 1→2、`status=indexing` 即已可见，测试文档已删除、0 残留。遗留：Bug4/Bug5 视觉建议人工过目；Reranker 模型缺失导致 `degraded=true`，属独立环境缺口。
- **037 首屏就绪缺口与 UX bug 合集** ｜ 待确认 → **已确认（进入实施）** ｜ 2026-09-16：经 grill with docs 确定 5 项边界（Q1=A 且补充「恒定上下文必须计入统计」，Q2/Q3/Q4/Q5 按架构师建议），用户明确确认 spec。范围：①上下文模块始终可见且计入恒定上下文（含修复 compute_context_usage 未传 system_rule 导致与真实装配不同源的漏算）；②KB 计数去掉硬编码 0 改 spinner 态；③v2 失败态中文可读 + 启动自愈（每文档每 chunker 限 1 次）；④审批卡片两处渲染点非 pending 时隐藏按钮 + 中文状态文案；⑤侧边栏三点菜单由死 span 改真按钮菜单。执行配置：主 Agent 为架构师自身，子代理统一 `hy3`（用户临时决策，0.00 倍率）。待核实项：根目录 CONTEXT.md 是否真被后端装配（已核实后端只读 USER.md/MEMORY.md/项目 MD），未注入则不计入占比。
- **037 首屏就绪缺口与 UX bug 合集** ｜ 已确认（实施中） → **已完成** ｜ 2026-09-16：5 项全部落地并经真实浏览器（Playwright/Chromium）验收——①上下文模块始终可见（`display:flex` 128×30，无会话显示「—」，`is-idle` 隐藏逻辑与 CSS 规则已删除）且恒定上下文计入统计（后端补 `system_rule` 恒定段 + 修复 dry-run 漏传 `project_id` 导致项目 MD 漏算）；②`#kb-count` 去硬编码 0 改加载态，实测显示真实计数 3；③审批卡片两处渲染点非 pending 不再创建按钮、状态文案中文化；④侧边栏三点菜单由死 `<span>` 改真 `<button>`（`aria-haspopup="menu"`），实测点击弹出「刷新模型列表 / 打开模型库视图」；⑤v2 重建失败态中文可读 + 启动自愈（顶层幂等标记每文档每 chunker 限 1 次），3 篇文档 v2 全部 indexed、failed 归零。回归：前端契约 21/21、`node --check` 全过；后端全量 2396 passed / 6 failed（6 个均核实为 main 带来的既有失败，其中 4 个经 `git stash` 隔离验证与本次改动无关）。部署：PID 1804，`/api/health` 200。遗留：`test_online_model_dispatch.py` 缺 `langchain_openai` 依赖收集失败（环境缺口）；Reranker 模型缺失致 `degraded=true`（独立环境缺口）。评审：本轮由主会话代行验收（代行，非独立评审）。
- **037 首屏就绪缺口与 UX bug 合集** ｜ 已完成 → **实施中（追加 Bug 6-8）** ｜ 2026-09-16：用户追加三项对话布局诉求，裁决**不另立 spec**、并入本 bug 合集（原拟的 039 已撤回）。新增 Bug 6 对话框模型选择器靠右（`.composer-footer .model-picker` 加 `margin-left:auto`，因它是首个子元素而渲染在最左）；Bug 7 聊天面板最多约两个屏幕高（`.chat-panel` 只有 `min-height` 无 `max-height`，被回答内容无限撑长，改为加上限 + `.messages` 内部滚动）；Bug 8 滚动右侧时左侧栏固定（`.sidebar` 未 sticky，改 `position:sticky` 且窄屏 ≤760px 行为不变）。grill 决策：Q1=A（左侧 tags 指整个侧边栏）、Q2=A（限高作用于整个聊天面板）。约束：不改 `#model-select` 逻辑、不得回退 Bug 1「上下文模块始终可见」契约。
- **037 首屏就绪缺口与 UX bug 合集** ｜ 实施中（Bug 6-8） → **已完成** ｜ 2026-09-16：Bug 6-8 全部落地并实测。Bug 6 模型选择器：实测 `.composer-footer` 无剩余空间（`margin-left:auto` 会无效），改为把 `.model-picker` 移到发送按钮前（id/事件/联动不变），已靠右（left 1102 / right 1298，发送按钮 1310）。Bug 7 聊天面板限高：新增 `max-height: calc(200vh - 162px)`，注入 80 条消息后面板封顶 1638px、`.messages` 内部滚动（7352>1503）、页面总高 1796px = 2.00 屏（原本会撑到 8 屏）。Bug 8 侧边栏固定：`.sidebar` 加 `position:sticky; top:0; align-self:start; max-height:100vh; overflow-y:auto`，滚动 1200px 后 top 仍为 0。回归：node 契约 21/21、`node --check` 全过、前端契约 pytest 59 passed（3 个文件同步 `styles.css?v=52`）；`#context-meter` 始终可见未回退；窄屏（720px）`sidebar display=flex` 与改动前完全一致（既有行为，非回归）。注：子代理分派连续 429，Bug 6-8 由主会话直接实现。
- **037 首屏就绪缺口与 UX bug 合集** ｜ 已完成 → 实施中（追加 Bug 9/10） → **已完成** ｜ 2026-09-16：Bug 9 用户报告「Ollama 挂了么/模型库不显示」——实测 Ollama 正常（11434 可生成，4.8s 返回），真因是 ResearchStore 的 SQLite 连接泄漏：进程 88,778 个句柄中 88,778 个全部指向 data/research/research.sqlite3（去重仅 87 路径），fd 耗尽致新建 httpx Client 抛 EMFILE，健康检查 500、模型库空白。修复：`_connect()` 改 `@contextmanager` 保证关闭（89 个调用点零改动），新增 5 用例（还原修复后 3 failed 证明可捕获），research 定向 62 passed、全量 2401 passed 无新增失败；重启后 fd 从 88,542 降至 144、health 200、模型库返回 11 个端侧模型。Bug 10 用户截图报告侧边栏「最近会话/工作区」重叠——复现确认为 **Bug 8 实施引入的回归**：`.sidebar` 限高后成为受约束 flex 容器，`.conversation-memory`（min-height:0）被压缩至 0 高、内容外溢（修复前 工作区 top=178 < 最近会话 top=197）。修复：`.sidebar > * { flex-shrink: 0 }`，超高走栏内滚动（修复后 工作区 412 在 最近会话 298 下方、mem 高 234、内部滚动 972>700、sticky 与上下文模块契约不回退）。回归：node 契约 21/21、前端契约 pytest 64 passed、`styles.css?v=53`。
## 2026-09-16

- **029 Research Task 全文获取与知识库联动 — Task02** ｜ 实施中 → **已完成（NO-GO）** ｜ 复用审计确认下载、导入、切片定位可复用，但 Research 侧审批、document link、AcquisitionEvent 和 EvidenceUpgrade 持久化缺失；`5 passed, 1 xfailed`，Task03 先补齐合同。
- **028 Research Task 可靠调度、计划版本与恢复 — Task04** ｜ 实施中 → **已完成** ｜ 接通 paused、pause/resume/cancel CAS、计划版本追加、审批幂等和 checkpoint 恢复接口；定向后端与 Spec027/034 受影响测试通过，未跑全量。
- **028 Research Task 可靠调度、计划版本与恢复 — Task05** ｜ 实施中 → **已完成** ｜ 前端接入暂停、继续、批准、取消、恢复提示和刷新/SSE 状态恢复；前端定向合同测试通过，待 Task06 收口。
- **029 Research Task 全文获取与知识库联动 — Task03** ｜ 实施中 → **已完成** ｜ 新增审批、document link、AcquisitionEvent、EvidenceUpgrade 桥接并复用既有 PaperImportBatchService；定向测试 `9 passed`，未下载真实 PDF。
- **028 Research Task 可靠调度、计划版本与恢复 — Task03** ｜ 实施中 → **已完成** ｜ 新增可恢复租约、checkpoint、资源预约与公平轮转调度器，复用既有状态机与 ResourceProbe；定向测试 `10 passed`，未跑全量。
- **028 Research Task 可靠调度、计划版本与恢复 — Task02** ｜ 实施中 → **已完成（GO）** ｜ ResearchStore 启用 WAL 与 30 秒 busy timeout；跨进程租约、过期接管、旧 token 拒绝、checkpoint CAS、终态不可逆及公平调度合同通过，定向测试 `6 passed`。
- **034 会话式深度研究与真实子 Agent Runtime** ｜ 已完成 → **实施中（Task11）** ｜ 真实 Smoke 生成的 Markdown 只有一篇证据对象和引用清单；新增 Task11 补强 USENIX 至少五篇候选保留及实质性报告输出，完成后重新验收收口。
- **028 Research Task 可靠调度、计划版本与恢复** ｜ 待确认 → **实施中（Task02）** ｜ 用户明确要求跳过等待并继续开发，先执行 SQLite WAL、租约、checkpoint 与公平调度 Go/No-Go 门禁。
- **029 Research Task 全文获取与知识库联动** ｜ 待确认 → **实施中（等待 028 调度合同）** ｜ 用户明确要求连续推进；全文下载与导入仍依赖 028 的可靠调度合同，暂不越过前置门禁。
- **029 Research Task 全文获取与知识库联动 — Task04** ｜ 实施中 → **已完成** ｜ 2026-09-16：接通既有 `hybrid_search` 与 inspection manifest，新增 EvidenceUpgradeService 和 evidence-upgrade API；证据保存文档、切片、页码、源哈希与 manifest 指纹，删除/重建/变更时 fail-closed。定向验证 12 passed，组合回归 69 passed、5 subtests。
- **028 Research Task 可靠调度、计划版本与恢复 — Task06** ｜ 实施中 → **收口中** ｜ 2026-09-16：收口审查发现恢复 API/UI、评审台账和部署 smoke 证据缺口；已补齐 `POST /recover`、前端“检查并恢复”按钮及定向测试，待最终评审、全量回归和部署验证。
- **029 Research Task 全文获取与知识库联动 — Task05** ｜ 实施中 → **已完成** ｜ 2026-09-16：完成候选增删、只读预览、显式确认、逐篇导入状态、登录等待、失败重试和全文证据定位入口；确认前不下载。前端定向 15 passed、Node 语法/合同检查通过，待 Task06 收口。
- **028 Research Task 可靠调度、计划版本与恢复 — Task06** ｜ 收口中 → **实施中（运行时证据已部分补齐）** ｜ 2026-09-16：真实 FastAPI 与 Research 页面加载 smoke 已通过，最终全量回归 2450 passed；按钮旅程与强退恢复尚未执行，继续保留实施中。
- **029 Research Task 全文获取与知识库联动 — Task06** ｜ 待执行 → **实施中** ｜ 2026-09-16：完成三份评审、全量回归和服务页面 smoke；真实公开 PDF/KB 导入与全文证据仍未执行，验收保持 NO-GO。
- **034 会话式深度研究与真实子 Agent Runtime — Task11** ｜ 实施中 → **已完成（实现与目录复验）** ｜ 2026-09-16：使用现有 USENIX 缓存候选池 `search_id=dd5c47aa0cb541188b884c27fa233e67` 固定复验 5 篇模糊测试论文；`ReportSynthesizer` 产出 5 条引用、约 8.9k 字符 Markdown，标题/摘要来自目录，关键词缺失时明确不补写。全量回归另发现既有会话压缩 worker 用例阻塞，Spec034 总收口仍保持实施中。
- **034 会话式深度研究与真实子 Agent Runtime** ｜ 实施中 → **已完成** ｜ 2026-09-16T22:28:29+08:00：人工验收通过后修复 Intake 流序号导致的假中断、活跃研究冲突按钮无响应、计划操作按钮字号和目录详情降级丢候选；合并 `origin/main` 后全量回归 `2478 passed, 1 skipped, 67 subtests`，验收材料和复盘同步完成。
- **028 Research Task 可靠调度、计划版本与恢复 — Task06** ｜ 收口中 → **已完成** ｜ 2026-09-16：补齐 `GET /api/research-scheduler/status`，聚合队列、额度和安全摘要且不泄露租约 token；Spec028 定向回归 `24 passed`，最终全量回归 `2481 passed, 1 skipped, 5 warnings, 67 subtests`，8500 本机重启 smoke 的 health、首页、scheduler status 均 HTTP 200，收口文档与部署记录已同步。
- **028 Research Task 可靠调度、计划版本与恢复** ｜ 实施中（Task06） → **已完成** ｜ 2026-09-16：Task02–06 全部完成，租约/checkpoint/公平调度、暂停/审批/取消/恢复、scheduler status 与状态台账完成；本地 `main` 已包含本 Spec 代码和文档，未 push。

## 2026-09-17

- **029 Research Task 全文获取与知识库联动 — Task06** ｜ 实施中 → **已完成** ｜ 修复本地优先检索缺少服务端快照句柄、Research Task 未持久化 `search_id` 和确认句柄未校验的问题；真实验证任务 `3eee288b8e5a512dad3dad524d787c63` 完成 preview→确认→既有批次→公开 USENIX PDF 导入→v1 索引→全文证据升级，最终全量回归 `2486 passed / 1 skipped / 5 warnings / 67 subtests` 退出码 0，用户人工验收通过。
- **029 Research Task 全文获取与知识库联动** ｜ 实施中 → **已完成** ｜ Task02–06 收口，评审、运行时证据、部署记录和复盘均已落盘；本地 `main` 已包含 Spec029 修改，远程 `origin/main` 已是本地分支祖先，无需重复合并。
## 2026-09-17

- **Spec 030：跨论文证据矩阵与深度研究报告**：`待确认` → `实施中`。用户明确确认“确认 Spec030/按此执行”，开始按 Task02–06 顺序实施；Task 开发阶段执行定向测试，Spec 收口时再执行全量回归。
- **Spec030 Task02：冻结 Claim/Evidence 与报告协议**：`实施中` → `已完成`。Luna high 子 Agent 完成 `evidence-report-v1` 合同、固定样本与 4 项定向测试，结果 `GO_FOR_TASK03`。
- **Spec030 Task03：实现证据矩阵与校验**：`待执行` → `实施中`。依赖合同已冻结，开始接入既有 ResearchStore 和全文 provenance。
- **Spec030 Task03：实现证据矩阵与校验**：`实施中` → `已完成`。完成 Claim/Evidence/ComparisonDimension/Cell 持久化、owner/version 隔离及矩阵 POST/GET；定向测试 3 passed，全文 provenance 复用 Spec029。
- **Spec030 Task04：实现报告生成、版本和导出**：`待执行` → `实施中`。开始复用既有报告合成/Artifact 能力，接入 `evidence-report-v1` 矩阵和三格式只读导出。
- **Spec030 Task04：实现报告生成、版本和导出**：`实施中` → `已完成`。完成不可覆盖 `ResearchReport` 版本、citation manifest 回查、Markdown/HTML/JSON 一致导出；定向测试 4 passed，受影响后端 89 passed。
- **Spec030 Task05：实现报告工作台与引用交互**：`待执行` → `实施中`。开始接入矩阵、版本化报告、引用展开与只读下载 UI。
- **Spec030 Task05：实现报告工作台与引用交互**：`实施中` → `已完成`。完成证据矩阵、覆盖缺口、版本/格式视图、citation 展开和现有切片定位；`node --check`、前端定向测试 35 passed。
- **Spec030 Task06：最终评审、回归、部署与复盘**：`待执行` → `实施中`。Task02–05 均已通过各自定向门禁，开始唯一全量回归、浏览器 smoke、部署和收口评审。
- **Spec030 Task06：最终评审、回归、部署与复盘**：`实施中（P1）` → `已完成`。修复 `EvidenceReportError` 错误出口与矩阵未就绪状态映射，保留旧资源版本兼容标记；后端复核通过，全量回归 2504 passed、1 skipped、67 subtests，运行时 smoke 的 health/root=200、未知矩阵=404、未知报告=404、非法格式=406。
- **Spec 030：跨论文证据矩阵与深度研究报告**：`实施中` → `已完成`。Task02–06 全部完成，证据矩阵、不可变三格式报告、引用定位 UI、验收评审、部署验证和复盘均已落盘；未 push/merge。
- **Spec 031：动态模型路由与资源调度优化**：`待确认` → `实施中`。用户确认所有 Spec，开始 Task02 单/多实例与 9B Worker 基准门；子 Agent 临时使用 Luna high，Task 阶段只运行定向测试。
- **Spec031 Task02：单实例/多实例与 Worker 基准门**：`实施中` → `已完成（单实例条件放行）`。真实 1–4 Worker 基准全部 HTTP 200、失败率 0%；热吞吐提升约 28.1% 但 TTFT 约 3.45×，ResourceProbe cap=1；多实例因无第二实例/资源证据保持 NO-GO。Task03 仅按单实例 shadow/观测路径继续，P1/P2 证据增强列入 Task06。
- **Spec031 Task03：实现路由观测与 Shadow Policy**：`待执行` → `实施中`。Task02 仅放行单实例、ResourceProbe 约束的观测路径；开始记录脱敏决策/结果、策略回放和不可阻塞降级。
- **Spec031 Task03：实现路由观测与 Shadow Policy**：`实施中` → `已完成（单实例条件放行）`。完成值级敏感内容拒绝、ResearchStore owner/幂等隔离、生产 opt-in 观测装配和不改变生产选择的 shadow replay；独立复审 GO，定向回归 111 passed、5 subtests。生产 outcome 自动记录与 Task02 benchmark 证据增强列入 Task06。
- **Spec031 Task04：实现内存感知 Worker 扩缩与策略激活**：`待执行` → `实施中`。Task03 复审 GO，开始在单机/单实例门禁内接入现有 ResourceProbe、ResearchScheduler 与资源预约；多实例、自动下载/卸载和跨机器调度保持禁止。
- **Spec031 Task04：实现内存感知 Worker 扩缩与策略激活**：`实施中` → `已完成（后端 GO）`。完成 strong 跨 scheduler 原子单并发、过期 quota 恢复、同任务 grant 隔离、服务端 evidence gate 与原子策略激活；reviewer/tester 均 GO，定向回归 154 passed、5 subtests。runtime smoke、权限边界与 Task02 provenance 留给 Task06。
- **Spec031 Task05：实现路由解释与基准界面**：`待执行` → `实施中`。Task04 reviewer/tester GO，启动前端只读解释视图和受控基准状态；不开放策略编辑、不显示敏感文本、不修改后端。
- **Spec031 Task05：实现路由解释与基准界面**：`实施中` → `已完成（前端 GO）`。完成脱敏模型/原因/Worker/升级解释和 warm/cold 基准卡；reviewer/tester 均 GO，43 passed，严格数值与路径 fail-closed 通过。`routing_benchmark` 投影留作 Task06 P2。
- **Spec031 Task06：最终评审、回归、部署与复盘**：`待执行` → `实施中`。Task02–05 门禁均通过，开始唯一全量回归、前后端运行时 smoke、部署证据和最终复盘；多实例 NO-GO 与遗留 P2 只做诚实记录。
- **Spec031 Task06：最终评审、回归、部署与复盘**：`实施中` → `已完成`。修复 benchmark 质量/provenance、压缩 worker 持久化顺序、测试 worker 隔离及论文评估安全选集投影；最终全量回归 `2539 passed, 5 warnings, 67 subtests`，8500 部署 smoke 通过。
- **Spec031：动态模型路由与资源调度优化**：`实施中` → `已完成`。Task02–06、三份评审、复盘和运行时验证已收口；仅单实例范围 GO，多实例明确 NO-GO。
- **Spec034：会话式深度研究 Agent Runtime**：`已完成` → `实施中`。真实浏览器端到端排查确认后端链路正常（approve_plan 返回 200、`research_service.start` 在进程内后台线程执行编排、SSE 可取到事件），缺口在前端：计划批准后未加载新建 Task 详情与事件流，时间线因无 Task 事件（`hidden = events.length === 0`）不渲染，致使 spec028 运行/调度恢复、spec029 全文获取、spec030 证据矩阵无法验证；新增 Task12 承接该前端修复。
- **Spec034 Task12：批准后加载 Task 视图与事件流（时间线渲染）**：`待执行` → `已完成`。修复竞态——并发 `refreshWorkspace` 清空选中导致在途 `selectTask` 被守卫误杀、新建 Task 接口从未请求；加 `selectTask` 在途保护并消除批准后重复 SSE 管道；真实浏览器验证批准后 6s 内时间线渲染，`node --check` 通过。
- **Spec034：会话式深度研究 Agent Runtime**：`实施中` → `已完成`。Task12 收口，Task01–12 全部完成；端到端中 spec029 全文获取 / spec030 证据矩阵在本机仍因真实检索与 LLM 耗时在窗口内未到达而 SKIP，属环境耗时而非功能缺陷。

## 2026-09-20

- **Spec040 Research Runtime 指数退避与线上模型兜底** ｜ `新建` → `待确认` ｜ 2026-09-20：根据会话 `14355ba3973e46d6a59fd2819df6f9b8` 暴露的资源竞争快速失败，落盘失败分类、持久化指数退避、受控线上模型回退和观测验收边界；尚未修改业务代码，等待用户确认。

- **039 API 端到端成功案例与人工验收协议** ｜ `待确认` → `实施中` ｜ 2026-09-20：用户确认先完成 Spec039，再以 Spec032 作为示范；启动验收协议 Skill、模板接入和 Spec032 API E2E/人工案例产出。子 Agent 临时使用 Luna high。
- **039 API 端到端成功案例与人工验收协议** ｜ `实施中` → `阻塞` ｜ 2026-09-20：验收协议、Skill、模板和真实 API 证据已落盘；Spec032 任务链已完成但报告仍缺少标题/摘要/关键词/方法比较，且浏览器投影与恢复路径未复核，按 90% 门禁暂不交付。
- **039 API 端到端成功案例与人工验收协议** ｜ `阻塞` → `待人工验收` ｜ 2026-09-20：运行 D 已生成 5 篇可读报告并完成 Artifact/浏览器复核，运行 E 补齐处理中 task/Worker/Skill/Tool 状态采样；修复小模型重复 citation candidate_id 的唯一引用归属校正，定向测试 81 passed、5 subtests，允许用户开始人工验收，Spec 尚未收口。
- **039 API 端到端成功案例与人工验收协议** ｜ `待人工验收` → `待人工验收` ｜ 2026-09-20：继续修复评估器数组/批量证据展开、搜索 Worker 只读恢复、长摘要安全上限和固定渲染回退；定向测试 85 passed、5 subtests，真实报告 API 返回 200。保持待人工验收，未提前收口。
- **039 API 端到端成功案例与人工验收协议** ｜ 新建 → `待确认` ｜ 2026-09-20：根据用户要求把自然语言 Intake 作为主验收路径，增加真实 API E2E 前置门禁、详细人工步骤和 90% 准备度阈值；仅落盘 Spec 与任务文档，等待确认后再创建验收 Skill。

- **Spec032 Research Task 数据源与安全会议扩展** ｜ `已确认` → `待确认` ｜ 2026-09-20T03:38:32+08:00：用户经多轮 Grilling 确认多来源 Worker Skill、统一 Tool、官网优先、批准计划内自动导入与待处理论文人工修复。原任务已有代码与真实产品接线存在差距，修订 Spec、审计和 Task06–14 已落盘；本次仅文档，不改业务代码，等待新版 Spec 明确确认。
- **Spec032.1 USENIX Skill 解耦与详情页摘要补齐** ｜ `已确认` → `已确认`（移交记录，状态未变） ｜ 2026-09-20T03:38:32+08:00：作为 Spec032 子规格保留 Task02–06 成果；原 Task08/10 待办转由 Spec032 Task13 承接，Task07 自身评审仍未完成，未标记完成或伪造 Task09 结果。
- **Spec032 Research Task 数据源与安全会议扩展** ｜ `待确认` → `实施中` ｜ 2026-09-20T03:50:06+08:00：用户确认新版 Spec032 并授权开发；启动 Task06，先统一七来源 ID、字段真实来源、权威级别与结构化返回合同。子 Agent 临时使用 Luna xhigh；Task 阶段只运行定向测试。
- **Spec032 Task06：统一来源 ID、权威、返回合同与旧回归** ｜ `进行中` → `已完成` ｜ 2026-09-20：Luna high 子 Agent 完成版本化 SourceResult/ImportResult、七来源 canonical ID、真实 authority 归一化、旧 SQLite 别名迁移和统一薄包装；主 Agent 复跑 206 个相关测试，ruff、compileall、git diff --check 均通过，放行 Task07。
- **Spec032 Task07：官网目录优先、聚合兜底与逐年字段覆盖** ｜ `实施中` → `部分完成` ｜ 2026-09-20：IEEE S&P 2024 官方目录固定样本、字段 provenance、缺失摘要/关键词告警及 PDF 响应拒绝已通过 76 个定向测试；CCS/NDSS 与其余年度保持未验证/NO-GO，不伪造覆盖，Task08 只可接入已验证范围。
- **Spec032 Task08：来源注册、真实同步与 Graph/Store/Planner 接线** ｜ `实施中` → `部分完成` ｜ 2026-09-20：七来源 Registry 工厂、受控同步 API、真实终态、SQLite 重启读取和 generic adapter 状态修复通过 48 个相关测试与 12 个 subtests；Graph/Planner 全量 source_ids 接线尚未完成，保持诚实的部分状态。
- **Spec032 Task09：多来源 Worker Skill 与统一 Python Tool** ｜ `实施中` → `已完成` ｜ 2026-09-20：统一 `paper_discovery` 的 `worker-tool-v1` facade、来源 Skill、注册/分派入口和 fail-closed 校验完成；132 个相关测试、21 个 subtests 及静态检查通过，CCS/NDSS 未验证状态未被伪造为成功。
- **032 论文来源扩展 — Task10** ｜ 实施中 → 已完成（定向验证通过） ｜ 2026-09-20：批准计划自动导入复用既有批量导入、安全下载、身份核验与索引链路；普通检索、未批准或已取消计划不触发 PDF 请求。定向测试 206 passed，Ruff、compileall、diff-check 通过。
- **032 论文来源扩展 — Task11** ｜ 实施中 → 已完成（后端定向验证通过；前端留 Task12） ｜ 2026-09-20：新增候选级持久待处理队列与人工解决记录，复用既有登录/继续/重试和 KB 上传；跨任务去重、身份不确定阻断、ResearchDocumentLink 回填通过 102 passed、12 subtests，静态检查通过。
- **032 论文来源扩展 — Task12** ｜ 待执行 → 实施中（前端） ｜ 2026-09-20：Task11 后端问题队列接口已冻结，启动来源动态进度卡、待处理论文入口、登录/上传/重试动作和字段来源展示；仅分派前端角色，保留真实浏览器 smoke 到最终验收。
- **032 论文来源扩展 — Task12** ｜ 实施中（前端） → 已完成（前端定向验证通过；真实 smoke 留 Task14） ｜ 2026-09-20：前端完成七来源动态进度卡、候选字段来源展开、waiting_login/failed 动作和人工确认上传；`229 passed`、Node syntax、diff-check 通过。
- **032 论文来源扩展 — Task13** ｜ 待执行 → 实施中 ｜ 2026-09-20：Task12 已完成，启动 032.1 余项审计与 IDE/会话 Skill 粘性移交；不代签 032.1 评审，不伪造产品 API 成功。
- **032 论文来源扩展 — Task13** ｜ 实施中 → 部分完成（静态/契约通过；真实服务 smoke 阻塞） ｜ 2026-09-20：补齐 IDE Skill 的 `source_page_url` 官方详情页回退；Task13 合同 4 passed，会话/仓储/Skill 相关测试 73 passed。服务未启动导致真实检索→导入 smoke 留 Task14。
- **032 论文来源扩展 — Task14** ｜ 待执行 → 实施中 ｜ 2026-09-20：Task06–12 定向实现完成、Task13 已诚实记录 smoke 阻塞，启动最终复用审计、三门评审、唯一全量回归、受控服务 smoke、部署与收口复盘。
- **032 论文来源扩展 — Task08 follow-up** ｜ 部分完成 → 已完成（定向验证通过；真实 smoke 留 Task14） ｜ 2026-09-20：修复 Planner→Research Worker 的多来源接线；`ieee_sp/ccs/ndss/openalex/crossref` 统一走 `PaperDiscoveryToolFacade`，转换并冻结既有目录/来源记录/provenance/SearchJob/SearchResult，USENIX/DBLP/all 旧 Graph 保持不变。Task08/09/Spec034 合同 23 passed、相关来源/Graph 回归 215 passed，Ruff、compileall、diff-check 通过。
- **032 论文来源扩展 — Task07 follow-up** ｜ 部分完成 → 部分完成（新增 NDSS 2024 固定样本） ｜ 2026-09-20：补齐 NDSS 官方 accepted-papers 2024 路由、HTML 解析、ETag/content-hash、PDF 响应拒绝和字段缺失告警；82 项相关定向测试通过。NDSS 仅为 2024 bounded subset，2021–2023/2025 未验证；CCS 仍 NO-GO，未伪造年度覆盖。
- **032 论文来源扩展 — Task07 CCS follow-up** ｜ 部分完成 → 部分完成（CCS bounded NO-GO） ｜ 2026-09-20：审计 CCS 2021–2025 官方入口；2021/2022/2024 缺稳定身份键，2023 动态数据库故障，2025 依赖 JavaScript。新增 `artifacts/task-07/ccs-coverage.md` 与 56 项 gate 测试，保留 Crossref/OpenAlex 兜底，未新增不可靠官方解析器。
- **032 论文来源扩展 — Task14 follow-up** ｜ 实施中 → 实施中 ｜ 2026-09-20：纳入 Task08 多来源 Worker bridge 与 Task07 CCS bounded NO-GO；Spec032 相关回归更新为 `765 passed`。18080 health/ready 已 HTTP 200，受控目录 smoke 有成功和 degraded 两类真实结果；完整覆盖、登录/导入和业务恢复仍缺收口证据，暂不收口。
- **032 论文来源扩展 — Task11 recovery follow-up** ｜ 已完成（后端定向验证通过） → 已完成（补充状态保护） ｜ 2026-09-20：动作投影随 waiting_login/failed 最新状态收敛，resume 审计、resolved 重复上传保护补齐；定向 106 passed/12 subtests，Spec032 相关回归 764 passed。真实登录/上传 smoke 留 Task14。
- **032 论文来源扩展 — Task14 runtime follow-up** ｜ 实施中 → 实施中 ｜ 2026-09-20：18080 沙箱外 health/ready HTTP 200；USENIX 2024（227）与 NDSS 2024 official（142）目录 sync 完成并在重启后可读；IEEE S&P 2024 外站 sync 返回 `SOURCE_FAILED`/degraded，完整四会覆盖、候选评估→导入与业务批次恢复仍未达收口门禁。
- **032 论文来源扩展 — Task07/08 NDSS runtime follow-up** ｜ 部分完成 → 部分完成 ｜ 2026-09-20：修复 NDSS 2024 runtime 未传 `route=official` 的接线缺口；新增 2024 official/其它年份 Crossref fallback 测试，相关定向测试通过，目录阶段仍不探测 PDF。
- **Spec040 Research Runtime 指数退避与线上模型兜底** ｜ `待确认` → `已确认` ｜ 2026-09-20：用户要求立即开始开发并指定子 Agent 使用 Luna high；确认失败分类、指数退避和受控线上模型回退范围，进入实现前评审与 Task02。
- **Spec040 Research Runtime 指数退避与线上模型兜底** ｜ `已确认` → `实施中` ｜ 2026-09-20：开始 Task02 失败分类与 Go/No-Go 门禁；Task 阶段仅运行定向测试，线上 Provider 默认保持关闭。
- **Spec040 Task02–03：失败分类与指数退避** ｜ `实施中` → `已完成（后端定向验证通过）` ｜ 2026-09-20：AgentRuntimeError 保留真实稳定错误码；资源忙进入持久化 `waiting_retry`，实现有界指数退避、重启恢复和原子领取。定向研究运行时回归 91 passed，线上 Provider 回退留 Task04。
- **Spec040 Task04–05：Research Runtime 指数退避与线上模型兜底** ｜ 待执行 → 已完成（Task06 收口保留） ｜ 2026-09-20：完成线上 Provider 受控回退、任务运行时脱敏观测投影与前端等待/切换状态提示；定向验证通过，保留全量回归、真实 API E2E、部署和复盘门禁。
- **Spec040 Research Runtime 指数退避与线上模型兜底** ｜ 实施中 → 已完成 ｜ 2026-09-20：Task06 收口通过；全量回归 `2684 passed, 3 skipped, 67 subtests`，8500 回环部署的 health/ready/models/research-task/scheduler API 通过，DeepSeek Provider 探针在模型别名修正后 HTTP 200；验收评审、人工步骤、准备度矩阵和复盘已落盘。Qdrant warmup 单独降级记录，不属于 Spec040 阻塞。

- **Spec032 Research Task 数据源与安全会议扩展** ｜ 实施中 → **实施中（Semantic Scholar 扩展）** ｜ 2026-09-21：用户确认把 Semantic Scholar Academic Graph 从仅 OA 下载兜底扩展为批量元数据补全、候选池辅助召回和 autocomplete/引用图辅助；新增 Task15–17。Task15 已落地统一客户端、字段 provenance 和 Graph 缺字段补全，Task16–17 保留候选来源门禁与产品接线，不提前宣称完成。
- **Spec032 Task17 图辅助** ｜ 实施中 → **最小实现完成，待 Task14** ｜ 2026-09-21：Luna high 子 agent 完成 citations/references 的稳定分页契约、paperId/limit/offset 输入边界、去重解析、429/5xx 脱敏降级与定向测试；产品 API/UI 仍按 Spec 边界关闭，真实 key 与最终回归留 Task14。
- **Spec032 Task16 缓存语义** ｜ 最小实现完成 → **最小实现完成（缓存审计补强）** ｜ 2026-09-22：重复 query + conference 读取已完成的 Semantic Scholar fetch unit，跳过重复 bulk 请求和重复写入，并回填 paper_count/last_success_at；并发租约仍留 Task14/后续收口。
- **Spec032 Task17 产品 API** ｜ 最小实现完成 → **最小实现完成（受控 API 已接线）** ｜ 2026-09-22：新增 metadata-only autocomplete、citations、references 只读端点，复用共享限流与脱敏错误合同；前端 UI、目录写入和报告引用链保持关闭，真实 key/部署验收留 Task14。
- **Spec032 Task15–17 外部 smoke** ｜ 实施中 → **实施中（外部网络阻塞）** ｜ 2026-09-22：使用 `.env` 中的 key 发起官方 autocomplete probe 时，本机 DNS 无法解析 `api.semanticscholar.org`；未伪造成功，代码侧定向回归保持 66 passed，真实 key/429/重启验证继续留 Task14。
- **Spec032 Semantic Scholar 429 处理** ｜ 实施中 → **实施中（退避补强）** ｜ 2026-09-22：元数据客户端与 OA 回退适配器统一采用有界指数退避，优先使用合法 `Retry-After`（最大 30 秒），并新增 429 重试测试；相关定向回归 72 passed，Spec032 仍待 Task14 收口。
- **Spec032 Task16 持久化复核** ｜ 实施中 → **实施中（SQLite 重启验证补齐）** ｜ 2026-09-22：Semantic Scholar bulk recall 已验证 fetch unit、目录论文、来源记录和字段 provenance 可跨 SQLite 重启复用；重复 query 只发起一次 bulk 请求。Task14 的真实来源覆盖、导入恢复和最终签字仍未完成。

## 2026-09-19

- **Spec 032：Research Task 数据源与安全会议扩展**：`待确认` → `已确认`。用户授权「重新梳理 Spec032 逻辑并开发」；架构师复核后确认 Adapter 与 IEEE S&P / ACM CCS / NDSS 三会议源已在代码层落地（Task02–04 实现完成），剩余缺口为来源注册表、`/api/papers/sources*` 接口、字段级 provenance 表、`authority_rank` 尺度统一、`source_kind` 约束扩展、SourceCoverage 与来源卡片 UI；原 Task05 拆为后端 Task05 与跨端 Task06，验收评审顺延为 Task07。
- **Spec 029 / 030 / 031 agent 路径打通（修复分支）**：新建分支 `fix/spec029-030-031-pipeline`（自 `main` 5a8181f 切出），修复 `search_paper_catalog` 外网 0 命中无本地兜底、agent 路径从不落库论文选集、跳过 WorkItem 时非法状态转移被吞三个 bug。
- **Spec 029/030/031 P0 修复**：`待修` → `已完成`。`_validated_evaluator_candidates` 聚合分支原先把候选合法性绑在 `catalog_metadata` 上，元数据缺失即返回空 → synthesizer 被判 `NO_VALIDATED_EVIDENCE` **不被派发** → 任务 `partial`。改为以 Search Worker 的 `candidates` 召回白名单作为合法性唯一依据（新增 `_recalled_candidate_ids`），元数据只补字段不再是门禁；新增 `tests/test_validated_evaluator_candidates.py`（7 例），回归 422 passed。端到端复验：任务 `426515552d2b5a61bdce681e22d22892` 的 5 个 WorkItem 全部 completed，`syn` 正常派发。
- **Spec031 补齐缺失端点**：`未实现` → `已完成`。Spec031 接口表声明但代码缺失的 `GET /api/research-routing/status`（200 真实资源摘要 / 503 含降级状态）与 `GET /api/research-routing/decisions`（脱敏决策 + owner 隔离 + 400 参数校验）已实现；新增 `tests/test_research_routing_status_decisions.py`（8 例）。至此 029/030/031 三端均可通过 API 验收，样例见 `artifacts/spec029-030-031-api-sample.md`。
- **Spec032 Task05 后端第一批**：`待执行` → `已完成`。统一 `authority_rank` 为唯一方向「数值越小越权威」（新建 `domain/source_authority.py`），新建 `infrastructure/source_registry.py`（7 个来源的注册表 + 必需源外部开关 409），并把 `search_source_progress` 的 `source_kind` CHECK 扩展为 7 种（schema v3 迁移已生效）。新增 `tests/test_spec032_authority_registry.py`（12 例），相关回归 720 passed。
- **Spec032 Task05 后端第二批**：`待执行` → `实施中` → `已完成`。`field_provenance` 表与 v4 迁移、`save_field_provenance`/`get_field_provenance`（权威门禁：低权威只补缺、不得覆盖）并在 DBLP 落库路径接入 provenance sink；`GET /api/papers/sources`（配置级 health、无网络副作用、脱敏）、`PATCH /api/papers/sources/{id}`（未知 404 / 必需源 409）、`POST /api/papers/sources/{id}/sync`（202 受控年度 scope，无独立同步入口的源返回 409 而非伪造成功）。新增 `tests/test_spec032_field_provenance.py`（8 例）与 `tests/test_spec032_sources_api.py`（22 例）。跨领域回归 **820 passed**、ruff 全通过。
- **已知边界（留 Task06）**：`/papers/sources` 的 PATCH 启停为进程内运行时状态，跨重启回到服务端配置默认值；`dblp`/`openalex`/`crossref` 无独立同步入口故 sync 返回 409；Planner 侧 `source_ids` 校验尚未接入主流程。

- **Spec 039：测试补全与测试基建整理**：`待确认` → `已确认`（用户授权直接执行，不经评审）。核查发现：测试**类型**缺「前端/网站端到端（不调 API 的真实浏览器操作）」；具体用例缺口含 Planner `source_ids/scope` 422 校验与 `SourceCoverage` 进度表未实现、增量缓存语义与跨源合并等漏测；42 个测试文件含 `spec` 数字、17 个含 `task` 数字（git 核实全部由 `compwjh` 创建，根因是命名规则此前从未沉淀到文档/skill）；`tests/` 平铺 150+ `test_*.py`。已新建 7 个功能子目录（各含 `__init__.py` 功能说明），全量测试按功能分类，42 个违规文件改名（去 spec/task 数字、按功能命名），移动时同步修正 `parents[1]`→`parents[2]`、fixtures 路径与一处跨文件 import；命名规则沉淀至 `.codebuddy/skills/test-naming/SKILL.md`。验证：`pytest tests --collect-only` 重组前后均为 **2613 collected**，无导入错误。
- **041 Langfuse 观测：trace 详情与瀑布图** ｜ 待确认 → **已确认（进入实施）** ｜ 2026-09-21：grill 确认边界——`LANGFUSE_MIGRATION_V4_WRITE_MODE` 默认 `events_only`（worker/src/env.ts:570），该模式按 `v4WritesToLegacyTables`（同文件 692-693）**不写 traces/observations 表**，故详情页空白、瀑布图无数据源；本机 .env 未设该变量即走默认。方案首选切 `dual`（同时写 events 与 legacy 表）复用 Langfuse 原生瀑布图；备选 `events_only + ALLOW_PREVIEW_OPT_IN=true`；兜底换 v3，均失败才考虑自研（需先修订 spec-013）。同时按用户裁决去掉 input 脱敏（spans.py:225 redact_prompt_messages 清零 content），并同步修订 spec-013 A3 口径为 input+output 均全量。用户授权：修复后继续按 spec-013 原则为未埋点新功能补埋点，方案由架构师直接制定并执行。

- **041 Langfuse 观测：trace 详情与瀑布图** ｜ 已确认 → **实施中（T-A/T-B/T-D 落地；T-E 待实施）** ｜ 2026-09-21：T-A `vendor/langfuse/.env` 设 `LANGFUSE_MIGRATION_V4_WRITE_MODE=dual` 并重启 Langfuse（v4.27.0 OSS）；T-B spans.py `redact_prompt_messages` 保留原文 content、新增 tests 6 例 33 passed，后端评审通过（无必改项）；T-D ClickHouse 补 query_log 段（`~/opt/clickhouse/config.xml`，因「无配置文件」模式内嵌默认配置不含 query_log），`system.query_log` 已创建并写入 1425 行，worker `V4LegacyApiUsageJob failed` 报错停止（grep count=0）。运行时实证：trace `63d39d2d853c34860f450d0309098dd6` 的 input/output 全量可见、`observations` API 已返回数据，但瀑布图只有单条 0.00s generation 条（Langfuse SDK 4.15.1 不支持 start_time，spans.py:13-22 注释属实）。用户 2026-09-21 三选一裁决为**方案 2**：在 spans.py 中走 OTel 直 API + `LangfuseOtelSpanAttributes` 生成 4 子 span（load/prefill/decode/overhead）+ generation 主体 `completion_start_time` 标记首 token；新增 T-E，前端零改动；同步修订 spec-013:143「不自研甘特图」约束为说明方案 2 仍走原生瀑布图渲染、不违反本约束。

- **041 Langfuse 观测：遗留项清理（2026-09-21 架构师）** ｜ 实施中 → **遗留项逐条处理** ｜ (1) 默认链路：`OLLAMA_ROUTE` 默认由 `langchain` 改为 `direct`（spec-013:118 同步修订）——依据实测 langchain 链路无服务端 timings、5 阶段瀑布条恒为 0（trace `f589b138...`），direct 链路实测 load 5.575s / prefill 0.214s / decode 16.288s（trace `29c97aef...`），用户 grill 裁决「必须看到瀑布图」优先于「保持 langchain 默认」；A6 双链路对比仍可按显式 route 参数走 langchain，ChatOllama 链路不删除。(2) A5 判据放宽：原「热调用 load 接近 0」实测未达（冷 5.575s / 热 3.632s，差 ≈1.9s），根因 Ollama `keep_alive=5m` 默认行为非实现问题，判据改为「冷调用 load 明显长于热调用」，`OLLAMA_KEEP_ALIVE` 调优留作运维遗留。(3) 历史 trace 不回填：已在 spec-041:54 书面声明（约 1769 行旧事件不回填 legacy 表，仅新 trace 受益）。(4) 私有 API 升版适配：已在 spec-041:91 记录（`langfuse._otel_tracer` 用 getattr 兜底、`create_span_attributes` 用 try/except ImportError 容错；每次 langfuse 升版须跑 1 次回归，预期改动 1-5 行）。(5) 全量后端回归未跑完（沙箱 SIGTERM）：待默认值改动落地后分段复跑。

- **041 Langfuse 观测：A5 结论修正 + 默认路由落地验证（2026-09-21 架构师）** ｜ 遗留项处理 → **A5 已达成、默认路由生效** ｜ (1) A5 修正：此前以冷 5.575s / 热 3.632s 判定「部分达成、需放宽判据」属误判——第二次测量时模型尚未真正热起来。第三次实测（`qwen3.5:9b`，trace `959a71648d40b20278008adc9a8a597a`，未传任何环境变量）`phase:load = 0.003s`，热调用 load 确实归零，冷/热差异肉眼可辨。spec-013 A5 与 spec-041 边界 5 均改回**「已达成」，判据维持原样不放宽**。(2) 默认路由生效：`backend/app/platform/config.py:118-122` 的 `OLLAMA_ROUTE` 默认已改 `direct`，主服务在不带 `OLLAMA_ROUTE` 环境变量重启后，新 trace 的 metadata `route=direct` 且 5 阶段时长真实（load 0.003s / prefill 0.221s / decode 41.346s），证明生产默认即为直连、观测瀑布图开箱可用。配套：`tests/conftest.py` 新增 autouse fixture 把**测试环境**默认固定回 langchain 以兼容既有 mock（不动生产配置对象），`tests/test_chat_route.py` 的 `test_default_route_is_langchain` 改名 `test_default_route_is_direct` 并显式 patch 验证生产默认值。

- **041 Langfuse 观测：trace 详情与瀑布图** ｜ 实施中 → **已完成（2026-09-21 验收通过）** ｜ 后端全量回归分段跑完（11 批，**2545 passed / 3 failed / 1 collection error / 67 subtests，覆盖 177/177 文件 = 100%**），4 条失败经证实**全部为环境既有**（①`test_online_model_dispatch.py` 缺 `langchain_openai`；②`test_kb_candidate_rebuild.py` broker shim 拦 `mkdir papers`；③④`test_import_compensation.py` 与 `test_spec032_doi_resolver_import.py` 因 broker shim 包装 `shutil.rmtree` 丢失 `avoids_symlink_attacks` 属性致清理提前 return），**真实回归 0**。三项关键行为实测确认：生产默认 `config.OLLAMA_ROUTE == direct`（独立进程，未受 conftest 影响）；`tests/conftest.py` 的 autouse fixture 仅 patch `chat_runner.OLLAMA_ROUTE`、不动 `platform.config`（自建 pytest 插件断言验证 13 passed）；`test_default_route_is_direct` 1 passed。ruff 改动文件 All checks passed、全仓 105 条为存量；改动文件无密钥泄漏。8 条边界全部达成（边界 4 瀑布图 5 阶段条、边界 5 冷/热 load 差异均已实证，A5 曾误判部分达成、第三次热调用 `load=0.003s` 修正）。运行时：主服务 8400 / Langfuse 3000 / ClickHouse 8123 全部 UP，`system.query_log` 持续写入、worker `V4LegacyApiUsageJob` 报错为 0。spec-041 状态置为「已完成」；工作树在分支 feature/spec-041-langfuse-trace-detail 上**尚未 commit**（待用户指示）。

- **041 Langfuse 观测：默认链路切 direct 后的三缺陷修复（2026-09-22 架构师）** ｜ 已完成 → **已完成（口径与延迟统计已修正）** ｜ 默认链路改 direct 后直连首次成为主路径，实测暴露三个此前被掩盖的缺陷，全部修复并落盘：(1) **T-F 全量 500**——qwen3.8 的 Ollama chat template 拒收第二条 system（`Jinja Exception: System message must be at the beginning`），而 `/api/chat` 固定构造 `[system(平台提示), system(USER.md 或空串), user]`，langchain 分支有合并逻辑、direct 分支原样透传，故每个请求 500；新增 `normalize_ollama_messages()` 只对下发 payload 归一化（调用方 messages 保持原样以保留 input 观测的多 system 形态），`_normalize_langchain_messages` 委托它。(2) **T-G 延迟统计失真**——generation 在调用结束后才创建、SDK 不支持 start_time，实测 21.8s 的调用 dur 仅 11ms，导致 P50/P95 与 Dashboard 全部失真；新增 `_backdate_generation_start()` 回填底层 OTel span 起点（实证回填 7000ms 读回差值正好 7000ms），三处起点共用同一 `base`。(3) **T-H 阶段口径错误**——原 `decode=[first_token_ms, first_token_ms+eval_ms]` 把已含思考 token 生成的 `eval_ms` 重复叠加，实测比真实墙钟多出 1.98s，decode 条伸出父 generation、overhead 恒为 0；改为按服务端时间轴四段首尾相接铺满 `[base, base+client_wall_ms]`。修正后实测（trace `16c1c5c4…`，curl 墙钟 22.1s）：GENERATION offset 0 / dur 21294ms，load 15772、prefill 1205、decode 4084、overhead 81ms。

- **042 OpenEval 接入：本地离线 Agent 评测闭环** ｜ 新建 → **待确认** ｜ 2026-09-22：基于 Langfuse 实测数据（一轮实验即产生 178 条 trace，其中 `ollama-chat` 56 条；token 用量仅在 direct 路由下为真实值，56 条中仅 15 条非 0）与 OpenEval 调研（存在名字冲突：`langchain-ai/openevals` / `open-evals.com` / `openeval-cli`），用 grill with docs 梳理 7 个待裁决决策点（选型、数据来源、判官模型、结果落点、评什么指标、首期范围、是否阻塞于路由与 token 埋点），并逐条给出架构师推荐默认值。全仓 `docs/sdd` 检索「openeval / 评测框架」仅命中本次测量报告，**无既有 eval spec，不存在重复实现风险**。spec 按推荐默认起草、状态为「待确认」，**待用户裁决 Q1–Q7 后才可转「已确认」**；同步建档 `plans/042/README.md` 与 `task-02-validate-feasibility.md`（Go/No-Go：验证判官质量、数据桥接、离线成立与 F5 路由矛盾点）。本条目为建档记录，不含任何代码改动。

- **042 OpenEval 接入：本地离线 Agent 评测闭环** ｜ 决策裁决完成（**状态仍为 待确认**）｜ 2026-09-22：用户裁决 Q1=B（`openeval-cli`）、Q2=A（回放 Langfuse trace）、**Q3=B（判官用 `qwen3.5:9b`，用户改判，原推荐 `qwen3.8:27b`）**、Q4=A（回写 Langfuse score 且必须同时落盘本地报告）、Q5=A+B（回答质量 + 记忆正确性）、Q6=A（最小闭环）、Q7=是（Task 02 先复核 F5 路由与 token 矛盾点）。spec 正文已按裁决修订：`judge_model` 默认改为 `qwen3.5:9b`；因 9b 判官能力弱于 27B，「判官一致性基线」由建议项**升级为强制门禁项**。派生第 2 轮问题 **Q8**（9b 未通过一致性门禁时的回退策略，推荐 A：回退 27B 重跑）。状态维持「待确认」，Q8 裁决后方可转「已确认」。

- **042 OpenEval 接入：本地离线 Agent 评测闭环** ｜ grill 决策全部完成（**状态仍为 待确认**）｜ 2026-09-22：**Q8 裁决为 A**——9b 未通过一致性门禁则回退 `qwen3.8:27b`，27b 亦未过则判 No-Go 并退化为「仅导出数据 + 人工标注」。至此 **Q1–Q8 全部裁决完毕，grill 设计树前沿为空**，spec 内容冻结。数据模型 `judge_model` 写入完整回退链；`task-02` 落实为「同时跑 9b 与 27b 两组对照并按链判定唯一选型」。**待用户明确确认 spec 后转「已确认」并从 Task 02 开工**；截至此时仍无任何代码改动。

- **042 OpenEval 接入：本地离线 Agent 评测闭环** ｜ 待确认（**前沿重新打开**）｜ 2026-09-22：用户提问「Langfuse 里也有 evaluation，它用的是什么框架」，据此实证补查本地 Langfuse v4.27.0 源码，新增事实 **F10–F15**：Langfuse **自带 evaluation**（23 个 managed evaluators：Hallucination / Faithfulness / Context Precision / Context Recall / Answer Relevance 等），引擎为 **Vercel AI SDK** 且含 **`@ai-sdk/openai-compatible`（支持自定义 baseURL）**；**未依赖 ragas / deepeval / openevals（依赖计数均为 0）**，Faithfulness 等仅与 Ragas 同名而非调用其库；**本地 Ollama 确实提供 `/v1` OpenAI 兼容端点**（实测返回模型列表）→ judge 可完全离线运行；但 Langfuse 当前 `.env` 中 judge LLM 配置为 **0 条**，评测暂不可用需先配 LLM connection。该事实**动摇已裁决的 Q1（选型）与 Q4（score 回写）**，故新增第 3 轮问题 **Q9**（A 全用 Langfuse 内置 / B 维持 openeval-cli / C 混合，推荐 C），spec **内容由「冻结」回退为未冻结**，状态仍为「待确认」，待裁 Q9 后再确认。仍无任何代码改动。

- **042 OpenEval 接入：本地离线 Agent 评测闭环** ｜ 待确认（**Q9 裁决完成，前沿重新为空、内容重新冻结**）｜ 2026-09-22：**Q9 裁决为 C（混合）**——通用维度（回答质量 / 忠实度 / 上下文相关性）用 **Langfuse 内置 evaluators**，score 由 Langfuse **原生回写、零成本**；**记忆正确性**（Q5-B，23 个内置模板均不覆盖）用外部自定义判官。随之**修订 Q1**（保留 `openeval-cli` 但范围收窄为仅服务记忆正确性）与 **Q4**（通用维度不再自建回写）。Q3 / Q8 / Q7 不变。新增前置动作：Task 02 须先为 Langfuse 配置指向 `http://localhost:11434/v1` 的 LLM connection（当前 judge 配置为 0 条）。另按用户提供的参考文章（cnblogs《使用 Langfuse 实现应用可观测性的实践（Prompt，RAGAS，Score）》）提炼 **R1–R8** 并入 spec：两种评估路径之分（印证 Q2=A 离线回放）、测试全量/生产采样、Ragas 指标 Langfuse 已内置故无需引入 ragas、自定义判官「Explanation + 枚举 Answer」范式、评估步骤用 `as_type="evaluator"` 记录、多轮 session 归组、SDK 与服务端 v4.27.0 版本匹配坑、score 支持枚举标签（记忆正确性建议用 `remembered`/`partially_remembered`/`forgotten`/`fabricated`）。派生待验证项交 Task 02：若「自定义 prompt 判官 + create_score」已足够，则 openeval-cli 可能整体不必要，届时按范围变更重新确认。状态仍为「待确认」，仍无任何代码改动。

- **042 OpenEval 接入：本地离线 Agent 评测闭环** ｜ 已确认 → **实施中（Q9 执行路径修订，闭环已跑通）** ｜ 2026-09-22：Task 02 第二轮实测新增 **F16**：SSRF 白名单（`LANGFUSE_LLM_CONNECTION_WHITELISTED_HOST`/`_IPS`）放行后 Langfuse 已能连本机 Ollama（`llm-connections` 201、创建 evaluator 200、worker 日志实证连到 127.0.0.1:11434）；**F17（关键阻塞）**：创建规则仍返回 422 `No object generated: response did not match schema`，根因是 **Ollama 的 OpenAI 兼容 `/v1` 端点不支持 `response_format: json_schema`（strict）**，Langfuse 内置结构化输出判官引擎依赖该模式 → **内置 evaluator 在本机产不出 score**（端点能力限制，禁止改业务代码绕过）。**Q9=C 前半段据此证伪，修订为「全部维度走自建判官、Langfuse 仅作 score 落点」**（Q4 不变），依据为自建判官实测可用（chat_quality：9b/27b 自一致率均 1.0、跨判官一致率 1.0，n=20）。第三轮实测**闭环已跑通**：自建判官 → 读 Langfuse 727 条 → 写回 score 成功（id `8f24dd05`）→ 删除校验 202；产物 `plans/042/task-02-run-eval.py` 与 `plans/042/task-02-eval-run-summary.json`。待办：步骤 4 离线校验的进程级精确采样、步骤 5 选型结论、Go/No-Go 报告仍未产出。

- **042 OpenEval 接入：本地离线 Agent 评测闭环** ｜ 实施中 → **Task 02 已完成（Go/No-Go 判定：Go）** ｜ 2026-09-23：补齐步骤 4 与步骤 5 并产出判定报告 `plans/042/task-02-gono-go-report.md`。五条验收结论：①路由与 token **Go**（主生成 `direct`+`qwen3.8:27b` token 真实；旁路 `langchain`+`qwen3.5:9b` 仍 0-token，记为遗留 L1，归 spec-013/041）；②判官可用 **Go**——`chat_quality` 上 9b/27b 自一致率均 1.0、跨判官一致率 1.0（n=20），`adopt: qwen3.5:9b`；`memory_correctness` 自一致 1.0 但跨判官仅 0.5（n=6），根因为数据集缺专门记忆探针，**Deferred 至 task 03**（遗留 L2，未伪造结论）；③桥接 **Go**（数据集 24 条，SKIPPED 判定正确，写回 score 成功 id `8f24dd05`、删除校验 202）；④离线 **Go**（`offline_guard` 结构性保证非 loopback 即拒，且完整闭环仅涉 127.0.0.1）；⑤选型 **Go**——因 F17（Ollama `/v1` 不支持 strict `json_schema`）内置 evaluator 不可行，修订为自建判官 + Langfuse 作 score 落点，**chat_quality 上 openeval-cli 不再必要**。总体判 **Go**，首期 `chat_quality` 评测闭环可落地。Task 02 状态置为已完成。

- **042 OpenEval 接入：本地离线 Agent 评测闭环** ｜ **待确认 → 已确认** ｜ 2026-09-22：用户明确确认 spec（Q1–Q9 全部裁决完毕、grill 前沿为空、内容已冻结），并指定**主 agent 为架构师自身、子 agent 使用 `hy3`（0.00 倍率，临时决策）**。自此刻起进入实施阶段，从 **Task 02（Go/No-Go）** 开工：先复核 F5 路由与 token 矛盾点，再配置 Langfuse judge LLM connection（指向本机 Ollama `/v1`），随后做 9b 与 27b 判官一致性对照、数据桥接验证与离线校验。若任一前提不成立即判 No-Go，回 spec-013/041 处理，不在本 spec 内扩大范围。
- **042 OpenEval 接入：本地离线 Agent 评测闭环** ｜ 实施中（Task 02 Go）→ **Task 03 已完成（`memory_correctness` 维度判定 `adopt:qwen3.5:9b`）** ｜ 2026-09-23：新建 `plans/042/task-03-memory-probe.md` 并由 `backend-dev`（hy3）实施，用于收敛 Task 02 遗留项 **L2**（该维度跨判官一致率仅 0.5）。根因确认为**输入不适定（ill-posed）**——Task 02 的 24 条样本全部来自真实 `ollama-chat` trace、**无任何「先前陈述偏好 → 后续追问」的记忆探针**，判官被迫四选一、标签实质随机。本 Task 构造 **20 条专用记忆探针**（4 类 gold 各 5 条：`remembered`/`partially_remembered`/`forgotten`/`fabricated`，一律 `synthetic: true`，不冒充真实 trace），并把 `memory_correctness` 判官 prompt 升级为 `{ctx}`(prior context)/`{q}`(追问)/`{a}`(回答) 三段式（`chat_quality` prompt 未动）。实测（20 探针 × 2 判官 × 3 次 = 120 次调用，温度 0，全部经 `offline_guard` 仅访问本机 Ollama）：**G1 自一致 1.0（n=40 块）/ G2 判别有效性 0.975 / G3 跨判官一致 0.95（n=20 对）**，unavailable 0/120。三项门禁全部过阈，按 Q8=A 裁决链给出**唯一 decision `adopt:qwen3.5:9b`**（9b G1=1.0/G2=0.95，27b G1=1.0/G2=1.0）。唯一失分样本 `mp-par-04`（gold=partially_remembered，漏掉「16G 内存」）：9b 三次一致判 `forgotten`、27b 判 `partially_remembered`，是两判官唯一一次分歧，属 `partial`/`forgotten` 边界天然模糊，**不构成判官失效**。产物：`task-03-memory-probe-result.json` / `-report.md` / `-progress.ndjson` / `-run.log`；代码：新增 `backend/eval_042/memory_probe.py` 与 `test_memory_probe.py`（19 passed，纯函数无网络），改 `config.py`（新阈值常量 + 三段式模板）与 `judge_client.py`（可选 `ctx`，向后兼容）。架构师回读校验：result JSON 与报告数值自洽（G2=(19+20)/40=0.975、G3=19/20=0.95），`chat_quality` 判官路径实测仍 `scored/good/1.0` 无回归。**如实标注：gold 为构造真值、非人工标注**，只证明判别有效性下界高，人类一致率仍待后续真实记忆 trace + 人工标注补算。spec 未新增决策点，范围不变。
