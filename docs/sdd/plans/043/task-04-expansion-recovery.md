# Task 04 — 扩展与恢复

> 关联：[Spec043](../../specs/043-literature-map-topic-exploration.md) ｜ 索引：[README](./README.md)  
> 依赖：03；被依赖：05、06；当前状态：**进行中（冻结增量合同）**。

## 一句话目标

用户可预览并确认扩展/刷新，作业停止或重启后不丢成果、重复抓取或复活已移除节点。

## 当前证据与前置条件

- Task03真实纵向阶段门禁PASS_WITH_LIMITATIONS，保留provider引用partial及既有KB异步v2问题。增量合同见 `artifacts/task-04/interface-contract.md`；本Task已开始分端开发，尚未评审、验收或部署。
- 复用代码位置是调研入口，未来实现时需对照实际提交核实，不复制过期实现。后续新增模块/前端文件按前置Task固定报告定位，不猜文件名。
- Spec处于待确认时禁止实现。需求/技术门禁通过及用户明确确认后，先核对工作区/实现分支，保护Spec032暂停快照及其他任务修改。
- 前置Task真实通过后才能执行；若预生成接口尚未冻结，应标阻塞而非自行发明第二套合同。

## 最小上下文

- `docs/sdd/specs/043-literature-map-topic-exploration.md（本Task有关章节）`
- `docs/sdd/plans/043/README.md`
- `backend/app/literature_maps/`
- `backend/app/paper_discovery/infrastructure/semantic_scholar_metadata.py`
- `frontend/ 地图组件（以Task03报告为准）`

## 数据、配置与接口增量

- 以Spec数据模型和端点章节为边界；只扩展本Task所需行为，不重定义Task03已冻结身份/事件/迁移合同。
- 地图范围最多200节点；首批默认30可20/50，扩展apply每批最多20。任何测试样例不得暗中改阈值或范围。
- 后端与前端交接固定输入输出、错误码和可观察状态，类型/版本变化先更新接口交接。

## 实施步骤与文件边界

1. 在Task03冻结合同上实现topic/references/citations/refresh preview，不修改既有节点集；候选标记已有/新增/缺失来源，继承地图原始范围。
2. preview apply要求base/expected_revision和幂等key，重新检查owner/节点归属/身份去重/选中最多20/总数200；冲突返回409并提示重新预览，不覆盖用户变化。
3. 刷新按差异确认补元数据/边；保护位置、人工分组、移除墓碑。明确用户重新加入才清墓碑。
4. 完成stop/cancel安全边界、有限退避后的failed/partial终态、失败单元retry与相似层补算；正常已有缓存/成功单元不重复抓取。restart仅重入队可恢复工作。
5. 处理删除地图与在途任务竞态：阻止晚回调创建节点；停止不删已有图，不改历史研究任务。
6. 前端显示预览勾选、可加入数量/上限、范围不足、刷新差异、409、等待退避与失败补缺入口；不无限转圈。

允许范围：仅literature_maps应用/仓储/路由及地图前端，必要复用现有client。禁止第二套限流器或搜索缓存。

## 子任务拆分与分派

1. backend-dev：只承担本端/本角色步骤，使用上述最小上下文；当前模型从角色配置读取，实际调用遵循当次用户覆盖，不在本Task固化临时型号。
2. frontend-dev：只承担本端/本角色步骤，使用上述最小上下文；当前模型从角色配置读取，实际调用遵循当次用户覆盖，不在本Task固化临时型号。
- 后端完成后由独立 backend-reviewer 复核，backend-tester 运行后端精准验证。
- 前端完成后由独立 frontend-reviewer 复核，frontend-tester 做DOM/版本/XSS/交互契约与浏览器核对；不因前端单端改动运行后端全量。
- 主会话负责依赖接续与裁决；长报告落盘读回，不以口头“改好了”直接接部署。日志按spec/task/角色分层。

## 可直接使用的分派 Prompt

### backend-dev

