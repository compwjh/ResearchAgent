# 2026-11-07 复盘：Spec043 卡片设置列表 + 重命名／删除地图批次

## 1. 概览

用户反馈「设置标签只是卡片设置里的其中一个功能，弹出的是设置列表，还有设置标签的框太大了，缩小点」，随后选择方案 C「那你把新增重命名/删除地图 作进来吧」，最后回复 `直接开工` 确认按 6 项默认值执行。本批次把原来的「`⋯` 一步弹出标签面板」改成两级「卡片设置」列表，新增重命名与删除，缩小面板，并修复删除地图后标签绑定孤儿行。

结果：**已完成**。Gate 2 双评审通过 → 用户确认 → 跨端分派实现 → 4 轮定向修复 → 分端评审与复审 GO → 真实 API / 浏览器 E2E → 部署运行时验证 → Gate 5 验收 16/16 + 签字 + APPROVE → 台账与本地提交。

## 2. 时间线与分工

| 阶段 | 承担角色 | 产出 |
|---|---|---|
| 只读调查 + spec 修订（范围扩大） | 主会话 | spec C 段、5→6 个决策点 |
| 用户 `直接开工` 确认 + 状态冻结 | 主会话 | spec 两段状态、台账 |
| Gate 2 需求／技术评审 | `architect` | `043-card-settings-{requirement,tech}-review.md`，Q-1~Q-6 / T-1~T-12 |
| 后端实现（1 行绑定清理） | `backend-dev` | `store.py` + `test_map_delete_tag_bindings.py`（283→309 passed） |
| 前端实现（两级菜单等） | `frontend-dev` | JS/CSS + 版本号 + 静态契约（427→435 passed） |
| 分端评审 | `backend-reviewer` / `frontend-reviewer` | 后端 GO / 前端 GO（含 P1-01） |
| P1-01 修复 + 复审 | `frontend-dev` / `frontend-reviewer` | 435→437 passed，复审 GO |
| 真实 API E2E 暴露 P0 | 主会话（验证）+ `backend-dev` / `backend-reviewer` | 503 根因、P0 修复、315 passed、增量复审 GO 附条件 |
| 真实浏览器 E2E 暴露 P1-02 / P1-03 | 主会话（验证）+ `frontend-dev` | 宽度锁定、空态高度，437→438→439 passed |
| 集中复审 | `frontend-reviewer` | P1 全 CLOSED，GO |
| 跨端验收 / 签字 / 裁决 | `tester` / `architect` | 16/16 通过、签字、APPROVE |
| 收口 | 主会话 | spec 收口记录、台账、本复盘、本地 commit |

含代码文件的改动全部由 `backend-dev` / `frontend-dev` 分派完成；主会话只做编排、读回校验与纯文档同步。

## 3. 做对了什么

1. **范围扩大先停再动**：用户加「重命名／删除地图」时没有直接开工，而是先只读核实既有 `PATCH` / `DELETE` 端点、软删语义与标签绑定接缝，把范围扩大写入 spec 并请求再次确认；用户 `直接开工` 后冻结 6 项默认值，实施未越界。
2. **Gate 2 约束沉淀到 spec**：评审的 Q/T 编号逐条写入 spec「强制约束」段，并直接作为后续分派 prompt 的验收清单，减少返工。
3. **子代理「说改了」不算改了**：每轮分派后主会话都 `git diff` / `Read` 读回，独立复跑 `node --check`、前后端 pytest、`check_test_layout.py`、`innerHTML` 计数，四次定向修复的数字都可复现。
4. **诚实性验证**：后端两轮修复都做了「移走改动 → 新测试失败 → 复原 → 通过」，测试断言非恒真；首次 API E2E 失败产物另存 `...-first-run-failed.json`，没有覆盖或冒充通过。
5. **真实运行证据齐全**：API E2E 落盘请求/响应/实体 ID/最终状态；浏览器 E2E 落盘 6 张截图 + 逐层盒模型 + 可复现脚本；部署后 `?v=31/45` 5/5 200。
6. **既有缺陷不掩盖**：全量回归 2 个失败用「未含本批次改动的 HEAD 快照」复跑确认同源，如实登记为既有独立缺陷并建议另开 Bug Spec，既没写成通过，也没把它算成本批次失败。

## 4. 缺陷与根因（本批次最有价值的部分）

