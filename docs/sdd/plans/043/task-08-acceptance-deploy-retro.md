# Task 08 — 最终验收与收口

> 关联：[Spec043](../../specs/043-literature-map-topic-exploration.md) ｜ 索引：[README](./README.md)  
> 依赖：02–07阶段已完成；被依赖：无；当前状态：**已完成（2026-10-22；候选 `a328932` 的 runtime、browser、全量回归与部署验证通过，tester 与 architect 双签；用户人工验收尚未实际执行）**。

## 一句话目标

用最终候选真实证据完成API、浏览器、全量回归、独立验收和部署交付。

## 当前证据与前置条件

- 历史候选 `1a3ff26` 的真实 Task08 API E2E 已归档：服务 `http://127.0.0.1:8000/` ready，fresh map `35a56c6f2da84fca85fc3c21dfa0055c` 从 limit=20 受控恢复到 20 nodes/11 citation/5 similarity，references preview 45 候选确认 1 后最终 21 nodes/17 edges/revision 3；幂等/CAS409、项目解绑旧 conversation snapshot、项目删除仅解绑及 map 删除保护共享 KB/旧会话均通过。该历史资产与最终候选证据分开标注。
- Task07 最终候选 `1a3ff26` 已有真实 Chromium/CDP 375/390/1440 PASS：global-nav/详情普通 close、列表/详情抽屉、滚动、pan/pinch 保存重开、桌面拖动/1280 resize 与无横溢通过；摘要/历史 v1/v2 和全文按钮可用，未重复触发全文分析 POST。Task05 `82c816f` 的全文 API PASS 继续作为完整全文分析/会话证据。
- Task08 全量回归首轮 `map_regression_preflight` 的 `3191 passed / 18 failed / 14 skipped / 67 subtests / 5 warnings` BLOCK 继续作为历史证据保留；a328932 最终重跑已 exit 0（`3224 passed / 0 failed / 2 skipped / 67 subtests / 5 warnings`），两个 skip 是未设置 `RUN_E2E` 的合法 guard。运行中 job 的 stop 保留成果与进程重启恢复、最终 runtime/browser smoke 和列表关闭延迟复核均已有独立证据，不能把首轮失败覆盖为成功。
- 复用代码位置是调研入口，未来实现时需对照实际提交核实，不复制过期实现。后续新增模块/前端文件按前置Task固定报告定位，不猜文件名。
- Spec处于待确认时禁止实现。需求/技术门禁通过及用户明确确认后，先核对工作区/实现分支，保护Spec032暂停快照及其他任务修改。
- 前置Task真实通过后才能执行；若预生成接口尚未冻结，应标阻塞而非自行发明第二套合同。

## 最小上下文

- `docs/sdd/specs/043-literature-map-topic-exploration.md（本Task有关章节）`
- `docs/sdd/plans/043/README.md`
- `docs/sdd/specs/043-literature-map-topic-exploration.md`
- `docs/sdd/plans/043/README.md`
- `docs/sdd/plans/043/artifacts/ 下前序固定报告`
- `deploy/README.md`
- `deploy/VERIFICATION.md`

## 数据、配置与接口增量

- 以Spec数据模型和端点章节为边界；只扩展本Task所需行为，不重定义Task03已冻结身份/事件/迁移合同。
- 地图范围最多200节点；首批默认30可20/50，扩展apply每批最多20。任何测试样例不得暗中改阈值或范围。
- 后端与前端交接固定输入输出、错误码和可观察状态，类型/版本变化先更新接口交接。

## 实施步骤与文件边界

1. 先核对Task02–07实际结果、公开合同与真实缺口，不按代码存在判完成；读spec-acceptance-protocol执行真实API门禁。
2. 选Task02已证明的主题，新map/job从主题创建，核对真实论文/引用/相似依据，保存重开、预览apply、停止/补缺/重启和200上限；真实请求与合成测试分开标记。
3. 验证入库/人工恢复桥接、项目删除解绑、地图删除不删原件、摘要/全文分析和会话隔离、PNG/JSON、手机与桌面。
4. 真实浏览器记录关键截图（列表/图谱/详情、进度与预览、手机抽屉）；界面无P0/P1。明确引用不可得等partial，不用截图假图充当完成。
5. 最终候选运行项目现有全量回归命令并记录退出码/通过数量/失败项；失败同范围定向修复后重跑全量。不得在中间Task重复全量。
6. 整理逐步人工验收：访问URL/端口/前置条件、每步点什么/看到什么/等什么/下一步/失败恢复/产物路径；十项准备度>=9且无核心缺失才交付。
7. tester出真实验收报告，architect签字，需求/技术最终结论与引用路径核实，补复盘、Task/README/spec及状态changelog。
8. 最终提交与精确版本部署，验证首页/ready/地图及会话关键接口；报告实际命令/地址/版本，未经新授权不push/main合并。

