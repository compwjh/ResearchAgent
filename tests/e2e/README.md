# 前端 / 网站端到端测试（真实浏览器）

覆盖 **spec028–031** 共同支撑的「研究会话全生命周期」：创建 → 计划/模型路由 → 运行与持久化调度/恢复 → 全文获取 → 证据矩阵与只读报告。测试只通过浏览器操作页面，**不显式调用后端 API**。

## 为何需要它

`tests/frontend/*.js` 只是用 Node `require` 前端模块做逻辑单元测试，没有浏览器、没有真实页面交互。本项目此前**缺真实浏览器端到端**这一类测试（见 Spec 039 类型矩阵 `❌ 基本缺失`），本目录补齐该缺口。

## 技术栈

- Python + Playwright（`playwright` 包，已装在 `.venv`）。
- 不依赖 `pytest-playwright` 插件，浏览器在 `conftest.py` 用同步 API 直接管理。

## 运行步骤

```bash
# 1) 安装浏览器二进制（仅需一次）
.venv/bin/python -m playwright install chromium

# 2) 启动后端（端口 8000，同时 serve 前端静态资源）
./deploy/start.sh -d

# 3) 运行端到端测试
RUN_E2E=1 .venv/bin/python -m pytest tests/e2e -v
```

可选：用 `E2E_BASE_URL=http://other-host:8000` 指向非默认地址。

## 设计约定

- 整套用例用 `pytestmark = pytest.mark.skipif(not RUN_E2E, ...)` 保护：**常规 `pytest tests` 收集时整集跳过**，不会污染单元/集成套件、也不会因缺少浏览器/服务而报错。
- 重型段（跟随到运行/完成）依赖后端 LLM；若环境无可用 LLM，对应断言会 `pytest.skip`，创建与计划渲染段仍可通过。
- 选择器直接取自 `frontend/index.html` 的 `research-view` 结构（`#research-goal`、`#research-task-list .research-task-card`、`#research-detail-status[data-status]`、`#research-plan-section`、`#research-timeline-section`、`#research-acquisition-*`、`#research-evidence-matrix-body`、`#research-report-markdown` 等）。
