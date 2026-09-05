---
name: regression-guard
description: 本项目高频回归点清单（每条对应一次真实事故）。改动前后必查：前端 DOM 契约/资源版本号/XSS/CSS 作用域，后端 SQLite 迁移/外键/SSRF/USENIX 来源/禁止重复实现。
---

# 高频回归防护清单

> 每条都对应一次真实事故或反复排查，改完必须逐项自查。

## 前端（改 `frontend/**` 必查）

1. **DOM 契约一致**：JS 渲染的 class/id ⇄ CSS 选择器必须交叉核对。
   - 事故：JS 输出 `model-list-item` 而 CSS 写 `.model-item`，整个视图样式失效、退回裸 DOM。
   - 做法：写完 JS 用 Grep 在 CSS 搜同名选择器确认存在；写完 CSS 用 Grep 在 JS/HTML 搜同名 class 确认被渲染。
2. **静态资源版本号**：改 `frontend/app.js` / `styles.css` 后，**必须**同步升 `frontend/index.html` 的 `?v=N`。
   - 不升 → 浏览器沿用旧缓存，出现"服务端已更新但页面没变"的假故障（曾反复排查三轮）。
3. **XSS**：所有用户输入一律 `textContent` / `input.value`，**禁止 `innerHTML` 拼接**。
4. **CSS 作用域隔离**：新增样式带视图前缀（如 `#models-view`），避免污染其他视图；禁止非法声明。

## 后端（改 `backend/**` 必查）

5. **SQLite 迁移**：`schema_meta` 版本校验严格（版本不匹配即 raise）。升版必须「先迁移后升版本号」、单事务、全部 `IF NOT EXISTS` 幂等、失败整体回滚，禁止手工删表补救。
6. **外键**：v2 新增外键统一 `ON DELETE RESTRICT`，禁止 CASCADE（保留来源证据与冻结结果）。
7. **SSRF / 下载安全**：URL 校验与下载一律走既有 `paper_download_security.py` + `paper_download.py`（HTTPS/443/allowlist/公共 IP/逐跳校验），**不得弱化、绕过或另建一套**。
8. **USENIX / DBLP 来源**：只接受 `www.usenix.org` 同源、无 query/fragment/userinfo、路径会议前缀一致；官方关键词缺失必须为空 tuple，**禁止推断或生成**；目录同步禁止 PDF 下载/HEAD/Range 探测（URL 可保存，内容只在导入时验证）；DBLP 绝不覆盖 USENIX 的标题/作者/摘要/关键词。
9. **Qdrant**：collection 必须参数化传入，论文发现目录用独立 collection，不得混入个人 PDF 分块。

## 禁止重复实现（出现第二套即返工）

不得新增第二套：下载器 / SSRF 校验 / 导入流程 / 批任务状态机 / 身份规范化 / embedding 索引检索。
需要某能力时先查既有模块并复用；确需替换，必须给出「无法安全复用」的可复现证据、迁移范围与回归测试。
