# Task11 主会话真实浏览器验证记录

## 已完成的桌面验证（2026-10-28）

对象为当前8000服务，JS37/CSS23；地图 `0baabeae7268429c9f7e4de8098ae1d0`，种子 `21041260a5394f42891b020128fa60fa`。操作由主会话通过真实浏览器执行，不是自动测试夹具。

- 打开“扩展关联论文”，参考文献45条、引用本文首50条；按引用数排序后恢复来源顺序。候选来源、发表来源、摘要可用性和零引用数均可见。
- 跨两个页签选中两篇，批量确认后新增两篇；再次选择一篇，遇到版本冲突后点击“重核当前选择”，重新确认后成功。两批共三篇真实分析完成，独立公开API核验见[记录](2026-10-28-expansion-browser-api.md)。另一次独立API端到端新增三篇见[API记录](2026-10-28-expansion-real-api.md)，两次计数不能混用。
- 两次加入后、点击“查看新增论文”前，旧24个节点DOM坐标/半径和视图变换保持不变。新增点的间距检查通过；原始快照和计算结果在下方目录。
- 切换两条批次历史，分别显示对应的两篇和一篇；旧批次“查看新增论文”定位到该批次论文。

证据：[浏览器目录](task-11-runs/20261028-browser/)。`ui-before.json`、`ui-after-both.json`、`ui-spacing.json`为读取的DOM数据；`ui-selected-two.png`、`ui-two-batches.png`、`ui-first-history-locate.png`为实际截图。API独立核验另外记录持久化位置、旧节点和边保留及摘要产物。

## 手机缺陷与验收边界

390×844真实视口下，候选面板被父容器挤压到约20px（clientHeight18，scrollHeight872），父画布面板高度654px。见`mobile-panel-before.json`、`mobile-expanded-before.png`。这使手机候选读取与选择不可用，判定为阻塞；不能用此前385项前端通过替代真实手机成功。

2026-10-29继续修复：前端开发子Agent已接手，要求以受限父容器高度建立回归，再验证375/390及桌面。修复后版本、真实截图和最终结论待补；当前不宣告Task11完成或READY_FOR_USER。

## CSS24真实手机复核与后续阻塞

2026-10-29当前8000页面实际加载JS37/CSS24。独立验证页打开既有地图与种子，390×844预览高度248.859px、client247，375×844高度240px；documentWidth分别为390/375，无横向溢出。真实点击引用本文页签、排序选择并勾选候选，确认入口曾变为“批量确认所选论文（1个新身份）”；本轮未提交新批次。截图见`mobile-390-after.png`、`mobile-375-after.png`。随后已重置临时视口。

但最终前端全量CSS24为386通过/1失败/0跳过：既有真实触控测试无法点开详情，独立重跑仍失败。不能据上述预览高度通过宣告整个手机体验通过。已交回前端开发诊断并保持原真实触控断言，Task11仍实施中；修复后的新版本必须另行复审和全量。

## CSS25真实手机复核

当前8000静态候选7364a26b，JS37/CSS25。375×844下关闭预览时画布和SVG均324px，点击GAT圆节点后详情面板is-open为true，标题正确。点击“扩展关联论文”后预览240px，参考文献45/引用本文50页签可操作，切换引用本文并按年份排序成功；390×844预览248.859px，两者documentWidth均等于视口宽，无横向溢出。截图`mobile-css25-375.png`及`mobile-css25-390.png`，390测量`mobile-css25.json`。临时viewport已reset。

本次真实浏览器验证通过的是页面点击及尺寸；物理手指触控由独立Chromium真实touch事件回归覆盖，不能声称CUA点击等同物理手机实机。最终前端全量attempt4仍待完成。

## CSS25手机端完整扩展链（新增验收数据）

390×844真实浏览器点击“引用本文50”→“加载更多50篇”，先显示“正在读取下一页”，随后页签100、已加载100篇。选择有摘要候选`candidate-33841855e806bb3b4d08aa79`（mmWave Radar-Based Unsupervised Person ReID via Multi-Level Mutual Signal Contrastive Learning），按钮变为“批量确认所选论文（1个新身份）”，点击后受理批次`28ff58c5244c46ddb8b31491e7702606`。页面真实提示“已新增1篇·已有0篇·待处理1项”“等待摘要分析结果”“分析排队1·完成0·失败0”和论文“分析排队中”。原始DOM及截图`mobile-css25-pending.json/png`。此为先前API3篇和桌面UI3篇之外的第七篇，终态另补，不以受理当完成。

手机新批次终态：页面显示“批次已完成”“待处理0项”“分析排队0·完成1·失败0”及论文“分析完成”，见`mobile-css25-completed.json/png`。独立QA公开API GET确认批次completed、新节点`a9dfddd15066489e96d57f576e5526de`、analysis`31bca85908bb4863b6b7d2558888f75b`completed且summary非空；graph revision196、28节点/25边。手机GUI加载、选择、确认、等待反馈和完成产物链通过。临时viewport再次reset回默认。

### 当前只读产物快照补证

截图及最初QA观察时graph revision为196；随后新节点布局保存后，当前公开GET返回revision197（28节点/25边）。二者是不同采集时刻，不改写历史截图/响应。当前原始HTTP200响应见[batch](task-11-runs/20261029-mobile-api/batch.json)、[analysis](task-11-runs/20261029-mobile-api/analysis.json)、[graph](task-11-runs/20261029-mobile-api/graph.json)，包含采集时间、请求方法/路径、状态及原响应体；batch和analysis均completed。候选完整ID为`candidate-33841855e806bb3b4d08aa79`。
