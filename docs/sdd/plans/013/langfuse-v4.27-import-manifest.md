# Spec 013 Task 07：Langfuse v4.27.0 导入前置清单

> 关联任务：[`task-07-stats-custom-view.md`](./task-07-stats-custom-view.md)  
> 关联 Spec：[`013-llm-observability-platform.md`](../../specs/013-llm-observability-platform.md)  
> 当前状态：`源码已导入，基线 commit 待在可写 Git 环境建立`

## 目的

在不直接修改外部目录的前提下，为 Langfuse v4.27.0 二次开发建立可审计、可回滚的项目内导入基线。本文记录导入范围和校验协议；源码现已复制到 `vendor/langfuse/`，后续二次开发只允许在该副本进行。

## 来源与版本证据

| 项目 | 证据 |
|---|---|
| 来源目录 | `/Users/wjh/opt/langfuse-src/langfuse` |
| 根包版本 | `package.json` 的 `version: 4.27.0` |
| Web 包版本 | `web/package.json` 的 `version: 4.27.0` |
| Worker 包版本 | `worker/package.json` 的 `version: 4.27.0` |
| Node 要求 | 根、Web、Worker 均为 `node: 24` |
| 包管理器 | 根 `package.json` 为 `pnpm@11.22.0` |
| 工作区 | `web`、`worker`、`packages/**`、`ee` |
| Git 状态 | `git -C /Users/wjh/opt/langfuse-src/langfuse rev-parse --is-inside-work-tree` 返回 `fatal: not a git repository`；来源目录不存在 `.git` 条目 |
| 建议导入目录 | `vendor/langfuse` |

关键文件 SHA-256（导入前基线）：

```text
a76d2ccfddc79489032e66af7c2372e4dce2609212fe47fd04eff8b8fecf71be  package.json
209316802ca13766215d1e17ce8b83347abbe53fa87f0b156ddf93bb0d288c40  pnpm-workspace.yaml
086e8f67ae7581b50af10e37a46a3da1720b2d7e17ad1addd0ede6ff083fd399  web/package.json
f5e2d2ecdf276b44e89b9d34c559414967e018f5cd4b5c4f190ed8053ff80779  worker/package.json
417705a69537754dde324c27bc414e7254519ce5612bb6fadcaeefce9fd8adae  pnpm-lock.yaml
```

上述摘要只证明本次读取到的来源文件内容。由于来源没有 Git commit，不能把任何本地文件状态伪称为官方 commit；项目内副本的 vendor 基线 commit 仍需在 Git 索引可写时建立，并同时保存本清单和导入日志。

## 预计导入文件范围

### 第一批：可构建源码基线

导入到 `vendor/langfuse/`，保留原始相对路径：

- 根构建与工作区描述：`package.json`、`pnpm-workspace.yaml`、`pnpm-lock.yaml`、`turbo.json`、`vitest.workspace.ts`、Prettier/TypeScript/Knip 配置。
- Web 应用：`web/src/**`、`web/public/**`、`web/package.json`、Web 的构建、测试、类型检查和配置文件。
- Worker 应用：`worker/src/**`、`worker/package.json`、Worker 的构建、测试、类型检查和配置文件。
- 共享包：`packages/**` 中源码、schema、数据库访问层、测试和各包 `package.json`；不包含依赖安装目录和构建输出。
- 企业版源码：`ee/**` 中被工作区引用的源码、测试和包清单；不包含本地依赖目录。
- 构建辅助：`scripts/**`、`patches/**`、必要的 `docker-compose*.yml`、`prettier.config.cjs` 和 `LICENSE`。

预计规模证据（来源当前目录，不含依赖和构建缓存）：`web/src` 约 32M、`worker/src` 约 6.6M、`packages` 约 24M、`ee` 约 80K、`scripts` 约 168K、`patches` 约 84K。实际导入文件数和总大小以导入命令输出为准，必须写入 Task 07 执行结果。

### 第二批：二次开发相关文件

完成第一批构建校验后，再按 Task 07 的小批次逐步新增或修改：

1. 查询 schema/router：`web/src/features/ollama-insights/server/**` 与 API 根路由的最小接线。
2. ClickHouse 查询与类型：每次最多两个文件，先固定 v4.27 实际 schema。
3. 页面入口和导航：项目页面、导航路由各批最多两个文件。
4. 阶段甘特、分布和趋势组件：每个组件配对应测试，禁止大批量重写现有 Dashboard。

第二批代码已在导入文件读回和静态校验后分批执行；完整依赖安装和基础前端测试仍受当前网络/依赖环境阻塞。每批代码均先由 `junior-dev` 按 Task 07 的完整 Prompt 执行，主 Agent 读回并校验后才进入下一批。

## 必须排除的内容

以下内容禁止进入 Git 跟踪的 `vendor/langfuse` 基线：

- 依赖和包管理缓存：`node_modules/**`、`.pnpm-store/**`、任何生成的依赖链接。
- 构建和测试产物：`.next/**`、`.next-check/**`、`dist/**`、`build/**`、`out/**`、`coverage/**`、`test-results/**`、`.turbo/**`、`*.tsbuildinfo`、缓存目录。
- 版本控制和 IDE 私有状态：`.git/**`、`.claude/worktrees/**`、`.cursor/**`、`.vscode/**` 的本地配置、`.codex/**` 的本地配置和日志。
- 运行时数据与日志：数据库文件、数据库 journal、ClickHouse/PostgreSQL/Redis/MinIO 数据目录、`logs/**`、`*.log`、临时目录、运行时生成的上传对象。
- 凭据和本地环境：`.env`、所有实际环境文件、证书、私钥、Cookie、Token、密码；只允许按来源项目的安全规则选择性保留脱敏的 `*.example` 文件。
- 与本次构建无关的个人工作区和生成文件：`.DS_Store`、`*.pem`、`.idea/**`、编辑器插件状态、未审查的本地脚本。

