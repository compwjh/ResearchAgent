# 0003 论文下载的对端 IP 复核：证据来源统一为 httpcore `server_addr`

Status: accepted

论文导入批次曾全部以 `DOWNLOAD_BLOCKED`（对外文案"下载地址被安全策略拒绝"）失败。排查表明**下载地址能解析到、网络能连通、服务端已返回 HTTP 200**，失败发生在拿到响应之后的 SSRF 对端复核：真实 httpcore 流只以 `server_addr` 暴露远端地址，而 `_peer_from_response` 只查询 `peername`，后者恒为 `None`；`_check_peer` 因此判定"没有对端证据"，对自建客户端抛出"无法复核实际连接地址"。这是防护的**误报**——不是找不到地址，也不是网络下不了。

我们决定：`_peer_from_response` 按 `peername` → `server_addr` 顺序取值，并兼容 `extensions["server_addr"]`，使默认（未注入 resolver）的真实下载路径能取得真实对端 IP 并交给 `validate_peer_ip` 校验。

## Considered Options

- **自造 transport 并向 `extensions` 注入 `peer_ip`**：能解决，但需改接线（`_build_paper_batch_service` 传递 transport/client），并引入一层自定义网络栈，维护成本高；且未注入时默认路径依旧坏。
- **放宽 `_check_peer`（自带客户端取不到对端就放行）**：改动最小，但等于关闭真实链路的 SSRF 对端复核，使其形同虚设，不可接受。
- **要求调用方注入 `peer_ip_resolver`**：把问题推给调用方；现有测试正是靠注入 resolver 才从未暴露该缺陷，默认路径仍会误杀，不解决根因。
- **顺序读取 `peername` → `server_addr`（选定）**：一处取值修复，默认路径即可拿到真实对端 IP；顺序保证既有 mock/legacy transport（只提供 `peername`）行为不变，对端复核因此**真正生效**而非被绕过。

## Consequences

- 真实下载恢复：`validate_peer_ip` 现在能拿到实际连接的 IP，并校验其落在 `validate_url` 解析出的公共 IP 集合内，SSRF 防护由"误杀"转为"真正生效"。
- 既有的 DNS 预解析 + 白名单 + 逐跳重定向校验全部保持不变，未削弱任何一层。
- 测试必须覆盖 httpcore 真实形状（`peername` 为 `None`、`server_addr` 有值）；否则默认路径仍可能失真——本缺陷之所以长期存在，正是测试一律注入了 `peer_ip_resolver`。
- 服务层 `_mark_failed` 仍只持久化"错误码 → 固定文案"，进程内异常文本不入库；因此库里看不到"无法复核实际连接地址"这类子原因。是否细化落库文案属独立决策，不在本 ADR 范围。
