# Task02 可用数据与许可盘点

关联：[Spec050](../../../../specs/050-agent-safety-and-factuality.md) · [PIGuard 证据核对](../../piguard-training-evidence.md) · [Go/No-Go](go-no-go.md)

| 项 | 值 |
|---|---|
| 核对日期 | 2026-11-14 |
| 范围 | 本机 `/Users/wjh/piguard-repro` 只读盘点；**未下载任何数据、未打开测试集** |

## 1. 代码与模型许可（本机已核实）

| 对象 | 路径 | 许可 | 状态 |
|---|---|---|---|
| PIGuard 上游代码 | `upstream/LICENSE` | **MIT**（Copyright (c) 2024 Hao Li） | 已核实，可复用；仍需逐文件审查后接入 |
| 基础模型 DeBERTa-v3-base | `models/deberta-v3-base/README.md:8` | `license: mit` | 已核实 |
| 上游 README 徽章 | `upstream/README.md:12` | License-MIT | 与 LICENSE 一致 |
| VIGIL / MARCH | 本机无副本 | 复用授权**未核实** | 按 Spec050：仅依据公开机制自主实现，不复制代码 |
| RAD 检索库 | 本机无副本 | 访问条件**未核实** | 数据卡区分「检索库快照」与「待发布完整评测文件」；需分别核实 |

## 2. 训练 / 验证数据（本机已核实）

| 项 | 值 | 证据 |
|---|---|---|
| 训练 | 76,729 条 | `runs/official-clean/datasets/train.json`；`audit.json` `train.rows` |
| 验证 | 144 条 | `runs/official-clean/datasets/valid.json`；`audit.json` `valid.rows` |
| 训练指纹 | `d2d3a74c…0cb` | `preparation-audit.json` `derived_sha256.train.json` |
| 验证指纹 | `fdf0f1f8…87b` | 同上，与 `source_sha256.valid.json` 相同（byte-identical） |
| 排除记录 | 6 条（3 空文本 + 3 验证重复） | `preparation-audit.json` `excluded_training_rows` |
| 数据审计 | `pass=true`、`normalized_exact_overlap_count=0`、`schema_errors=[]` | `runs/official-clean/audit.json` |
| 测试集 | `test_files_opened=false` | 同上；`preparation-audit.json` |
| 验证标签分布 | benign 96 / injection 48 | `audit.json` `valid.label_counts` |

## 3. 验证集构成与 PINT 冲突（需负责人裁决）

`audit.json` 的 `valid.source_counts`：

| 家族 | 子集 | 条数 |
|---|---|---:|
| NotInject | one / two / three | 16 + 16 + 16 = 48 |
| BIPIA | code / text | 12 + 12 = 24 |
| WildGuard | — | 24 |
| **PINT** | chat / documents / hard_negatives / internal_prompt_injection / jailbreak / public_prompt_injection | **8 × 6 = 48** |
| 合计 | | **144** |

**原样记录差异**：

1. Spec050「PIGuard 接入补充」写「**PINT 无授权时记 N/A**，完整论文总分记 N/A」，并要求「冻结候选后同题比较官方权重与本机权重在 NotInject、BIPIA 和 WildGuard 的表现」。
2. `upstream/README.md:94` 写明 PINT benchmark **非公开**、需表单申请访问；同文件 `:92` 说明 144 条验证集由 NotInject / BIPIA / Wildguard-Benign / **PINT** 构成并已随仓库提供。
3. 因此本机**训练验证阶段已使用 48 条 PINT 派生样本**，而公开评测口径要求 PINT 记 N/A。两者不是同一用途，但存在口径关联：验证成绩 `111/144` 中包含这 48 条。

本任务不裁决该差异，交负责人确认：验证集是否保留 PINT 派生样本、公开对照是否排除 PINT、以及 `111/144` 是否需按 96 条子集另报。

## 4. 公开对照数据可用性

| 数据 | 本机状态 | 结论 |
|---|---|---|
| NotInject | `upstream/datasets/NotInject_{one,two,three}.json` 存在 | 文件在本机；**未打开、未评测** |
| BIPIA | `upstream/datasets/BIPIA_{code,text}.json` 存在 | 文件在本机；**未打开、未评测** |
| WildGuard | `upstream/datasets/wildguard.json` 存在 | 文件在本机；**未打开、未评测** |
| PINT | 本机无独立基准文件 | 上游说明非公开需申请；按 Spec050 记 N/A |
| RAD | 本机无副本 | 访问条件与测试集可用性分别核实，未核实前不得使用 |
| 替代基准 | 未选定 | Spec050 允许「许可明确的替代集」，须标注与论文配置差异 |

上游随附评测文件与训练验证集的分隔、`test_files_opened=false` 一致；Task02 严格遵守「不读测试集」，未执行 `eval.py` / `eval_hf.py`。

## 5. 数据隔离与许可缺口（第二交付相关）

| 缺口 | 状态 |
|---|---|
| NotInject / BIPIA / WildGuard 各自许可与使用条件逐项核实 | 未执行 |
| RAD 检索库快照与完整评测文件的访问条件 | 未执行 |
| VIGIL / MARCH 复用授权 | 未执行（按 Spec050 自主实现） |
| 官方 PIGuard 权重获取与许可 | 未执行（Task08 需做同题对照） |
| 业务文档/用户输入自动进入检索或训练集 | 未发生；Spec050 明确禁止 |
| 按文档与攻击家族隔离训练、检索、调参、最终评测 | 训练/验证已按官方快照隔离；调参与最终评测隔离待 Task06 |
| 上线门槛由独立验证集先确定 | 未定稿（负责人） |

## 6. 明确不做

未下载受限数据、未自动下载任何模型、未执行 `HF trust_remote_code`、未打开测试集、未跑公开基准、未生成跨组增益数字。许可与评测口径的最终裁决由负责人定稿。
