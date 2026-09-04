# 任务 02 — 验证稳定基线、数据源与浏览器桥接（Go/No-Go）

> 关联：[spec-015](../../specs/015-security-paper-discovery.md) ｜ 索引：[README](./README.md)  
> 依赖：任务 01，且 spec-013、spec-014 完成；当前状态：`待执行`

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
- 验证 spec-014 内部 rerank 契约及不可用时的降级语义。
- 验证 Playwright 持久化 profile 可在项目数据目录之外的 Git 忽略目录保存。

## 实施步骤与决策依据

### 阶段 A：冻结安全基线

1. 记录 `git status`、当前分支和 commit，不修改工作树。
2. 确认 spec-013、spec-014 状态均为 `已完成`，验收签字和运行时验证真实存在。
3. 在现有代码上运行首页、健康检查、知识库检索、Reranker 探针和全量测试，记录动态回归基线。
4. 仅在全部通过后，从明确 commit 创建 `feature/spec-015-security-paper-discovery`；若仍有来源不明的未提交改动则停止并报告。

### 阶段 B：检索源 Go/No-Go

5. 对 CCS、USENIX Security、IEEE S&P、NDSS 各选至少两个年份执行 DBLP 检索。
6. 记录主会、Workshop、Poster 等实际样本，证明主会别名过滤可实现。
7. 以 DOI 和标题调用 OpenAlex，记录摘要、OA 状态和 PDF 字段的覆盖率与缺失行为。
8. 验证 DBLP Venue Search 能搜索并选中一个非内置会议，且结果足以生成受控配置。
9. 记录限流、超时、User-Agent 与失败响应，确定客户端退避和缓存策略。

### 阶段 C：排序与浏览器 Go/No-Go

10. 使用不少于 3 条方向查询和 20 条候选调用 spec-014，确认分数有限、映射稳定、相关文档在前。
11. 建立最小 Playwright 原型，验证持久化 profile、显式打开/关闭和异常退出恢复。
12. 在用户具有合法权限的前提下分别验证 ACM Digital Library、IEEE Xplore：打开登录页、用户登录、重新访问论文页、发现可下载 PDF。
13. 检查日志、终端和文件，确认没有密码、Cookie、Authorization 或完整带令牌 URL 泄漏。
14. 回填基线 commit、浏览器版本、支持站点规则与 Go/No-Go 结论；No-Go 时停止任务 03–09。

## 子代理分派

- `tester`：执行 DBLP/OpenAlex、Reranker 和浏览器验收矩阵，输出原始结果摘要。
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
| spec-013/014 尚未收口 | No-Go，保持待执行，不复制半成品 |
| DBLP 会议流混杂 | 保存样本并设计别名/类型过滤；无法可靠过滤则回需求评审 |
| 登录无合法测试权限 | 标记验收阻塞，不伪造成功 |
| Playwright 环境失败 | 缩小为浏览器安装/权限诊断；连续三次失败按规则阻塞 |

## 产出物与执行结果

- 产出：本文中的基线、数据源矩阵、排序探针、浏览器证据和 Go/No-Go 结论。
- 执行结果：待执行后填写。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-03 | 架构师(自身) | 创建任务计划，状态为待执行 |
