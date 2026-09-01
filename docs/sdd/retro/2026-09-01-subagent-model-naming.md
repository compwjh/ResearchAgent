# 复盘：子代理 model 名带 `-q4` 报 not found 的真实根因

> 归档性质：一次性环境配置问题的排查记录，**低频场景，不进 `AGENTS.md`**。
> 若将来再次出现子代理 `Subagent model config is invalid! Model ... not found`，再来查本文件。
> 日期：2026-09-01

## 1. 现象

给 `junior-dev` 的 front matter 填带量化的名字后，分派即失败：

```
Subagent model config is invalid! Model qwen3.8:27b-q4 not found
```

先后尝试过的名字与结果：

| agent 里写的 model | 结果 |
|---|---|
| `qwen3.8:27b` | ✅ 可用 |
| `qwen3.5:9b` | ✅ 可用 |
| `oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU` | ❌ not found（含 `/`） |
| `qwen3.8:27b-q4` | ❌ not found |
| `qwen3.8-27b-q4` | ❌ not found（本次修复前） |

## 2. 曾得出的错误结论（及为何错）

一度归纳为"**框架只认无后缀的标准名，任何带 `-q4` 的名字都不认**"，并据此推断框架有内置白名单、新 `ollama create` 的 tag 不会自动进入白名单。

该结论**是错的**。它把"名字字符串不一致"误判成了"命名格式不被接受"，导致后续转向"用别名绕开命名"的错误方向，白白多试了几轮。

## 3. 真实根因

**agent 的 `model` 字符串，与用户级 `models.json` 里注册的 `id`，从来就不是同一个字符串。**

三个具体错误叠加：

1. **横线版 vs 冒号版**
   注册进 `~/.codebuddy/models.json` 的是 `qwen3.8:27b-q4`（冒号），agent 里写的却是 `qwen3.8-27b-q4`（横线）。两者是不同字符串，框架做精确匹配，必然 not found。

2. **注册到了框架不读的位置**
   有一轮把条目只写进了**项目级** `.codebuddy/models.json`，而框架实际只读**用户级** `~/.codebuddy/models.json`（此点 `AGENTS.md` 早有记录，排查时没有回头查）。

3. **项目级配置被污染，干扰判断**
   项目级文件里 `qwen3.8:27b-q4` 这个 id **重复出现两次**，且字段与可用条目不一致（`vendor: "Ollama"` vs `"user"`、`maxOutputTokens: 4096` vs `32768`、缺 `supportsReasoning`）。重复 id 让"到底注册没注册"变得无法判断。

## 4. 排查手法（可复用）

**用 blob ID 判断"哪些名字其实是同一个模型"**：`ollama list` 中 ID 列相同的行，是同一模型的不同 tag，不是多个模型。

```
NAME                                          ID              SIZE
qwen3.8-27b-q4:latest                         9c67ea656a96    17 GB
qwen3.8:27b                                   9c67ea656a96    17 GB
oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU    9c67ea656a96    17 GB
```

由此得到一个关键事实：**`qwen3.8:27b` 本身就是 q4_K_M 量化版**，与那个名字很长的量化模型是同一 blob。所谓"要换用量化模型"其实早已在用，只是名字看不出来。

同理，如果某个名字 ID 与其他行都不同（如当时的 `qwen3.8:27b-q4` = `10f7aa483419`），说明它是被 `ollama create` 出来的**另一个** blob，不是想要的那个量化模型——这是当时没发现的第二个坑。

## 5. 修复动作

1. 备份两级 `models.json`（曾因改乱配置导致用户无法选择线上模型，改动前必须备份）。
2. 用户级 `~/.codebuddy/models.json` **只追加**、不改原有条目，新增：

   ```json
   {
     "id": "qwen3.8-27b-q4",
     "name": "qwen3.8-27b-q4",
     "vendor": "user",
     "url": "http://localhost:11434/v1/chat/completions",
     "maxInputTokens": 32768,
     "maxOutputTokens": 32768,
     "supportsToolCall": true,
     "supportsImages": true,
     "supportsReasoning": true
   }
   ```

   字段名与取值克隆已验证可用的条目，避免字段缺失导致条目被框架过滤。
3. 项目级 `.codebuddy/models.json` 清掉重复 id，与用户级对齐。
4. 用 `python3 -c "json.load(...)"` 校验语法与重复 id。
5. 先用 `curl` 打到 Ollama 的 `/v1/chat/completions` 确认该 model 名在 Ollama 侧可响应，再排查框架侧。

## 6. 结论与规则

- `model` 名**带 `-q4` 完全可行**，格式不是障碍。
- 铁律：**agent 的 `model` 字符串必须与用户级 `models.json` 中某条 `id` 逐字符相同，且不含 `/`**。
- `models.json` 是**热加载**的，改完无需重启，下一次分派即生效（本次追加后当次分派即成功，38.73s）。
- 排查顺序应为：先比字符串是否逐字符一致 → 再看注册位置（用户级）→ 再看字段完整性 → 最后才怀疑框架限制。**不要一上来就归因为"框架不支持这种命名"**。

## 7. 关于 `q4_K_M` 与 `mtp-q4_K_M` 的选型

- `q4_K_M`：4bit 分组量化里质量与体积平衡最好的常用档位，社区默认推荐。
- `mtp-q4_K_M`：在 q4_K_M 基础上带 MTP（多 token 预测），只有**支持 MTP 的推理后端**才有加速收益；Ollama 的 OpenAI 兼容接口未必能正确利用，反而增加兼容风险。
- 结论：本项目选 **`q4_K_M`（不带 mtp）**。当前 `qwen3.8-27b-q4` 指向的 blob `9c67ea656a96` 正是 `q4-km-32gbGPU`，已符合。
