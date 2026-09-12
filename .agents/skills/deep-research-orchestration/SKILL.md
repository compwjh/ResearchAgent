---
name: deep-research-orchestration
description: 会话式深度研究的领域编排协议，负责 Intake、研究范围和受控阶段衔接。
tools: []
---

# 深度研究编排

本 Skill 只描述研究领域的会话编排，不执行搜索、下载、导入或模型运行。

## 会话入口

明确的深度研究请求进入 `begin_research_intake`。先展示已启用 Skill 的摘要，
再通过 `activate_skill` 完成能力校验后才读取本 Skill 正文。普通聊天和含糊的
“查一下”请求不得静默创建研究 Session。

## Intake 规则

逐项收集主题、研究目标和时间范围；三者都是计划前阻塞字段。语言、来源、
深度、引用和输出格式使用可见的安全默认值。每个字段必须保留来源、置信度、
确认状态及产生它的消息 ID。缺少阻塞字段时只追问，不创建 ResearchTask。

## 后续边界

当前会话层只负责恢复 Session/Draft 和向用户呈现缺失字段。计划生成、审批、
搜索、AgentRun 与报告交付由后续受控阶段处理；本 Skill 不创建子 Agent，
也不授权未注册的 Tool、Shell、Python 或任意公网 URL。
