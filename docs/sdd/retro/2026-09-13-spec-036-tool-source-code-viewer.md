# 复盘 — spec-036 Tool 入口源码只读查看

**日期**：2026-09-13
**角色**：架构师（主会话）
**结论**：三道门禁全部走完并签字放行；达到 DoD，状态转 `已完成`。

## 1. 做了什么

为「Skill 与 Tool」管理页的 Tool 列表新增「代码」按钮 + 只读弹窗，展示每个 Tool 注册入口（`模块.函数`）对应的源码与 `文件:行号`。后端新增 `GET /api/tools/{name}/code`，用 `inspect` 解析 `entry` 字符串到源码（`inspect.getsourcelines` 的 `[1]` 为源码块首行，被装饰函数即装饰器行）；前端复用 Skill 详情弹窗的 `st-detail-*` 类，所有文本走 `textContent` 杜绝注入。

- 后端 `routes_tools.py` / `tool_service.py`（新增 `resolve_tool_source` / `ToolRegistryService.get_tool_entry` / `_import_entry_object`）
- 前端 `index.html` `#st-tool-code-dialog` + `app.js` `openToolCode` / `codeBtn`（防串台范式同 `openSkillDetail`）
- 测试：`test_tool_registry.py` 新增 17 例（38 passed）、`test_frontend_skill_tool_contract.py` 新增断言（18 passed）

## 2. 关键约束与验证

| 约束 | 验证结果 |
|---|---|
| M-01 `lineno` 是源码块首行（装饰器行） | `kb_ask` 实测 953 = `@router.post("/kb/ask")`，`def` 在 954；测试用 `ast` 判装饰器行，不写死 `def` |
| M-03 解析终点必须 `isfunction/ismethod` 且属性链非空 | 11 类终点（模块/包/类/实例/属性链终点）探针全部返回 `None`，无整文件/整类泄漏 |
| M-04 错误文案固定、无绝对路径泄漏 | 固定文案；6/6 响应体无 `/Users`/`.venv` |
| M-06 名称精确匹配 | unknown / `../` 注入 / `KB_ASK` 大小写变体均 404 |
| M-07 禁用 Tool 可见 + 不加缓存 | 可见性不受 `enabled` 影响；两次请求两次 `inspect` 调用（无缓存） |
| M-02 前端四子约束 | `?v=45` 一致、`textContent` 无 `innerHTML`、契约 id 断言、复用既有 CSS 不新增 |

## 3. 本次踩的坑 / 教训

1. **子代理派发网络中断是真实阻塞**。本会话 `frontend-reviewer`、`tester` 两次分派均回报 `502 ENOTFOUND` / `429 too many requests`，无法派发。应对：改为**主会话直评**——坚持「非采信式复核」（逐行回源码 + 跑真实测试 + 真实服务 curl），不引用任何子代理回传摘要，并在评审头部如实标注「代行」及原因。价值：评审证据反而更直接（实测 5/5 200、38 passed），且没有因为网络放弃验收。

2. **行号是漂移的，绝不能写死**。spec-035 在途改动在 `routes_kb.py` 上方加 1 行 import，使 `kb_ask` 装饰器行由 952→953。我在 proposal/plan/需求评审三处写死 `952`，被后端评审标 MEDIUM（M-036-01）。根因是「文档记录的是 HEAD 快照，而验收应按运行时返回值」。已统一改为 953 + 漂移说明，并把验收口径锁定为「以接口返回值为准」。
   - **通用规则**：凡是涉及「源码行号 / 文件位置」的文档断言，都应标注「快照 + 以运行时为准」，避免其它在途 spec 改动造成验收假阴性。

3. **后台进程会被工具调用回收**。`nohup ... &` 启动的 uvicorn 在 Bash 工具返回后被杀；正确做法是 `run_in_background: true`，服务才能常驻供 E2E 探测。本次 E2E 实际命中了会话早期已启动、仍占用 8000 端口的上一实例（PID 44575），新实例因「address already in use」退出——反而证明旧服务可用，直接复用其做核对。

## 4. 遗留

- **未推送**：按用户「先不推」裁决，全部改动留工作区，未 `git commit`/`push`；与 spec-035 在途改动共存，避免交错。
- 全量回归未跑（单端定向改动，按项目规则只跑定向测试）。
- `degraded=true` 与本任务无关，属 spec-033 已归因的 reranker 模型文件缺失（独立环境缺口）。
