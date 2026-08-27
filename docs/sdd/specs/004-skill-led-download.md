# 004 完全由 download-paper Skill 主导下载

**状态：已完成**

## 一句话目标

将论文下载流程改为**下载执行完全由 download-paper skill 主导**：候选的元数据检索（Crossref / OpenAlex）保持原样，skill 只主导下载决策与执行编排，后端受限服务按 skill 指示执行下载；并**放宽 003 的"明确不做"**，允许在 skill 判定需要时采用 Cookie / 浏览器会话 / PoW / 科研通文献互助等方式获取受版权保护的付费论文。

## 已记录决策（来自用户澄清）

- **D1 = A**：Skill 编排 + 后端执行。skill 是主路径与决策者，真正下载由受限后端服务执行（校验大小 / PDF 头 / SHA-256 / 输出目录）。
- **D2 = B**：放宽 003 约束，允许 Cookie / 浏览器 / 科研通文献互助。
- **D3 = 保留 Crossref / OpenAlex 元数据检索**：用户确认 `download-paper` skill 只负责"给定 URL 后下载"，不具备"标题→元数据"的发现能力，因此发现源维持现状；本 spec 仅将"下载执行"改为 skill 主导，不改动发现链路。
- **两者组合的精确含义**：D2 放宽后，D1 选项 A 中"付费论文仍下不了"的保留条件不再成立——放宽的目的正是让付费 / 受限论文可通过 skill 的 Cookie / 文献互助方式下载。即：**skill 主导下载编排，后端在 skill 指示下可执行含凭据的下载；元数据发现仍走 Crossref / OpenAlex**。

## 必须先行澄清的实现前提（阻塞项）

- 用户已选定凭据来源 = **本机 opencli 浏览器工具**（后端调用 `opencli browser <session> eval "document.cookie"` 取 Cookie、解 PMC PoW，并在登录态科研通账号下做文献互助）。
- **环境验证（2026-08-26）**：本机 `opencli` **未安装**（PATH 与常见目录均无）。因此即便 spec 确认，付费 / 受限论文路径在 opencli + 可控浏览器就绪前**无法实际运行**；公开 HTTPS PDF 路径不受影响，可立即使用。
- 实现时 `download_pdf.py` 的凭据获取须改为由后端调用 opencli（而非脚本内硬编码），且 opencli 可用性需作为 skill 状态校验的一部分。

## 数据模型（草案）

| 字段 | 类型 | 约束 |
|---|---|---|
| `skill_name` | string | 固定 `download-paper` |
| `orchestration` | enum | `skill_led`（本 spec 后成为默认） |
| `download_method` | enum | `public_https` / `cookie_session` / `pow_challenge` / `literature_mutual_aid`（科研通） |
| `requires_credentials` | bool | `true` 时进入凭据获取分支 |
| `cookie_input` | string | 仅经用户显式提供，不得由模型生成；不落库、不回显、不写日志 |
| `referer` | string | 可选，随用户提供的凭据一并提交 |
| `credential_source` | enum | `user_pasted` / `opencli_browser`（取决于"凭据来源"决策） |

## 端点 / 接口（草案）

- 将 `POST /api/agent/articles/search` 与 `download` 的默认路径改为 skill 编排；后端仍执行下载。
- 新增凭据 / 登录回传接口（如 `POST /api/agent/articles/credentials`），用于 Human-in-the-loop 提交 Cookie / referer；明文不落库、不回显、不写日志。
- 保留 `GET /api/agent/skills/download-paper` 作为 skill 可用性校验。

## 边界（每条之后会变成一条测试）

- 凭据（Cookie / Token）**仅**经用户显式提供，传输与处理须隔离，不得出现在 SSE / 日志 / 前端回显。
- 即使放宽，下载仍须由后端执行文件头 / 大小 / SHA-256 校验，输出目录受控。
- 不能静默伪造下载成功；无合法来源须返回明确原因与下一步建议。
- 模型（含 worker 子模型）不得自主生成、猜测或留存凭据；凭据只能来自用户显式输入或经授权的本机浏览器工具。

## 明确不做（修订 003）

- 删除 003 中"不向子模型开放 shell / 浏览器 / Cookie"与"不绕过付费墙 / 文献互助"的禁止项；改为：上述能力仅在**用户显式授权、凭据由用户提供（或经授权的本机浏览器工具获取）、且仅用于用户已获合法访问授权的文献**时启用。
- 仍禁止：模型自主生成 / 猜测凭据、将凭据写入日志或前端回显、超出法律允许访问范围的滥用、把凭据用于与论文下载无关的用途。

## 验证方式（草案）

- skill 主导的公开 PDF 计划与下载（继承 003 既有测试）。
- 放宽后的 Cookie / 文献互助路径：仅在用户显式提供凭据的前提下做受控验证，不自动触发。
- 安全回归：凭据不出现在日志 / SSE / API 响应；无凭据时付费路径明确提示而非伪造成功。

---

**三条自检**：①每条规则能不能写成测试？草案已可写，待"凭据来源"决策后补全。②人能在 2 分钟内审完吗？能。③范围划死了吗？主路径已划死；仅"凭据来源"为待决阻塞项。

## 实施与验证（2026-08-26）

- 后端 `backend/app/services/download_paper_skill.py`：新增 `decide_download_method`（按候选判定 `public_https` / `cookie_session` / `pow_challenge` / `literature_mutual_aid`）、`fetch_cookies_via_opencli`（调用本机 `opencli` 取 Cookie，缺失时抛 `OpenCliUnavailable`）、`download_under_skill`（skill 编排、后端执行，非公开路径在 opencli 不可用时返回明确 error 事件而非伪造成功）、`build_skill_plan`（替代原仅支持公开的 `build_download_plan`，对受限候选标记 `requires_credentials`）。`backend/app/services/article_download.py` 的 `download_article` 增加 `extra_headers` 透传。
- 路由 `backend/app/api/routes.py`：`download` 端点默认 `use_skill`（skill 可用时）改由 `download_under_skill` 执行；`plan-download` 端点改用 `build_skill_plan`，对受限候选也返回 skill-led 计划；保留 Crossref / OpenAlex 发现链路（D3）。
- 凭据约束：Cookie / referer 仅由 `opencli` 本机浏览器工具提供，模型绝不生成凭据；凭据不回显、不落库、不进日志。
- 新增测试 `tests/test_skill_led_download.py`（9 条）+ 改写 `tests/test_api.py` 中 2 条沿用旧 `build_download_plan` 的用例；全量 39 条测试通过。
- 运行时验证：本地服务 8137 启动正常；`/api/agent/skills/download-paper` 返回 `available: true`（skill 文件与 `deepseek-coder:33b` 均就绪）。付费 / 受限路径因本机 `opencli` 未安装仍不可实际运行（见"阻塞项"），公开 HTTPS PDF 路径不受影响。