| 编号 | 现象 | 根因 | 修复 |
|---|---|---|---|
| P0 | `PATCH /{map_id}` 只带 `{expected_revision,name}` 稳定 503，重命名主路径不可用 | `service.py:54` 与 `store.py:45` **各自定义** `_UNSET = object()`；service 把自身哨兵转发给 store，store 的 `project_id is _UNSET` 判定为假，把裸 `object()` 绑进 SQLite → `ProgrammingError` → `_error()` 归 503 | `service.update_map()` 未显式传 `project_id` 时省略该参数；显式传（含 `None`）照旧转发并保留校验。合约不变 |
| P1-01 | 删除后列表重取失败只有通用「地图列表加载失败」 | 调用方未区分「本地已移除」语义 | `loadMaps()` 返回 boolean，`finalizeMapDeletion()` 补专属提示；5xx 兜底改为场景文案 |
| P1-02 | 二级面板宽 160（应 200），高 121.8 | `positionTagMenu()` 每次定位写内联 `maxWidth`，一级量到 160 后压住二级 CSS 的 200，内容换行 | 测量前清除 `maxWidth` / `minWidth` / `width` 内联约束，测完再设 |
| P1-03 | 宽度修好后高度仍 121.8 > 105 | `send-button` 全局样式未压，`new` 表单行 44px；空态 `options` 白占一个 gap | `:empty` 隐藏、`padding-top 8→4`、create 按钮压到 24px、panel `gap 6→4` → **200×94.8** |

**共性教训**：静态契约测试与单元测试都是绿的，四个缺陷全部由**真实运行**（HTTP 请求 / 真实 Chromium 盒模型）暴露。静态断言能锁住结构，锁不住「跨模块哨兵对象是否同一实例」和「CSS 内联样式是否会覆盖类规则」。以后凡涉及跨模块默认值传递或尺寸指标，必须把真实 E2E 提前到实现阶段，而不是留到收口。

## 5. 分派通道与档位

- 默认档 `Deepseek-V4.1-Flash` 在本批次绝大多数分派正常（Gate 2、两轮 dev、两轮 reviewer、tester 均成功）。
- 最后 `architect` 签字分派连续两次 429。按 `SUBAGENT-ORCHESTRATION.md`「重试 → 换档 → 记录阻塞」处置：重试仍 429 后，主会话临时把 `.codebuddy/agents/architect.md` 的 `model` 改为历史验证过的 `hy3` 完成签字（用户 2026-11-07 早前曾授权过临时 hy3；本轮是规则内应急处置，**不是本轮重新授权**），完成后立即还原 `model: Deepseek-V4.1-Flash`，`git diff -- .codebuddy/agents/` 为空，临时档位未写入任何规范文档。
- 第一次 429 的分派实际已在磁盘上落过一版签名（回传丢失但产出存在），再次印证「子代理说改了/报错了都要读回磁盘确认」。

## 6. 数据

- 前端 `439 passed`（基线 427）；后端三路径 `315 passed`（基线 306+3）；`node --check` 0；布局/命名校验 ok；`innerHTML` 0、`fetch(` 3。
- 全量回归 `2 failed, 4011 passed, 2 skipped, 67 subtests passed`，exit 1（2 个为 HEAD 既有缺陷，见第 3 节第 6 点）。
- 真实 API E2E **16/16**：创建地图 → 绑标签 → PATCH 200（revision 0→1）→ GET 复核 → 旧 revision 409 `MAP_CONFLICT` → DELETE 204 → 列表不含 → 绑定表 0 残留、其它绑定不受影响。
- 真实浏览器 E2E **32/32**：1440 一级 `160×136`、二级 `200×94.8`；760 触发器 `44×44`、两级面板在视口内、不遮挡卡片文本；`page_errors=[]`。
- 部署：`127.0.0.1:8000`（launchctl 托管，PID 39227），5/5 端点 200，首页静态引用确为 `css?v=31` / `js?v=45`。

## 7. 未做到项与遗留

- 人工验收 8 步**未由用户实际走查**；已由真实 Chromium 自动化按同一路径执行并给出可复现脚本，但不等价于人工签字。
- 全量回归未 100% 绿：`tests/paper_discovery/` 2 个既有失败（临时目录 `paper-import-*` 未清理），建议另开 Bug Spec，不在本批次修（避免范围扩大）。
- P2-01 `finalizeMapDeletion()` 残留 `state.maps` 隐式依赖（当前路径不可达）；P2-02 5xx 措辞已 ≥95% 消解；LOW-01 `positionTagMenu()` 清内联约束早于 class 切换（当前结果正确，属顺序脆弱点）。
- 未 push、未合 `main`（按项目 Git 纪律，Agent 只做本地 commit）。

## 8. 下次可直接复用

1. 分派 prompt 里直接给「文件:行 + 目标状态 + 强制约束编号 + 回传片段要求」，子代理产出质量显著提高。
2. E2E 脚本落到 `plans/043/artifacts/*.py` 而不是内联 heredoc：命令超长会失败，落盘后既可执行又成为「可复现步骤」交付物。
3. 视觉指标（宽/高/触摸目标/不重叠）必须用 `bounding_box()` 逐层量，先拿到构成再改 CSS，避免凭估算反复试。
4. 端口被本项目旧服务占用时，`stop.sh` 可能因无 PID 文件失效；用 `launchctl remove <label>` 释放后按 `deploy/README.md` 重新 `launchctl submit`，比换端口更不改变用户访问地址。
5. 静态断言容易假通过（例如 `width <= 200` 让 160 也通过），应加「等于目标值」的双向断言（本次补了 `abs(width-200)<=1`）。
