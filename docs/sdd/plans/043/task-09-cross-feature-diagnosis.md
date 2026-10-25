# 2026-10-26 跨功能问题诊断与接续

主会话只读核查；本文不是实现/验收通过声明。用户要求补答额度中断期间的问题。当前未修改下述三个问题的业务代码，避免与待收口的地图动作反馈混为完成。

## 知识库重建入口（归属 Spec018）

- 实际GET `/api/kb/papers` HTTP200，目标“How to Peel a Million- Validating and Expanding Bitcoin Clusters.pdf”只有canonical `document_id=d4dfd2a620384ad5bece27320661f8f0`；v1=107、v2=308片段，均indexed/100/error=null。没有证据显示现有索引丢失。
- `frontend/app.js` 的 `rebuildKbPaper` 仍以 `paper.paper_id` 构造旧alias地址，`renderKbPapers` 未做ID归一；因此canonical-only记录构造错误目标。错误读取只看detail，未读取canonical error envelope，退化为“重建失败：重建失败”。尚未重放修改索引的POST，不声称已验证重建成功。
- 修复方向：复用canonical document ID和现有reindex接口/错误合同；不能恢复旧表或降低generation gate。回归必须用canonical-only真实响应形状，验证点击产生正确文档ID、202任务和可观察终态；覆盖结构化错误。单文档真实重建，禁止全库重建代替。

## 记忆管理红色404（归属 Spec038）

- 实际GET `/api/memories?scope=global&status=active` HTTP404 `detail=Not Found`；`loadMemories`仍调用此地址。
- `routes_conversations.py`明确记载Spec038移除了旧memories CRUD，真相源已改为MarkdownMemoryStore；系统规则卡成功不代表下方旧CRUD仍存在。
- `tests/frontend/test_frontend_management_contract.py`只断言APP源码含`/api/memories`，不检查服务实际路由，导致错误接口反而通过静态契约。
- 修复方向：按文件记忆真相源接齐管理展示/修改，不能重新引入旧SQLite真相源，也不能清空列表/隐藏404冒充恢复。涉及新的文件管理公开接口时，须先补Spec038接口/路径白名单/owner隔离及并发写边界，再确认实施；当前仅诊断，不承诺已实现管理能力。

## 等待登录不应依赖短期搜索有效期（归属 Spec032）

- 批次`1a76e369-c638-4f2c-a430-42552a1e7012`实际GET仍waiting_login；条目`9eed783f-ff98-4021-99dd-1ab2787688cb`为LOGIN_REQUIRED，search_id为2026-09-22人工ACM搜索。
- login/resume均先调用`_paper_item_browser_target`→`_paper_snapshot_for_item`，后者强制查原搜索有效期，过期即SEARCH_EXPIRED，早于新登录窗口的创建。批次服务`_snapshots_for`已经支持哈希核验的持久快照独立于搜索TTL，路由没有复用这条恢复链。
- 此外浏览器会话另有短期TTL（配置缺省回退article_login_timeout_seconds=300）；第三方Cookie/权限也可能自然失效，均不能与任务有效期混同。
- 修复目标：等待人工操作的任务与论文快照持续保留，用户何时点“打开登录”都可基于服务端可信快照重新开窗口；资源超时可回收临时窗口，但不取消任务/强迫重新检索，恢复时可复用现有持久profile并重新核验当前授权。不能承诺第三方登录永不过期，也不能直接关闭安全检查或无限保留浏览器进程。缺失/损坏快照须说明恢复需要什么，不能伪造候选或信任客户端URL。
- 必测：搜索过期后首次开登录、服务重启后打开、临时窗口过期后重开、用户延迟操作、快照损坏拒绝、未授权站点拒绝、继续成功关联原批次，不依赖即时人工登录。

## 回归缺口

历史全量/静态测试通过不能替代真实部署契约：需要把列表实际DTO→按钮→实际API→状态/产物串起来，并保留“历史文档”“跨版本管理页”“等待人工数日的批次”案例。不能将此前地图窄测试通过冒充这三个场景已验证。