```text
角色：backend-dev。模型按本次主会话明确分派；不修改长期配置。Spec043 Task04：扩展与恢复。
目标：用户可预览并确认扩展/刷新，作业停止或重启后不丢成果、重复抓取或复活已移除节点。
只读取本Task、关联Spec有关章节、前置任务固定交接报告，以及“最小上下文”列出的本端必要文件。角色技能按项目绑定加载，不全仓扫描；前端不要读取后端实现，后端不要扫描前端vendor。
允许范围：backend/** 与 tests/literature_maps/（必要时既有受影响后端领域测试）；不得修改frontend/**。报告例外写本Task artifacts 下固定报告，进展日志写 .codebuddy/agent-logs/spec-043/task-04/backend-dev/。
执行本Task实施步骤中属于本角色的部分；跨端公开契约只以已冻结文档为准，缺失或冲突先报告主会话，不自行猜测。
禁止：未确认就实现、扩大Spec、重写下载/embedding/chat框架、读取或输出.env凭据、保存隐藏推理、篡改旧研究任务、清空数据库、覆盖用户修改、自动push/合并main、伪造验证或提前宣称部署。
完成后可观察状态：本Task验收标准属于本端的条目达到，并明确尚未由真实API/浏览器验证的部分。
验证：运行本Task“验证命令”中属于本端的精确命令，补充实际改动文件ruff/语法或前端静态检查；除Task08最终收口外不跑全量。
返回并落盘：结果状态/摘要；改动文件；命令、退出码、通过数；产物路径；决策依据；风险与阻塞；主会话下一动作；开始/结束/耗时；可取得时记录模型/token/工具次数，不编造缺失指标。
```

### frontend-dev

```text
角色：frontend-dev。模型按本次主会话明确分派；不修改长期配置。Spec043 Task04：扩展与恢复。
目标：用户可预览并确认扩展/刷新，作业停止或重启后不丢成果、重复抓取或复活已移除节点。
只读取本Task、关联Spec有关章节、前置任务固定交接报告，以及“最小上下文”列出的本端必要文件。角色技能按项目绑定加载，不全仓扫描；前端不要读取后端实现，后端不要扫描前端vendor。
允许范围：frontend/** 与本Task对应的前端契约测试；不得修改backend/**。报告例外写本Task artifacts 下固定报告，进展日志写 .codebuddy/agent-logs/spec-043/task-04/frontend-dev/。
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
- `.venv/bin/python -m pytest -q tests/literature_maps/test_map_expansion.py tests/literature_maps/test_map_job_recovery.py tests/literature_maps/test_map_revision_conflicts.py`
- `.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_expansion.py`

- 预览不改图、确认只加入选择的有效候选，重复确认不重复节点。
- 199→最多200、超过20/200拒绝、移除重加、两客户端冲突可恢复。
- 真实新run扩展/刷新及受控重启后保留已完成结果，证据区分mock恢复测试与真实smoke。
- 测试文件/函数名不含spec/task数字，源码归领域子目录；全量回归只在Task08最终候选。
- 本Task结果不足时标明“不通过/阻塞”，不得记录为“已完成”。

## 风险、停止条件与回滚

出现跨owner/晚回调复活/数据丢失或无限重试时阻塞该Task，不用删除库解决。
- 保留用户数据和已完成结果；迁移前备份，回滚禁用新增入口/作业，不删共享目录/KB/旧报告，不reset/stash/clean覆盖修改。
- 真实外部API限流/权限失败保留脱敏证据，说明具体下一步，不绕过访问控制。
- Spec范围或公开接口发生实质变化先回架构师/用户确认，不靠实现者自由设计补齐。

## 产出物

- `artifacts/task-04/backend-report.md`（待执行后生成）
- `artifacts/task-04/frontend-report.md`（待执行后生成）
- `artifacts/task-04/recovery-evidence.json`（待执行后生成）
- 代码/测试/评审与本Task交付应可追溯到同一候选提交；上述固定文件追加修复记录，不重复建多轮报告。
- artifacts路径均相对 `docs/sdd/plans/043/`。目前未产生，不预造结果或真实数据。

## 执行结果

待执行后填写。

## 变更日志

- 2026-10-19：主会话依据已确认讨论纯文档代行建档，非独立评审；Task保持待执行，未改业务代码。
