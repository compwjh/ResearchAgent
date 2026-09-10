# Spec015 Task07 论文检索 Tab 最终技术复核

- 评审者：当前协作 Agent
- 角色：开发主管（Tech Lead）
- 评审模型：本回合 `gpt-5.6-luna/high`
- 评审时间：2026-09-05 00:34–00:40（Asia/Shanghai）
- 复核范围：Spec015、Task07 计划、最新 Task07 修复记录与日志、`frontend/index.html`、`frontend/app.js`、`backend/app/api/routes.py`、`backend/app/api/schemas.py` 及论文检索/导入测试
- 评审约束：只读复核；未修改业务代码、测试或 Git 状态，未执行 commit、push、reset、stash、clean
- 进展日志：`.codebuddy/agent-logs/tech-lead-spec015-task07-final-20260905-003411.md`

## 结论

**打回，暂不签字放行。**

最新 Gate 修复已闭合 `aria-current` 同步、真实受控会议搜索 GET、按 `batch_id` 的独立批次渲染、服务端 opaque ID 导入边界以及论文动态文本的 XSS 安全渲染；自动化检查全部通过。但功能开关尚未形成真实的首屏闭环，且跨响应去重没有使用 DOI/DBLP key，排序也未实现 Spec015 要求的完整稳定 tie-break。因此当前不能声称 Task07 技术复核通过。

## 必须退回修复的问题

### T7-F1（P1）：关闭开关时无法保证首屏隐藏且不发起论文请求

`frontend/app.js:351-358` 的 `readPaperFeatureFlag()` 在没有页面注入值时默认返回 `true`。虽然 `frontend/app.js:96-111` 尝试从 `/api/health` 读取 `paper_discovery_enabled`，但 `backend/app/api/routes.py:253-259` 的健康响应实际只返回 `status`、`model`、`models`，没有该字段，也没有在 `frontend/index.html` 注入服务端环境值。

实测：在 `PAPER_DISCOVERY_ENABLED=false` 环境下请求 `/api/health` 返回 200，JSON keys 为 `['model', 'models', 'status']`，`paper_discovery_enabled` 缺失。浏览器因此首屏仍按 `true` 显示“论文检索”入口；用户点击入口后才请求会议配置并收到 503，不能满足“开关关闭时入口和请求均不出现”。

`setPaperEnabled(false)`（`frontend/app.js:411-427`）确实会 abort 当前搜索并清除 `batchPollTimer`，但 `schedulePaperBatchPoll()` 的已发出请求在 `frontend/app.js:703-708` 完成后没有再次检查 `paperState.enabled`，仍可能更新状态并渲染。修复必须同时补齐服务端/页面首屏能力状态，以及关闭后的 in-flight 响应失效保护。

### T7-F2（P1）：跨响应去重缺少 DOI/DBLP key

`frontend/app.js:497-509` 的 `paperCandidateIdentityKeys()` 只生成 `candidate_id` 和规范化 `title/year/conference` 键，完全没有使用候选对象已有的 `doi` 或 `dblp_key` 字段。若同一论文在不同会议响应中的服务端候选 ID 不同、但 DOI 或 DBLP key 相同，当前实现仍会展示重复记录，违反 Spec015 的 DOI、DBLP key、规范标题去重约束。

此外，当前元数据键包含会议身份；即便标题和年份相同，跨会议响应也不会由该键合并。需要明确采用与服务端一致的规范身份键，并补充跨响应 DOI、DBLP key、规范标题重复样本的前端回归。

### T7-F3（P2）：排序虽确定，但不满足 Spec015 完整稳定排序契约

`frontend/app.js:512-527` 的比较器按有效分数、`rank`、`responseIndex`、`candidateIndex` 排序。它能在固定会议选择顺序下形成确定结果，但没有使用 Spec015 要求的 `(initial_rank asc, year desc, normalized_title asc, candidate_id asc)` 完整 tie-break；`rank` 还是每个单会议响应的局部 rank，不是跨会议全局 rank。应补充同分/同 rank 的年份、规范标题和 candidate ID 回归，或由服务端返回单一全局 snapshot。

## 已确认通过或基本通过的项目

| 项目 | 判定 | 证据 |
|---|---|---|
| 导航无障碍 | 通过（静态） | `showView()`（`frontend/app.js:906-923`）遍历全部导航项，将当前项设为 `aria-current="page"`，其余设为 `false`，并同步论文入口隐藏状态。 |
| 真实会议搜索 GET | 通过（受限契约） | 前端 `frontend/app.js:850-875` 实际调用 `GET /api/papers/conferences/search?q=`；后端 `backend/app/api/routes.py:264-294` 只搜索服务端已有会议并返回安全 payload，无客户端 URL 信任。 |
| 多批次独立渲染 | 通过（静态） | `frontend/app.js:718-774` 按 `data-batch-id` 建立并更新独立容器，不清空其他批次；失败重试和 waiting-login 操作挂在对应批次内。 |
| opaque IDs | 通过 | 搜索候选映射并以 `search_id/candidate_id` 提交导入（`frontend/app.js:646-675`）；登录/续传仅以编码后的 `item_id` 调用固定路径（`frontend/app.js:800-816`），不接受客户端 PDF/登录 URL。 |
| XSS / 动态文本边界 | 通过（论文区域） | `renderPaperResults()`、`renderPaperBatch()` 使用 DOM 节点和 `textContent`（`frontend/app.js:530-559`, `713-774`），论文专属渲染区没有 `innerHTML`。既有聊天 Markdown 的 `innerHTML` 不属于 Task07 论文字段。 |

## A3 自定义会议的前置环境阻塞

**A3 不通过，也不伪造通过。** `docs/sdd/reviews/015-task02-baseline-review.md` 已记录 DBLP Venue Search 因 `429/503` 无成功样本，Task02 技术结论保持 blocked。当前实现只允许搜索服务端已经配置的会议；没有新增会议 POST，`DELETE` 对自定义会议也明确返回 `CUSTOM_CONFERENCE_UNSUPPORTED`。这与当前 Task02 前置条件阻塞一致，但不等于 A3 已验收。待 DBLP Venue Search 获得可复现成功样本并重新确认会议配置契约后，才能实现/验收“搜索并新增自定义会议”。

## 验证结果

| 检查 | 结果 |
|---|---|
| `node --check frontend/app.js` | 通过，退出码 0 |
| `.venv/bin/python -m pytest -q tests/test_frontend_paper_contract.py` | 通过，3 passed |
| 论文 API/导入/搜索/批次/下载/身份定向回归 | 通过，97 passed，9 subtests passed |
| `.venv/bin/python -m compileall -q backend/app` | 通过，退出码 0 |
| `git diff --check` | 通过，退出码 0 |
| `PAPER_DISCOVERY_ENABLED=false` 下 `GET /api/health` | 200，但缺少 `paper_discovery_enabled`，为 T7-F1 复现证据 |

本轮未启动桌面/窄屏浏览器，也未执行 ACM Digital Library / IEEE Xplore 合法账户登录续传；这些验收不得由本报告静态检查替代。

## 签字

- 开发主管（Tech Lead）：**当前协作 Agent，签字：打回**
- 签字时间：2026-09-05 00:40 +0800
