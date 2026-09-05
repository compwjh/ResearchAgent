# 任务 02 — 验证稳定基线、数据源与浏览器桥接（Go/No-Go）

> 关联：[spec-015](../../specs/015-security-paper-discovery.md) ｜ 索引：[README](./README.md)  
> 依赖：任务 01；当前状态：`条件放行（内置会议召回）`

> 用户明确要求本轮跳过 Spec013/014 基线核对与 Reranker 模型判断；这两项记录为“跳过（用户授权）”，不作为本轮后续任务门禁。

## 一句话目标

在写业务代码前证明共同基线可运行、DBLP/OpenAlex 能覆盖目标检索、spec-014 可提供有效重排、Playwright 能完成 ACM/IEEE 合法登录续传；任一硬前提失败则停止后续实施。

## 背景与前置条件

- 当前主工作树可能包含 spec-013/014 未提交修改，严禁 reset、clean、stash 或覆盖。
- 输入只认 spec-013/014 的最终 spec、验收文档和明确 commit。
- 本任务允许安装经批准的 Playwright 依赖和浏览器运行时，但不得修改业务逻辑。
- ACM、IEEE 登录由用户在浏览器中亲自完成；不读取、记录或传递密码。

## 数据、配置与接口

- 验证 DBLP Search API 的会议流、年份、分页与返回字段。
- 验证 DBLP Venue Search 的名称查询、候选稳定标识和会议详情链接。
- 验证 OpenAlex 可按 DOI/标题补全摘要、OA 与 PDF 地址。
- Spec013/014 基线核对与 Reranker 质量判断本轮跳过（用户授权，后续任务再按既有契约接入）。
- 验证 Playwright 持久化 profile 可在项目数据目录之外的 Git 忽略目录保存。

### 技术复审修订门禁

- Spec013/014 基线核对按用户授权跳过；本任务只记录当前分支状态与 DBLP/OpenAlex/Playwright 证据，不把跳过项伪装为 Go。
- Playwright 先分层验证安装、可见窗口、profile 持久化、单 profile 文件锁和 ACM/IEEE origin allowlist；真实登录续传属于最终验收硬门禁。没有合法账户时必须记录阻塞。
- 记录浏览器/Playwright 版本、profile 权限、trace/HAR/video/download 禁用状态和异常恢复证据；凭证、Cookie、Authorization 和带令牌 URL 不得进入日志或产物。

## 实施步骤与决策依据

### 阶段 A：冻结安全基线

1. 记录 `git status`、当前分支和 commit，不修改工作树。
2. 跳过 spec-013、spec-014 状态与验收签字核对（用户授权）。
3. 跳过 Reranker 20 候选质量判断与探针（用户授权）。
4. 仅记录应用可运行性、DBLP/OpenAlex 数据源和 Playwright 环境证据，不以本任务替代全量回归门禁。

### 阶段 B：检索源 Go/No-Go

5. 对 CCS、USENIX Security、IEEE S&P、NDSS 各选至少两个年份执行 DBLP 检索。
6. 记录主会、Workshop、Poster 等实际样本，证明主会别名过滤可实现。
7. 以 DOI 和标题调用 OpenAlex，记录摘要、OA 状态和 PDF 字段的覆盖率与缺失行为。
8. 验证 DBLP Venue Search 能搜索并选中一个非内置会议，且结果足以生成受控配置。
9. 记录限流、超时、User-Agent 与失败响应，确定客户端退避和缓存策略。

### 阶段 C：排序与浏览器 Go/No-Go

10. 跳过 spec-014 rerank 质量判断（用户授权）。
11. 建立最小 Playwright 原型，验证持久化 profile、显式打开/关闭和异常退出恢复。
12. 在用户具有合法权限的前提下分别验证 ACM Digital Library、IEEE Xplore：打开登录页、用户登录、重新访问论文页、发现可下载 PDF。
13. 检查日志、终端和文件，确认没有密码、Cookie、Authorization 或完整带令牌 URL 泄漏。
14. 回填应用可运行性、浏览器版本、支持站点规则与数据源 Go/No-Go 结论；用户授权跳过项单独标记 deferred。

## 子代理分派

- `tester`：执行 DBLP/OpenAlex 与浏览器验收矩阵，输出原始结果摘要；Spec013/014 与 Reranker 项标记 deferred。
- `tech-lead`：复核 Go/No-Go 证据和安全风险。
- 任务不修改代码时由架构师负责命令编排与最终判断；如需改依赖/脚本，必须先拆成最多 2 文件的 `junior-dev` 分派。
- 子代理只读取本任务、spec-015、spec-013/014 最终验收和相关配置，不扫描整个项目。

## 实时监控

```bash
git status --short --branch
ollama ps
lsof -nP -iTCP -sTCP:LISTEN
tail -f deploy/run.log
```

## 验收标准

- 有明确且可复现的共同基线 commit，全量回归和运行时健康通过。
- 四个默认会议均能检索，并有可执行的主会过滤证据。
- OpenAlex 缺失或超时不会破坏 DBLP 基础结果。
- spec-014 20 候选批量重排通过，失败降级可观察。
- Playwright 在 ACM、IEEE 两站完成真实合法登录续传；凭证未泄露。
- 结论明确为 Go 或 No-Go；No-Go 包含阻塞原因和复现命令。

## 明确不做

- 不实现正式 API、UI、下载器或知识库改动。
- 不以 HTTP 200 代替数据质量、排序质量或真实登录验证。
- 不绕过登录、验证码或权限，不安装来源不明的浏览器扩展。

## 风险与回滚

| 风险 | 处置 |
|---|---|
| spec-013/014 或 Reranker 判断 | 本轮按用户授权跳过，记录 deferred，不阻塞数据源与浏览器子任务 |
| DBLP 会议流混杂 | 保存样本并设计别名/类型过滤；无法可靠过滤则回需求评审 |
| 登录无合法测试权限 | 标记验收阻塞，不伪造成功 |
| Playwright 环境失败 | 缩小为浏览器安装/权限诊断；连续三次失败按规则阻塞 |

## 产出物与执行结果

- 产出：本文中的数据源矩阵、过滤/降级证据和分阶段 Go/No-Go 结论。
- 执行结果：tester 完成 DBLP/OpenAlex 实测；tech-lead 条件放行内置会议 publication search 与 OpenAlex 补全。DBLP Venue Search 因 429/503 无成功样本保持 blocked；Spec013/014 与 Reranker 按用户授权 deferred。详见 [`015-task02-baseline-review.md`](../../reviews/015-task02-baseline-review.md) 与 [`015-task02-tech-review.md`](../../reviews/015-task02-tech-review.md)。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-03 | 架构师(自身) | 创建任务计划，状态为待执行 |
| 2026-09-04 | tester | 完成 DBLP publication/OpenAlex 实测，记录 429/500/503/timeout、USENIX `SOUPS` 混流和 OpenAlex 标题宽召回风险 |
| 2026-09-04 | tech-lead | 条件放行内置会议召回与 OpenAlex 补全；Venue Search 保持阻塞，要求显式 User-Agent、退避缓存、主会别名过滤和稳定 warning/error code |