允许范围：测试、验收、部署与文档同步；代码修复仍分派对应端，不由测试者盲改业务。部署权限与数据备份按项目文档。

## 子任务拆分与分派

1. backend-tester：只承担本端/本角色步骤，使用上述最小上下文；当前模型从角色配置读取，实际调用遵循当次用户覆盖，不在本Task固化临时型号。
2. frontend-tester：只承担本端/本角色步骤，使用上述最小上下文；当前模型从角色配置读取，实际调用遵循当次用户覆盖，不在本Task固化临时型号。
3. tester：只承担本端/本角色步骤，使用上述最小上下文；当前模型从角色配置读取，实际调用遵循当次用户覆盖，不在本Task固化临时型号。


- 主会话负责依赖接续与裁决；长报告落盘读回，不以口头“改好了”直接接部署。日志按spec/task/角色分层。

## 可直接使用的分派 Prompt

### backend-tester

```text
角色：backend-tester。模型按本次主会话明确分派；不修改长期配置。Spec043 Task08：最终验收与收口。
目标：用最终候选真实证据完成API、浏览器、全量回归、独立验收和部署交付。
只读取本Task、关联Spec有关章节、前置任务固定交接报告，以及“最小上下文”列出的本端必要文件。角色技能按项目绑定加载，不全仓扫描；前端不要读取后端实现，后端不要扫描前端vendor。
允许范围：本Task所需测试、证据与报告；不得直接修改业务代码。报告例外写本Task artifacts 下固定报告，进展日志写 .codebuddy/agent-logs/spec-043/task-08/backend-tester/。
执行本Task实施步骤中属于本角色的部分；跨端公开契约只以已冻结文档为准，缺失或冲突先报告主会话，不自行猜测。
禁止：未确认就实现、扩大Spec、重写下载/embedding/chat框架、读取或输出.env凭据、保存隐藏推理、篡改旧研究任务、清空数据库、覆盖用户修改、自动push/合并main、伪造验证或提前宣称部署。
完成后可观察状态：本Task验收标准属于本端的条目达到，并明确尚未由真实API/浏览器验证的部分。
验证：运行本Task“验证命令”中属于本端的精确命令，补充实际改动文件ruff/语法或前端静态检查；除Task08最终收口外不跑全量。
返回并落盘：结果状态/摘要；改动文件；命令、退出码、通过数；产物路径；决策依据；风险与阻塞；主会话下一动作；开始/结束/耗时；可取得时记录模型/token/工具次数，不编造缺失指标。
```

### frontend-tester

```text
角色：frontend-tester。模型按本次主会话明确分派；不修改长期配置。Spec043 Task08：最终验收与收口。
目标：用最终候选真实证据完成API、浏览器、全量回归、独立验收和部署交付。
只读取本Task、关联Spec有关章节、前置任务固定交接报告，以及“最小上下文”列出的本端必要文件。角色技能按项目绑定加载，不全仓扫描；前端不要读取后端实现，后端不要扫描前端vendor。
允许范围：frontend/** 与本Task对应的前端契约测试；不得修改backend/**。报告例外写本Task artifacts 下固定报告，进展日志写 .codebuddy/agent-logs/spec-043/task-08/frontend-tester/。
执行本Task实施步骤中属于本角色的部分；跨端公开契约只以已冻结文档为准，缺失或冲突先报告主会话，不自行猜测。
禁止：未确认就实现、扩大Spec、重写下载/embedding/chat框架、读取或输出.env凭据、保存隐藏推理、篡改旧研究任务、清空数据库、覆盖用户修改、自动push/合并main、伪造验证或提前宣称部署。
完成后可观察状态：本Task验收标准属于本端的条目达到，并明确尚未由真实API/浏览器验证的部分。
验证：运行本Task“验证命令”中属于本端的精确命令，补充实际改动文件ruff/语法或前端静态检查；除Task08最终收口外不跑全量。
返回并落盘：结果状态/摘要；改动文件；命令、退出码、通过数；产物路径；决策依据；风险与阻塞；主会话下一动作；开始/结束/耗时；可取得时记录模型/token/工具次数，不编造缺失指标。
```

### tester