当前来源已确认存在并必须排除的实例包括：根 `node_modules`（约 2.5G）、`web/.next`（约 1.5G）、各工作区 `node_modules`、`.turbo/cache` 和根 `.env`。

## 导入前校验命令

导入执行者已在来源目录只读运行以下命令，并把摘要（不含敏感环境变量）写入 `docs/sdd/plans/013/task-07-stats-custom-view.md` 的执行结果及 `.codebuddy/agent-logs/`：

```bash
SOURCE=/Users/wjh/opt/langfuse-src/langfuse
test "$(node -p "require('$SOURCE/package.json').version")" = "4.27.0"
test "$(node -p "require('$SOURCE/web/package.json').version")" = "4.27.0"
test "$(node -p "require('$SOURCE/worker/package.json').version")" = "4.27.0"
test ! -e "$SOURCE/.git"
git -C "$SOURCE" rev-parse --is-inside-work-tree 2>&1; test $? -ne 0
find "$SOURCE" -type f \
  -not -path '*/node_modules/*' \
  -not -path '*/.next/*' \
  -not -path '*/.git/*' \
  -not -path '*/.turbo/*' \
  -not -path '*/cache/*' \
  -not -path '*/logs/*' \
  -not -name '.env' \
  -not -name '*.log' | sort
shasum -a 256 "$SOURCE/package.json" "$SOURCE/pnpm-workspace.yaml" \
  "$SOURCE/web/package.json" "$SOURCE/worker/package.json" "$SOURCE/pnpm-lock.yaml"
```

导入后必须在项目根目录运行：

```bash
find vendor/langfuse -type f -not -path '*/node_modules/*' -not -path '*/.next/*' \
  -not -path '*/.git/*' -not -path '*/.turbo/*' -not -path '*/cache/*' \
  -not -path '*/logs/*' -not -name '.env' -not -name '*.log' | sort > /tmp/spec013-langfuse-vendor-files.txt
rg -n '(^|/)(node_modules|\.next|\.git|\.turbo|cache|logs)(/|$)|(^|/)\.env($|\.)|\.(log|pem)$' vendor/langfuse
test $? -ne 0
test "$(node -p "require('./vendor/langfuse/package.json').version")" = "4.27.0"
test "$(node -p "require('./vendor/langfuse/web/package.json').version")" = "4.27.0"
test "$(node -p "require('./vendor/langfuse/worker/package.json').version")" = "4.27.0"
```

随后在 `vendor/langfuse` 内执行依赖安装、类型检查、构建和最小测试；具体命令必须以导入时实际可用的 Node/pnpm 环境为准，并将退出码逐项记录。不得把 `pnpm install` 生成的依赖目录纳入 commit。

## 导入和回滚协议

1. 记录项目当前分支、HEAD、工作树状态以及 `vendor/` 是否已有用户文件；不得执行 `reset`、`stash`、`clean`、`checkout` 或覆盖已有修改。
2. 确认 `vendor/langfuse` 不存在或为空；若目录已有文件，停止并报告，不覆盖。
3. 仅按“预计导入文件范围”复制，使用排除清单；不得复制整个来源目录后再清理，因为这会短暂暴露凭据和运行时数据。
4. 运行导入后校验，人工抽查 `.env`、凭据、日志、缓存和大体积依赖目录均未进入目标目录。
5. 建立独立的本地基线 commit，commit message 必须关联 `spec-013`，并保存文件数、字节数、manifest 摘要和验证退出码。
6. 后续每个 Langfuse 二次开发批次使用独立 commit；主 Agent 只在验证通过后继续下一批。

回滚点是导入基线 commit 及其之后的独立批次 commit。若发现文件范围、版本、凭据排除或构建校验不符合要求，停止后只撤销本 Spec 的 vendor 导入变更；不删除已采集的 Langfuse 数据，不触碰 ResearchAgent 主工作树中其他 Spec 的修改，不执行破坏性 Git 操作。

## 后续交接与验收

导入任务完成后，执行者必须返回并落盘：

- 结果状态和摘要；
- 来源目录、目标目录、版本和基线 commit；
- 实际导入文件数、总字节数和排除项检查结果；
- 版本、manifest 哈希、无 Git 来源证据和所有测试命令/退出码；
- 产生的 commit 和可回滚点；
- 风险、阻塞和主 Agent 后续动作；
- 开始时间、结束时间、总耗时，以及可用时的模型/token/工具调用统计。

只有“导入基线可构建、排除规则通过、版本一致、commit 可回滚”全部满足，Task 07 才能解除“外部源码无 Git 基线”的前置阻塞。此后才允许开始查询层和页面层二次开发。

## 执行结果

- 本次仅完成前置清单和来源只读核验。
- 未创建 `vendor/langfuse`，未复制源码，未修改 `/Users/wjh/opt/langfuse-src/langfuse`，未修改项目业务代码。
- 来源版本：根/Web/Worker 均为 `4.27.0`。
- 来源 Git：确认不是 Git 工作树，无可用 commit。
- 当前结论：`待导入；不得进入页面编码`。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-03 | Junior Dev（`qwen3.8:27b-mlx`） | 完成 Langfuse v4.27.0 来源、版本、文件范围、排除项、校验和回滚协议的只读前置核验；未复制源码或修改外部目录。 |
