# Spec016 云端成果保存记录

用户于 2026-10-12 明确授权开发期间定期 push。主 agent 在阶段性检查后保存到 `origin/feature/spec-016-portable-task-ledger`。

| 提交 | 保存内容 | 远端核验 | 阶段状态 |
|---|---|---|---|
| `65e0e12534541e050a6f5b170da946a3a692e1dd` | 重建协议、Task03/04 基础、Task05 领取及恢复实现与已读回测试 | `git push -u origin feature/spec-016-portable-task-ledger` exit 0；随后 `git ls-remote --heads origin feature/spec-016-portable-task-ledger` 返回相同完整 SHA | Task05 集中验收与 CLI 扩展测试进行中；Task06–09 未完成 |
| `1047abca43f9058053c62581ae1466ae7de7d158` | CLI 领取/partial 恢复、状态一致性扩展测试；170 项工具测试与 8 组 Git/SQLite smoke 的实测报告 | `git push origin feature/spec-016-portable-task-ledger` exit 0，远端更新 `65e0e12..1047abc` | Task05 独立评审随后通过；Task06 继续实施 |
| `01e064178ab5f1c6282189c027b576fddbaa2feb` | Task05 签字/P2 修复、Task06 冻结协议、Prompt 与安全产物 hash | `git push origin feature/spec-016-portable-task-ledger` exit 0，远端更新 `1047abc..01e0641` | Task06 提交日志、结果及事件继续分批实现 |
| `101781b99740ff635275d9bf95284f60429b8833` | Task06 J1/J2 文档恢复、J3 索引快照、结果、owner 与事件/JSONL；独立定向测试证据 | `git push origin feature/spec-016-portable-task-ledger` exit 0，远端更新 `01e0641..101781b` | Task06 索引锁、验证回执及最终提交链继续实施 |
| `3ddf4e7490ac133a8de384b7ce4f6f2362be4be4` | Task06 不可变 Git blob/mode schema、可重试索引锁标记、运行摘要；13 项 journal、7 项锁原语和 4 项摘要定向测试证据 | `git push origin feature/spec-016-portable-task-ledger` exit 0，远端更新 `101781b..3ddf4e7` | Task06 锁包装器、验证回执、结果统计及最终提交链继续实施 |
| `e0c300140936a5991b3ac3e47638a360a1c2344a` | 只读结果查询、固定 schema 的 JSON/CSV 统计及 CLI；9 项独立定向测试证据 | `git push origin feature/spec-016-portable-task-ledger` exit 0，远端更新 `3ddf4e7..e0c3001` | Task06 防御性查询测试与最终提交链继续实施 |
| `c53b68100673cbe22b2171208cc22bb70019287f` | 原始 blob/mode 捕获与变更检查、owned lock 包装器及恢复；6 项捕获测试和 13 项锁测试证据 | `git push origin feature/spec-016-portable-task-ledger` exit 0，远端更新 `e0c3001..c53b681` | Task06 候选提交、索引恢复及最终 DB 事务继续实施 |
| `5a1c5ea475af0f900a6286710cc68acdf3b84fde` | 实际验证命令、私有日志与回执；15 项进程/运行器测试以及 11 项结果/统计/CLI 测试证据 | `git push origin feature/spec-016-portable-task-ledger` exit 0，远端更新 `c53b681..5a1c5ea` | Task06 候选提交、索引恢复及最终 DB 事务继续实施 |
| `f5b3162337cc15c41c2a295ff0bf70cc77f29783` | 隔离索引中的候选提交、校验后原始文件检查；6 项真实 Git 候选测试证据 | `git push origin feature/spec-016-portable-task-ledger` exit 0；`git ls-remote --heads` 返回同一完整 SHA | Task06 分支 CAS、索引安装及最终 DB 事务继续实施 |

| `e4710817ae523bccbc5d8e54d1480e7dad11bdc8` | 终态 SQLite 事务、不可变产物及重放保护；16 项定向测试证据 | `git push` exit 0，远端更新 `f5b3162..e471081` | Task06 完整 Git/SQLite 生命周期集成尚未完成 |
| `be29bc199b46829cbe605ad182e38e26829bdea8` | CLI 事件、领取后 Prompt 持久化及私有观察快照；17 项 CLI/Prompt 与 7 项观察定向测试证据 | `git push` exit 0，远端更新 `e471081..be29bc1`；`git ls-remote --heads` 返回同一完整 SHA | Task06 完整提交及失败历史恢复继续实施；缓存检查发现测试 EOF 空行，后续修正 |

| `468f47036250a680f5cb95327e9f2960d7593d49` | J2 恢复遵循冻结的文档 Git 执行位，原子写入保持默认私有权限；26 项 journal/安全测试证据 | `git push` exit 0，远端更新 `be29bc1..468f470` | 完整生命周期、失败历史及 Task07–09 尚未完成 |

| `5ea861f0ea5bd7b19fa45db92b7b327523f30bef` | 原始基线可穿过含观察事件的 abandoned 父 run；10 项定向测试及真实 owner 死亡/Task05 恢复证据 | `git push` exit 0，远端更新 `468f470..5ea861f` | failed 历史公开领取尚未接线；真实中断恢复继续验收 |

该检查点可从 GitHub 恢复，不能解释为整项 Spec 已完成。真实 CodeBuddy 验收仍待本地执行。
