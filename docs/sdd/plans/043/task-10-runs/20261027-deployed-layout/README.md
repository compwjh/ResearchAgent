# 布局检查点实际部署验证

部署提交5d42211a，http://127.0.0.1:8000，地图JS25/CSS16。仅部署已通过独立评审的布局与后端合同，配色和全文状态界面尚未实现。

实际旧图0baabeae7268429c9f7e4de8098ae1d0、目标circle点击打开长标题详情；画布前后高460px，transform不变，圆心elementFromPoint命中circle。JSON与PNG为当前部署真实浏览器结果，不是模拟接口回放。地图SQLite备份位于主运行目录data/literature_maps/backups/task10-before-v7-20261027-125322.sqlite3，启动后schema7；首页/health/conversations/models/graph均200。

本记录仅为阶段部署烟测，不替代最终API E2E、配色/全文验收或Spec收口。
