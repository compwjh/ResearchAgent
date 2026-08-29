# 技术评审（实现后复审）：spec-010 后端测试覆盖率提升至 80%

- 评审角色：开发主管（tech-lead）
- 评审类型：**实现后技术复审（Tech Review / Re-audit）**——非「实现前可行性评审」
- 评审对象：已合入的 `tests/test_api_routes_coverage.py`（41 用例）+ `.gitignore` 改动
- 评审时间：2026-08-29
- 评审方式：**基于真实代码 + 实测**（Read 测试全文、pytest --cov 实跑、grep 断言/mock 统计、git status 核对业务零改动）
- 前置文档：本文件上一版为「实现前可行性评审」，本次已按真实落地代码重写为复审结论。

## 结论：**通过（附意见）**

核心验收点全部经实测达标：覆盖率 69%→**87%**（≥80%，余量 7pt）、**85 passed**、**零业务代码改动**、**离线可重复**（本机无 Ollama 在线仍全绿）。发现的唯一隐患（`.gitignore` 残留合并冲突标记）属工程卫生问题，不阻断本 spec 达标，列为**非阻塞强制约束**要求后续清理。

## 验收点逐条实测核对（对照 spec 验收 V1–V4）

| 验收点 | 要求 | 实测结论 | 判定 |
| :-- | :-- | :-- | :-- |
| V1 | `pytest tests` 全通过、无新增失败 | `85 passed, 1 warning in 36.40s`（本机 macOS/Python3.9，无 Ollama 在线） | ✅ |
| V2 | `--cov=backend` TOTAL ≥ 80% | **TOTAL 818 / Miss 104 / Cover 87%**；主攻 routes.py 94%、chat.py 100%、article_agent 95% | ✅ 达标（87%，落在目标区间上沿之上） |
| V3 | 新用例含真实断言 + 离线可重复 | 41 用例 / 95 assert，无 `assert True`/空用例；全部外部依赖 mock，本机无 Ollama 仍全绿 | ✅ |
| V4 | 业务代码零改动 | `git status` 干净、非活跃合并；`backend/app/**` 无工作树改动；本 spec 仅新增 `tests/` + 改 `.gitignore` | ✅ |

> 说明：V5（门禁复检）为「解除 spec-008/009 合并阻断」的流程动作，属 spec 状态/流程变更，不在本技术复审的代码事实范围内，由验收评审与门禁表更新承接（见 `010-acceptance-review.md` / `009-pr-review.md`）。

## 评审意见（针对测试代码维度）

| 维度 | 判定 | 说明（基于代码事实） |
| :-- | :-- | :-- |
| 覆盖率提升真实性 | ✅ | 非凑数。41 个用例逐一到端点/分支：health、GET/PUT settings、get_task、probe、chat 正常+异常、search 各 return、download 503/502/404/PermissionError、login_completed、run_agent 4 分支、chat.py `ask_model` content 累加、backend.main 入口。断言命中**具体状态码 + 响应字段**（body["status"]、detail、SSE event.message），符合 spec §3「禁止无断言」。 |
| 断言质量 | ✅ | 95 处 assert 全有业务含义。异常路径断言错误语义（`"搜索关键词" in detail`、`status=="failed"`、`"50%" in error`、`download_outcome=="rate_limited"`）。无 `assert True`/裸调用。 |
| 外部依赖 mock | ✅ | 全部 patch 目标为 `backend.app.api.routes.<symbol>` 命名空间（`get_available_models`/`search_articles`/`probe_pdf_url`/`download_article`/`skill_status`/`build_chat_graph`/`create_chat_model`），未打到 httpx/subprocess 内部实现。Ollama 不可达用 `side_effect=httpx.HTTPError` 模拟，天然离线。 |
| 离线可重复 | ✅（已实测） | 在无 Ollama 服务的本机环境跑通 85 passed，验证不依赖在线模型/真实网络/真实子进程。 |
| 兼容性 | ✅ | 纯新增 `tests/**`，不改请求链路；`TestClient(app)` 只读调用现有路由。 |
| 容错/边界 | ✅ | 覆盖 400 校验（空/超长 question、非下载意图）、404（task/candidate 缺失）、502（上游/网络/限流）、waiting_login/login_required 边界，边界路径处理到位。 |
| 安全 | ✅ | 纯测试侧，无 innerHTML/密钥/新输入面；mock 隔离后不产生真实请求。 |
| 高频回归点：前端 class⇄CSS | **N/A** | 本次改动不涉及前端（spec「明确不做」），无 JS/CSS 变更。 |
| 高频回归点：静态资源 `?v=N` | **N/A** | 本次无 `frontend/` 变更，`index.html` 未动。 |

