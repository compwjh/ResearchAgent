# Spec042 最终部署与运行核对

最终实现候选：`145f9d6`，分支`codex/spec042-offline-evaluation`。收口时再次核实实现、前端及测试均无相对此候选的未提交变动；其后的提交仅为证据和状态文档。

## 实际可访问入口

- Langfuse：`http://127.0.0.1:3000/`，public ready真实HTTP200，返回`status=OK/version=4.27.0`。
- Worker：`http://127.0.0.1:3030/api/health`，真实HTTP200、`status=ok`。
- Spec043既有服务：`http://127.0.0.1:8000/`，ready=true，四项预热均ready；未重启或改动其业务代码。
- 以上服务均由既有数据运行，只监听loopback；主会话持有前台会话，实际启动命令与PID见[运行记录](langfuse-runtime-preflight.md)。没有安装、迁移、改凭据或暴露到局域网/公网。

## 工具部署与产物

本Spec是Python旁路CLI，不新增API或前端，无独立前端构建。仓库根目录已真实运行的入口为`.venv/bin/python -m backend.eval_042.cli`；帮助命令退出0，实际评分命令、环境前提和本地报告见[人工步骤](manual-acceptance.md)。既有本机项目seed凭据与CLI默认配置仅以内存布尔比较确认匹配，文档不写入值；切换项目需显式配置`LANGFUSE_PK`与`LANGFUSE_SK`。

成功run：`runs/20261023-0442-real-e2e-145f9d6/`，CLI退出0，本地判官3次，一次score POST，canonical exact验证通过。报告JSON/Markdown completed，written=1/verified=1/failed=0。headless正常登录既有Langfuse，只读核对同一trace的chat_quality与1.0；UUID由API精确核验，不声称页面展示UUID。

最终完整回归：3335 passed/0 failed/2合法RUN_E2E skip/67 subtests/5 warnings，退出0。真实API/页面验收不由skip或mock替代；原score可见性失败和一次390px超时均保留在历史run。独立tester及architect均通过，最终准备度9/10+1明确不适用项。用户尚未实际执行人工验收。

所有提交仅本地保存，没有push或合并main。人工一致率仍未评估，不把构造gold或本次自动判官得分冒充人类评价结论。
