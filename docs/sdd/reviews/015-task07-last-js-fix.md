# Spec015 Task07 最后一轮 JavaScript 修复记录

- 执行角色：junior-dev
- 修复时间：2026-09-05 00:54（Asia/Shanghai）
- 修复范围：仅 `frontend/app.js`；未修改后端、HTML、CSS 或测试文件
- 进展日志：`.codebuddy/agent-logs/junior-dev-spec015-task07-last-js-fix-20260905-0054.md`
- 约束：未执行 commit、push、reset、stash、clean

## 修复内容

1. 批次轮询新增 `batchPollSerial` 请求序列。每次轮询捕获自身序列，并在 fetch 返回、写入 `paperState.batches`、调用 `renderPaperBatch()` 或更新错误提示前再次检查功能开关和序列；关闭开关会递增序列，使所有在途响应失效。
2. 同分候选排序固定为最终分数层级之后的 `initial_rank asc → year desc → normalized_title asc → candidate_id asc`，移除局部 `rank` 和 DOI/DBLP 身份排序键；`responseIndex/candidateIndex` 仅作为最后稳定键。DOI、DBLP 和标题元数据去重逻辑保留。
3. 在 `app.js` 中保留可机械检查的 tie-break 顺序常量，并通过最小 Node 断言覆盖初始排名优先、年份/标题/候选 ID 顺序、轮询守卫和身份去重键。

## 验证结果

| 检查 | 结果 |
|---|---|
| `node --check frontend/app.js` | 通过，退出码 0 |
| 前端契约与论文相关回归 | 通过，`102 passed, 9 subtests passed` |
| Node 最小静态/行为断言 | 通过：同分 `initial_rank` 优先；年份、规范标题、candidate ID 顺序正确；轮询序列守卫存在；DOI/DBLP/标题去重键保留 |
| `git diff --check -- frontend/app.js` | 通过，退出码 0 |

## 交接结论

QA 报告指出的在途批次响应竞态和规范 tie-break 顺序缺口已在前端 JavaScript 范围内闭合。A3 自定义会议、真实 GUI/窄屏和 ACM/IEEE 合法登录仍属于既有外部环境阻塞，不在本轮改动范围内。