```text
角色：tester。模型按本次主会话明确分派；不修改长期配置。Spec043 Task08：最终验收与收口。
目标：用最终候选真实证据完成API、浏览器、全量回归、独立验收和部署交付。
只读取本Task、关联Spec有关章节、前置任务固定交接报告，以及“最小上下文”列出的本端必要文件。角色技能按项目绑定加载，不全仓扫描；前端不要读取后端实现，后端不要扫描前端vendor。
允许范围：本Task所需测试、证据与报告；不得直接修改业务代码。报告例外写本Task artifacts 下固定报告，进展日志写 .codebuddy/agent-logs/spec-043/task-08/tester/。
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
- `项目现有全量回归命令：先从pytest配置/CI查明并写入报告，不凭空声称数量`
- `.venv/bin/python scripts/check_test_layout.py`
- `真实HTTP/浏览器检查命令及请求由测试报告完整保存`

- 最终真实API E2E成功、关键图谱/导出/分析/会话产物可复核。
- 全量回归退出0、独立验收签字、状态/复盘/部署检查均真实完成。
- 完整人工步骤可复现且准备度>=9/10，无P0/P1/API失败/关键产物缺失。
- 测试文件/函数名不含spec/task数字，源码归领域子目录；全量回归只在Task08最终候选。
- 本Task结果不足时标明“不通过/阻塞”，不得记录为“已完成”。

## 风险、停止条件与回滚

任何核心API失败、未签字、全量失败或关键产物缺失均不标Spec完成，不要求用户代排错；记录阻塞及可行动下一步。
- 保留用户数据和已完成结果；迁移前备份，回滚禁用新增入口/作业，不删共享目录/KB/旧报告，不reset/stash/clean覆盖修改。
- 真实外部API限流/权限失败保留脱敏证据，说明具体下一步，不绕过访问控制。
- Spec范围或公开接口发生实质变化先回架构师/用户确认，不靠实现者自由设计补齐。

## 产出物

- `artifacts/task-08/api-e2e-evidence.json`（待执行后生成）
- `artifacts/task-08/manual-acceptance.md`（待执行后生成）
- `artifacts/task-08/regression-report.md`（待执行后生成）
- `artifacts/task-08/deployment-verification.md`（待执行后生成）
- `artifacts/task-08/retrospective.md`（待执行后生成）
- 代码/测试/评审与本Task交付应可追溯到同一候选提交；上述固定文件追加修复记录，不重复建多轮报告。
- artifacts路径均相对 `docs/sdd/plans/043/`。目前未产生，不预造结果或真实数据。

## 执行结果

### 2026-10-21 当前阶段同步

- Task08 live API 候选：`1a3ff26`，URL `http://127.0.0.1:8000/`；fresh map `35a56c6f2da84fca85fc3c21dfa0055c`。真实初始 limit=20，受控 retry 后 20 nodes / 11 citation / 5 similarity；references preview 45 candidates，确认 1 后最终 21 nodes / 17 edges / revision 3，partial warning 保留。
- 已真实通过：apply 同键幂等、旧 revision CAS409、project unbind 后旧 conversation snapshot、临时 project 删除仅解绑 map、临时 map 删除后旧 conversation 与共享 KB 保留。
- Task07 候选 `1a3ff26` 真实 375/390/1440 浏览器 PASS；Task05 API 全文 PASS，当前浏览器页面已显示摘要/历史 v1/v2 与全文按钮可用。本阶段未重复全文 POST，沿用既有 API 证据。
- `map_regression_preflight` 首轮隔离全量已 BLOCK（3191 passed / 18 failed / 14 skipped / 67 subtests / 5 warnings），root 正在分派同范围修复与重跑；运行中 job 的 stop 保留成果与进程重启恢复已真实 PASS。最终全量通过结果、最终部署、tester/architect 签字尚未产生，因此本 Task 仍为 **进行中 / BLOCKED_NOT_READY**，不得标记 Spec 完成。

### 2026-10-22 最终候选收口

- 候选 `a328932` 的最终全量回归在 `09:19:28Z–09:31:55Z` 完成，真实 `exit 0`，结果为 `3224 passed / 0 failed / 2 skipped / 67 subtests / 5 warnings`；2 个 skip 均为未设置 `RUN_E2E` 的既有 guard。首轮 2026-10-21 `3191/18/14/67/5` BLOCK 保留为历史，不改写。
- 当前部署命令为 `PORT=8000 RERANKER_ENABLED=false ./deploy/start.sh`，入口 `http://127.0.0.1:8000/`；runtime 已验证 ready/health/home、fresh `35a56...` 21/17 rev5、GAT `0baabe...` 21/18 rev124、全文 document/application binding；browser 已验证桌面/375、全文历史、两图以及列表关闭动画完成后的 hidden 状态。
- tester 与 architect 已完成最终双签，coverage/manual/review/部署证据均已绑定 a328932；Task08 当前状态为 **已完成**。`READY_FOR_USER` 表示人工验收材料已可交给用户执行，用户尚未实际执行本文步骤，不宣称用户已通过。

## 变更日志

- 2026-10-19：主会话依据已确认讨论纯文档代行建档，非独立评审；Task保持待执行，未改业务代码。
- 2026-10-22：同步 a328932 最终全量/runtime/browser/deployment 证据、tester/architect 双签与用户人工验收边界；保留 2026-10-21 首轮 BLOCK 及所有历史限制，Task08/Spec043 收口为已完成。
