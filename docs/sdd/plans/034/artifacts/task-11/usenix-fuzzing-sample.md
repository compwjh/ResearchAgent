# USENIX Security 模糊测试方法综述（目录证据样本）

> 生成时间：2026-09-16  
> 证据级别：USENIX 目录元数据（标题、摘要）  
> 说明：本样本用于验证“至少 5 篇候选 + 实质性 Markdown 输出”。5 篇均来自已缓存的 USENIX 目录候选池（`search_id=dd5c47aa0cb541188b884c27fa233e67`）；没有下载 PDF，因此结论只基于目录摘要。

## 研究范围

主题是 USENIX Security 中的模糊测试方法，重点观察测试对象、状态建模、输入生成和漏洞发现方式。目录中已找到并保留 5 篇相关论文。

## 论文摘要

### AidFuzzer: Adaptive Interrupt-Driven Firmware Fuzzing via Run-Time State Recognition

- 证据对象：`de8ac2a9bd6ef6161712af112c4ed298`
- 摘要：针对固件模糊测试中的中断处理问题，论文根据运行时状态识别中断触发时机，以减少固件过早崩溃或卡死，并提高代码覆盖率。
- 关键词：目录未提供（不由模型补写）
- 引用：`catalog:de8ac2a9bd6ef6161712af112c4ed298`

### ChainFuzz: Exploiting Upstream Vulnerabilities in Open-Source Supply Chains

- 证据对象：`9a3901ced063c726cb3ca72465ace6db`
- 摘要：研究开源软件供应链中的上游漏洞利用，关注软件组成分析工具误报较高导致人工验证成本上升的问题，并通过模糊测试辅助发现可利用路径。
- 关键词：目录未提供（不由模型补写）
- 引用：`catalog:9a3901ced063c726cb3ca72465ace6db`

### CoreCrisis: Threat-Guided and Context-Aware Iterative Learning and Fuzzing of 5G Core Networks

- 证据对象：`859012d84d4f30012440908e9bd4645c`
- 摘要：面向 5G 核心网实现，论文提出有状态黑盒模糊测试框架，通过构建有限状态机表示并进行威胁引导的迭代学习，识别逻辑错误和协议状态问题。
- 关键词：目录未提供（不由模型补写）
- 引用：`catalog:859012d84d4f30012440908e9bd4645c`

### Effective Directed Fuzzing with Hierarchical Scheduling for Web Vulnerability Detection

- 证据对象：`60fd7cc8c2a7fd2c34ecabcfe7ee070d`
- 摘要：针对 Java Web 应用测试空间大、漏洞目标分散的问题，论文提出带层级调度的定向模糊测试方法 WDFuzz，以更有效地分配测试预算并发现 Web 漏洞。
- 关键词：目录未提供（不由模型补写）
- 引用：`catalog:60fd7cc8c2a7fd2c34ecabcfe7ee070d`

### Encarsia: Evaluating CPU Fuzzers via Automatic Bug Injection

- 证据对象：`22c4e8be6db942f585b68c38eeeaf990`
- 摘要：论文关注 CPU 模糊测试器之间难以公平比较的问题，通过自动注入已知错误构造可重复的评估基准，比较不同测试器的发现能力和覆盖表现。
- 关键词：目录未提供（不由模型补写）
- 引用：`catalog:22c4e8be6db942f585b68c38eeeaf990`

## 跨论文观察

这 5 篇论文呈现出三条共同路线：第一，测试对象从固件、Web 应用扩展到 5G 核心网和 CPU；第二，单纯随机变异逐渐被运行时状态识别、有限状态机、威胁引导和层级调度替代；第三，评估重点从“是否找到新漏洞”扩展到覆盖率、状态探索效率和可重复比较。以上归纳只依据目录摘要，全文导入后还需要用切片证据复核。

## 局限

- 当前样本没有下载或读取 PDF 全文。
- 关键词使用目录已有字段；缺失字段不会由模型补写。
- 论文之间的性能数字和实验结论没有在摘要之外扩展。

## 引用清单

- `catalog:de8ac2a9bd6ef6161712af112c4ed298`
- `catalog:9a3901ced063c726cb3ca72465ace6db`
- `catalog:859012d84d4f30012440908e9bd4645c`
- `catalog:60fd7cc8c2a7fd2c34ecabcfe7ee070d`
- `catalog:22c4e8be6db942f585b68c38eeeaf990`
