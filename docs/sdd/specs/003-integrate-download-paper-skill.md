# 003 集成 download-paper Skill

**状态：已完成**

**实际实现**：已完成 skill 元信息读取与可用性检查（SKILL.md 与 `scripts/download_pdf.py` 存在性、受控子模型 `deepseek-coder:33b` 可用性）、`GET /api/agent/skills/download-paper` 状态接口（返回版本/路径状态与 worker model 可用性）、`POST /api/agent/articles/plan-download` 受控下载计划（仅允许 `pdf_url_status == public_pdf` 且 HTTPS 的候选；子模型输出仅提取 `user_message`，最长 300 字，且不得覆盖后端已探测的 URL、输出目录或命令）、以及 `POST /api/agent/articles/download` 新增可选 `use_skill: true`（校验 skill 可用后由受限后端 `download_article` 执行下载并记录 `skill_name`）。未接入 skill 脚本中的 Cookie/浏览器/登录下载能力，严格遵循“明确不做”中的付费墙、登录、验证码、反爬与第三方文献互助限制。

**验证结果**：28 个单元/API 测试全部通过（新增 `tests/test_download_paper_skill.py` 覆盖受控子模型、非公开/非 HTTPS 拒绝、结构化解析与不可信输出拦截；`tests/test_api.py` 覆盖 `use_skill` 记录 `skill_name`）；后端全量编译通过；服务在端口 8137 启动，健康接口、`/api/agent/skills/download-paper`（`available: true`）与一次真实 `deepseek-coder:33b` 生成的公开 PDF 下载计划均验证通过。

## 一句话目标

将本机已安装的 `download-paper` skill 接入论文 Agent：主模型负责识别意图、检索候选与选择执行步骤；`deepseek-coder:33b` 仅负责生成面向公开 PDF 下载任务的结构化执行建议和用户说明，实际下载仍由受限的后端服务执行。

## 设计与职责

- **主模型 / Agent 编排层**：复用现有 LangGraph 意图图，判断请求是否为论文下载；选择 `download-paper` 能力、搜索候选、探测链接，并决定是否进入下载或人工登录状态。
- **子模型 `deepseek-coder:33b`**：仅处理受控子任务（将候选与探测结果组织为结构化下载计划/用户说明）；不得获得任意 shell、浏览器、Cookie、凭据或文件写入权限。
- **Skill 适配层**：读取 `download-paper` 的元信息，并调用其中 `scripts/download_pdf.py` 的等价、安全下载能力；只允许已探测为 `public_pdf` 的 HTTPS URL。
- **下载服务**：继续负责大小限制、PDF 文件头、SHA-256、目标目录和错误处理，不能由模型直接下载文件。

## 数据模型

| 字段 | 类型 | 约束（必填？范围？默认？） |
|---|---|---|
| `skill_name` | string | 必填；固定 `download-paper` |
| `skill_path` | string | 必填；必须解析到受信任的本机 skill 目录，且包含 `SKILL.md` 和 `scripts/download_pdf.py` |
| `planner_model` | string | 必填；现有请求的主模型，仅用于编排/问答 |
| `worker_model` | string | 必填；固定默认 `deepseek-coder:33b`，必须存在于 Ollama 模型列表 |
| `download_plan` | object | 可选；只含候选 ID、公开 PDF URL、输出文件名、来源状态和用户说明；不得含 Cookie、Token、密码或任意命令 |
| `execution_mode` | enum | 必填；`public_download` / `login_required` / `not_available` |
| `skill_error` | string | 可选；不得泄露本机绝对路径以外的敏感配置或凭据 |

## 端点 / 接口

| 动作 | 输入 | 成功返回 | 失败情况（状态码） |
|---|---|---|---|
| `GET /api/agent/skills/download-paper` | 无 | skill 可用性、版本/路径状态、worker model 可用性 | `503` skill 文件缺失或 Ollama 不可达 |
| `POST /api/agent/articles/plan-download` | `{ task_id, candidate_id, model? }` | 受控的 `download_plan`、`execution_mode` 与用户说明 | `400` 输入无效；`404` 任务/候选不存在；`409` 链接未探测为公开 PDF；`503` 子模型不可用 |
| `POST /api/agent/articles/download` | 现有接口，增加可选 `use_skill: true` | 复用现有下载结果，并记录 `skill_name` | 保持现有下载错误语义 |

## 边界（每条之后会变成一条测试）

- 本机缺少 `SKILL.md` 或 `scripts/download_pdf.py` 时，状态接口明确返回不可用，不能静默降级到任意脚本。
- `deepseek-coder:33b` 不存在或 Ollama 不可用时，不执行下载；返回清晰的 `503` 错误。
- 仅当 `pdf_url_status == public_pdf` 且 URL 为 HTTPS 时才允许生成 `public_download` 计划或写文件。
- `401`、`403`、登录 HTML、付费墙、验证码、HTML 页面、非 PDF、超大文件和未知来源均不得由 skill 或子模型绕过；沿用 `login_required` 或 `not_available`。
- 子模型返回的任何 URL、文件路径、命令或指令都不能覆盖后端已探测的 URL、大小限制和输出目录。
- 子模型输出不包含 API Key、Cookie、密码、会话数据或完整的环境变量。
- 使用 `use_skill: false` 时，现有文章搜索、探测和下载行为保持不变。

## 验证方式

- 单元测试：skill 目录完整/缺失、worker model 存在/缺失、结构化计划解析和不可信子模型输出拦截。
- API 测试：公开 PDF 成功生成计划并下载；`401/403`、非 PDF、无 URL、HTTPS 以外 URL 和大文件均被拒绝或进入既有人工处理状态。
- 回归测试：现有 `tests/test_article_agent.py`、`tests/test_article_download_probe.py`、`tests/test_download_outcomes.py` 继续通过。
- 运行时验证：启动本地服务，检查健康接口、skill 状态接口及一次 mock 的公开 PDF 下载计划。

## 明确不做

- 不绕过付费墙、登录限制、验证码、反爬机制、访问控制或版权保护。
- 不使用第三方“文献互助”服务获取非开放获取论文。
- 不向子模型开放 shell、浏览器自动化、用户登录状态、Cookie 或任意文件系统写权限。
- 不改变已有前端交互，除非后续 spec 明确纳入。
- 不把 `deepseek-coder:33b` 配置为 Codex 主模型；它只作为项目运行时的受控子模型。

---

**三条自检**：①每条规则能不能写成测试？能。②人能在 2 分钟内审完吗？能。③范围划死了吗？能。
