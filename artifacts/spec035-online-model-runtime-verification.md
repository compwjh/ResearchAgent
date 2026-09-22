# Spec035 线上模型运行时验收（真实 API 端到端）

> 运行时间：2026-09-20T18:19:22+0800
> 服务：`http://127.0.0.1:8000`，当前工作树部署实例（`./deploy/start.sh` 前台常驻）
> 结论：**通过**。线上模型已注册、探测连通、真实对话返回内容。
> 本文件只记录真实请求与真实响应；所有 `curl` 均带 `--noproxy '*'`
> （本机有 `HTTP_PROXY=127.0.0.1:58692`，不加会把 localhost 请求吃掉返回 502）。

## 背景：本次修的是配置，不是代码

spec-035 的代码早已合入（`6fe3523` 接入 provider、`df674a5` 标记已完成），
但运行时一直未生效。本次定位到两级配置问题：

| 阶段 | `.env` 状态 | 结果 |
|---|---|---|
| 修前 | 只有 `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL`，**无 `ONLINE_MODELS`** | `get_online_models()` 空 → online 组为 0 项（验收场景 E 退化形态） |
| 修中 | `ONLINE_MODELS=deepseek:Deepseek-V4.1-Flash` | 注册成功但 `status=unreachable` |
| 修后 | `ONLINE_MODELS=deepseek:deepseek-flash` | `status=ready`，对话真实返回 |

`unreachable` 的真实原因（直连 `POST https://api.deepseek.com/chat/completions`，`max_tokens=1`）：

```json
{"error":{"message":"The supported API model names are deepseek-flash, deepseek-v4-pro,
 but you passed Deepseek-V4.1-Flash.","type":"invalid_request_error",
 "param":null,"code":"invalid_request_error"}}
```

HTTP `400`。网络是通的（`GET https://api.deepseek.com/models` 返回 `401` 未鉴权，即可达），
Key 有效。**`Deepseek-V4.1-Flash` 是 CodeBuddy 子代理档位名，与 DeepSeek 官方 API 不是同一套命名。**

## 运行 A：分组接口与连通性探测（通过）

请求：`GET /api/models?probe=1`，HTTP `200`。

online 组返回（原样）：

```json
{"id": "deepseek:deepseek-flash", "name": "deepseek-flash", "source": "online",
 "provider": "deepseek", "display_name": "deepseek:deepseek-flash",
 "current": false, "status": "ready", "capabilities": {"reasoning_efforts": null}}
```

- `status` = **`ready`**（修前为 `unreachable`）
- 端侧组 11 项全部 `status=ready`，未受影响 —— 符合 spec-035「`/api/health` 的 `models` 字段不变、零回归」
- 探测为 `max_tokens=1` 的轻量请求，结果有 60s 内存缓存

## 运行 B：线上模型真实对话（通过，验收场景 A）

请求：`POST /api/chat`，HTTP `200`，SSE 流。

```bash
curl -s --noproxy '*' -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"question":"只回复两个字：你好","model":"deepseek:deepseek-flash","stream":false}'
```

响应（原样）：

```text
data: {"type": "meta", "model": "deepseek:deepseek-flash", "mode": "normal"}

data: {"type": "token", "content": "你好"}

data: {"type": "done"}
```

- `meta.model` = `deepseek:deepseek-flash` —— 确认请求确实路由到线上 provider，不是回退到端侧
- 有真实 `token` 产出并正常 `done`

> 踩坑：该接口的消息字段是 **`question`**，不是 `message`。填 `message` 会返回
> `422 {"detail":[{"type":"missing","loc":["body","question"]}]}`。

## 复现命令

```bash
cd /Users/wjh/ResearchAgent
./deploy/start.sh                                    # 前台常驻；改 .env 后必须重启才生效

curl -s --noproxy '*' http://127.0.0.1:8000/api/health
curl -s --noproxy '*' 'http://127.0.0.1:8000/api/models?probe=1'
curl -s --noproxy '*' -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"question":"只回复两个字：你好","model":"deepseek:deepseek-flash","stream":false}'
```

## 遗留事项

1. **`.env` 里 `RESEARCH_ONLINE_FALLBACK_ENABLED` 已被置为 `true`**（本次一并改动）。
   含义：Research Runtime 遇瞬态失败会自动切到已注册线上模型，研究任务会产生真实 API 消耗。
   若只想手动选用、不要自动兜底，改回 `false` 并重启。
2. 本轮只验证 `deepseek-flash`。`deepseek-v4-pro` 亦在官方支持列表内且探测 HTTP `200`，
   但未纳入 `ONLINE_MODELS`，需要时追加即可（逗号分隔）。
3. Reranker 模型文件缺失（`data/models/qwen3-reranker-0.6b-q8_0.gguf`），
   服务以 RRF 降级模式启动，属既有状态，与线上模型无关。