## ⚠️ 工程卫生隐患（非阻塞，需后续清理）

- **`.gitignore` 含 6 个未解决的 git 合并冲突标记**（`<<<<<<< HEAD` / `=======` / `>>>>>>> feature/spec-009-agent-roles`，见 `.gitignore:9-15, 21-24`）。
  - 事实核对：`git status` 干净且非活跃合并，说明这些是**已提交进仓库的死标记**，不是进行中的合并。
  - 影响：`.coverage`/`.coverage.*`/`htmlcov/`/`.pytest_cache/` 的忽略规则被夹在冲突块内，语义上仍有效（这些行在 `=======` 与 `>>>>>>>` 之间，属「本分支新增」一侧，保留即生效），但**残留冲突标记是配置卫生缺陷**，后续任意一次真正合并/编辑该文件都可能引发混淆。
  - 定性：属工程卫生问题，**不阻断 spec-010 达标**（忽略规则实际生效，测试产物未入库——`git status` 无 `.coverage`/`htmlcov` 待提交项即为佐证）。列为**非阻塞强制约束 T-NEW**。

## 强制约束（合并后必须保持 / 需落实）

- **T1（已有）**：所有 patch 目标保持 `backend.app.api.routes.<symbol>` 命名空间，禁止下沉 patch 到 httpx/subprocess 内部实现。
- **T2（已有）**：涉及 `download_under_skill`/`download_article`/`probe_pdf_url`/`build_chat_graph` 的用例必须「先 mock 再调用」，运行期不得出现真实子进程/真实 HTTP/真实 Ollama 调用。
- **T3（已有）**：`login_completed` 用例必须一并 mock 下游 `download_article_endpoint`/`skill_status`/`get_available_models`，不得触发真实下载（现有 `test_login_completed_resumes_download` 已做到）。
- **T4（已有）**：chat 用例 mock model 须返回**多个非空 content chunk** 并断言 `answer` 拼接正确（现有 `test_build_chat_graph_streams_content_chunks` 断言 `answer=="你好"`，含空 chunk 分支，达标）。
- **T5（新，非阻塞）**：**清理 `.gitignore` 中残留的 6 个合并冲突标记**（`<<<<<<<`/`=======`/`>>>>>>>`），保留 `.coverage`/`.coverage.*`/`htmlcov/`/`.pytest_cache/` 忽略规则，消除配置卫生缺陷。此为本复审唯一新增待办。
- **T6（新，长期）**：新增覆盖率用例须断言**具体状态码 + 响应字段/错误语义**，禁止 `assert True` 或「调用即结束」的空用例（防止未来为凑覆盖率回退）。

## 判定统计

- 验收点 V1–V4：**4/4 通过（全部实测）**；V5 为流程动作，另行承接。
- 评审维度命中：**核心维度全部 ✅ / N/A（2 项高频回归点因不涉及前端标注 N/A）**。
- 强制约束条数：**6**（T1–T4 既有 + T5、T6 新增；其中 **T5 为本复审新发现待办**）。
- 阻塞项：**0（无阻塞）**；非阻塞待办 1 项（T5 `.gitignore` 冲突标记清理）。

## 风险定级：**低**

| 风险 | 等级 | 缓解/现状 |
| :-- | :-- | :-- |
| 为凑覆盖率写无断言空测试 | 低（已控） | 41 用例 95 assert 全有业务语义；T6 长期锁定 |
| mock 不彻底导致测试不可重复 | 低（已控） | 无 Ollama 环境实跑 85 passed；patch 目标统一在 routes 命名空间 |
| `.gitignore` 冲突标记残留 | 低（卫生） | 已列 T5 非阻塞待办；忽略规则实际生效，未污染仓库 |
| 覆盖率随环境/cov 版本波动 | 很低 | 87% 对 80% 阈值留 7pt 余量 |

## 阻塞项

**无。可维持 spec-010「已完成」状态。** 唯一遗留为 T5 工程卫生待办（清理 `.gitignore` 冲突标记），建议纳入后续技术债清单，不阻断当前门禁解除。

---
*评审文档路径：`docs/sdd/reviews/010-tech-review.md`*
*进展日志：`.codebuddy/agent-logs/tech-lead-010-20260829-124400.md`*
