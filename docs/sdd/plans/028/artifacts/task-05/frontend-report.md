# Spec028 Task05 前端交接报告

## 状态

**已完成（前端功能门；待 Task06 最终评审、全量回归与部署）**

## 实现范围

- `frontend/research-tasks.js`
  - 为任务详情接入 Task04 已存在的 `pause`、`resume`、`feedback(action=approve)` 与 `cancel` HTTP 接口。
  - 增加 `paused` / `recovery_required` 状态文案与操作权限投影；中断任务展示恢复提示，刷新沿用既有详情/SSE 恢复路径。
  - 暂停、继续、批准、取消统一使用二次点击确认（不调用原生 `prompt`/`confirm`），请求期间禁用同组操作并设置 `aria-busy`，重复点击不会重复提交。
  - 对网络失败可重试；对终态冲突、运行态冲突、非法状态和计划版本过期显示稳定错误并要求刷新，保持已持久化状态不被乐观伪造。
  - 成功后合并服务端返回的任务状态与计划版本，刷新任务卡；继续/批准重新接入既有 SSE，取消关闭流；不新增状态机。
- `frontend/index.html`
  - 增加暂停、继续、批准按钮和中断恢复提示，统一由任务状态控制隐藏/可用性。
  - `research-tasks.js`、`app.js`、`styles.css` 资源版本升至 `3` / `50`，保留历史版本兼容标记。
- `frontend/styles.css`
  - 增加 paused/recovery 状态徽章、操作 loading/确认/成功/失败/冲突态和窄屏可读的恢复提示，全部限定在 `#research-view`。
- `tests/test_frontend_spec028_task05_contract.py`
  - 固定 API 路径映射、状态投影、确认/防重复、错误恢复、DOM/XSS、资源版本合同。

## 验证

```text
node --check frontend/research-tasks.js
git diff --check
.venv/bin/python -m pytest --noconftest -q \
  tests/test_frontend_spec028_task05_contract.py \
  tests/test_frontend_spec034_task04_contract.py \
  tests/test_frontend_spec034_task07_contract.py \
  tests/test_frontend_spec034_task08_contract.py \
  tests/test_frontend_spec034_task09_contract.py
node tests/test_frontend_spec034_task08.js
node tests/test_frontend_spec034_task09.js
```

结果：Python 合同测试 `31 passed`，两项 Node 合同测试均 PASS；未运行后端 pytest，未提交或推送。

## 边界

- 未修改 `backend/**`，未新增 recover 端点或第二套状态机。
- `recovery_required` 当前只做安全提示；Task04 未提供对应写入 API，前端不伪造恢复成功。
- Task06 仍需执行前端/后端最终全量回归、真实浏览器 smoke、启动与运行时验证。
