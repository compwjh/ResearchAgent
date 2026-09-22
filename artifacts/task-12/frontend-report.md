# Spec032 Task12 前端交接报告

## 结果状态/摘要

已完成前端最小闭环：论文检索来源进度卡按服务端返回动态生成，不再固定枚举 USENIX/DBLP；卡片展示缓存/获取/完成/论文计数、cached/fetching/completed/failed/partial 状态、已验证年份与来源错误。Research Task acquisition status 的 `issues` 投影已进入待处理论文入口，按服务端 actions 和 waiting_login/failed 状态提供登录、登录后继续、重试或确认上传；上传成功后提示生成报告新版本且保留旧报告。候选字段 provenance 可展开查看。

## 改动文件

- `frontend/app.js`：来源进度安全归一化、动态卡片、年份/partial/错误展示。
- `frontend/research-tasks.js`：issues 状态投影、登录/继续/重试、人工确认 PDF 上传、报告新版本提示、字段来源展开；保留 textContent DOM 边界。
- `frontend/index.html`：来源进度动态容器、Research Task 待处理论文入口、资源版本号升级。
- `frontend/styles.css`：七来源自适应网格、待处理论文动作/确认态、字段来源展开样式。
- `tests/test_frontend_spec032_task12_issue_ui.py`：Task12 动态来源与 issue UI 静态契约。

## 后端接口契约核对

- 来源进度消费 `source_progress/sources` 数组或对象，识别 `source_id/source_kind/source`；不发明来源 ID。
- acquisition status 消费已有 `issues`、`actions`、`attempts`、`resolutions`；未修改后端。
- 交互端点为既有 `POST /api/papers/issues/{issue_id}/login|resume|retry|upload`。
- 上传只在用户勾选“我确认上传文件属于该候选论文”后发送 `identity_verdict=confirmed&identity_confirmed=true`；服务端仍是最终校验方。
- `report_action=generate_new_version` 只显示新版本提示，不改写旧报告。

## 测试命令/退出码/结果

- `node --check frontend/app.js`：退出码 0，通过。
- `node --check frontend/research-tasks.js`：退出码 0，通过。
- `.venv/bin/python -m pytest -q tests/test_frontend_spec032_task12_issue_ui.py tests/test_frontend_paper_contract.py tests/test_spec029_frontend_acquisition_progress.py tests/test_spec030_frontend.py tests/test_spec031_frontend.py`：退出码 0，33 passed。
- `.venv/bin/python -m pytest -q tests/test_frontend*.py`：退出码 0，229 passed。
- `git diff --check`：退出码 0，通过。

## 决策依据

- 复用 Task11 已冻结的 issue actions 和 acquisition status 返回，避免在前端推断/创建后端状态机。
- 动态卡片全部使用 `createElement`/`textContent`，来源名、错误码、论文 ID 和超长标题不进入 HTML 字符串。
- 上传身份不确定场景通过显式复选确认，不使用自动确认或远程凭证；waiting_login 不渲染 retry。

## 风险阻塞

- 未做真实浏览器 headed login、真实 PDF 上传或部署 smoke；需要主 Agent 在服务启动后验证。
- 当前论文检索搜索创建表单仍保留既有 USENIX 默认行为，本 Task 只改来源进度展示，不扩大搜索请求契约。
- 工作树含其他 Spec031/034/032 并行改动；本轮未执行 reset/stash/clean/checkout，未修改 backend。

## 主 Agent 后续动作

- 运行真实服务与浏览器 smoke：七来源动态卡、单源失败/partial、waiting_login 登录后继续、failed retry、身份确认上传和报告新版本提示。
- 按项目收口流程完成前端评审、最终全量回归、部署验证与 Spec032 状态台账更新。

## 时间与资源

- 开始：2026-09-20 05:50（Asia/Shanghai）
- 结束：2026-09-20 06:02（Asia/Shanghai）
- 总耗时：约 12 分钟
- 模型：Luna high（临时前端执行配置）
- 工具统计：shell 读取/检查 11 次；apply_patch 20 次；未调用后端测试、未调用子 Agent。
