# Task02 本机复训证据核对记录（PIGuard formal-v1）

关联：[Spec050](../../specs/050-agent-safety-and-factuality.md) · [Task02 契约](task-02-contract-and-feasibility.md) · [任务索引](README.md)

| 项 | 值 |
|---|---|
| 核对日期 | 2026-11-14 |
| 执行分支 / commit | `codex/spec050-piguard-integration` / `04bc3b34` |
| 核对对象 | `/Users/wjh/piguard-repro`（本机目录，Git 外） |
| 范围 | 只读：读取训练产物文件、计算权重 SHA-256、撰写本记录 |
| 未执行 | 未加载模型、未读取测试集、未做权重转换、未跑公开基准、未改任何运行时代码 |
| Spec050 状态 | `待确认`（不因本记录变更） |
| Task02 状态 | `待执行`（其余契约与可行性验收仍待执行，不因本记录变更） |

预期值来源：`docs/sdd/specs/050-agent-safety-and-factuality.md` §「PIGuard 接入补充（2026-11-13）」第 1 条。

---

## 1. 结论汇总

| # | 核对项 | Spec050 预期 | 实测值 | 证据路径（本机） | 结论 |
|---|---|---|---|---|---|
| 1 | 训练退出码 | `0` | `0` | `logs/formal-v1.exit-code`；`logs/formal-v1.log` 尾部 `exit_code=0` | 符合 |
| 2 | `finished` 事件 | 完成 | 1 条，`stage=finished`，`update=7194`，`epochs=3` | `runs/formal-v1/events.jsonl` 末行 | 符合 |
| 3 | epoch 数 | 3 | `epochs=3`；3 次 `validation`（epoch 0/1/2） | `events.jsonl`；`config.json` `epochs=3` | 符合 |
| 4 | 优化器步数 | 7,194 | `total_updates=7194`、`updates_per_epoch=2398`、`finished.update=7194`、事件流 `max update=7194` | `events.jsonl` 首行/末行 | 符合 |
| 5 | 最佳验证成绩 | 111/144 | `accuracy=0.7708333333333334` × 144 = **111/144**（最后一次 validation，epoch 2） | `runs/formal-v1/best_scores.json`；`events.jsonl` 的 3 条 `validation` | 符合（需换算，见 §3.4） |
| 6 | 训练样本数 | 76,729 | `76729`（`started.train_rows`、`audit.train.rows`、`preparation-audit.derived_rows.train`） | `events.jsonl`；`runs/official-clean/audit.json`；`runs/official-clean/preparation-audit.json` | 符合 |
| 7 | 验证样本数 | 144 | `144`（`started.valid_rows`、`audit.valid.rows`、`derived_rows.valid`、`best_scores.count`） | 同上 | 符合 |
| 8 | 排除记录 | 3 条空文本 + 3 条验证重复 | 共 6 条：`empty_or_invalid_prompt` × 3、`normalized_exact_overlap_with_validation` × 3；`source_rows.train=76735` → `derived_rows.train=76729`（差 6） | `runs/official-clean/preparation-audit.json` | 符合 |
| 9 | 基础模型版本 | DeBERTa-v3-base revision `8ccc9b6f36199bec6961081d44eb72fb3f7353f3` | `microsoft/deberta-v3-base` / `8ccc9b6f36199bec6961081d44eb72fb3f7353f3` | `logs/model-revision.txt`；`runs/formal-v1/config.json` | 符合 |
| 10 | PIGuard 上游 commit | `1b5751e88bf7475acbedfc8eda795ce060307c84` | `1b5751e88bf7475acbedfc8eda795ce060307c84` | `logs/upstream-commit.txt`；`config.json`；`preparation-audit.json` | 符合 |
| 11 | `best_model.pth` SHA-256 | `3f284d8e2655ba9714ab2ab449645aa82f4953a1c7ec20cf62402dfb81af35ea` | `3f284d8e2655ba9714ab2ab449645aa82f4953a1c7ec20cf62402dfb81af35ea` | `shasum -a 256 runs/formal-v1/best_model.pth`，退出码 `0` | 符合 |

**Spec050 的 11 项预期值全部有实测证据且一致，无缺失项。** 另有 4 项记录层面的观察/差异，按派工要求原样保留于 §3，不代负责人裁决。

---

## 2. 实测明细

### 2.1 退出码与完成状态

```
$ cat /Users/wjh/piguard-repro/logs/formal-v1.exit-code
0

$ tail -2 /Users/wjh/piguard-repro/logs/formal-v1.log
finished_at=2026-11-10T04:44:21Z
exit_code=0
```

`events.jsonl` 共 744 条事件，stage 分布：`started` 1、`train_update` 722、`checkpoint` 17、`validation` 3、`finished` 1。仅 1 条 `finished`，无中断后重跑的第二条完成记录。

### 2.2 步数与 epoch

```
{"time":"2026-11-10T03:03:09+0800","stage":"started","device":"mps",
 "train_rows":76729,"valid_rows":144,"updates_per_epoch":2398,
 "total_updates":7194,"resumed":false}
{"time":"2026-11-10T12:44:20+0800","stage":"finished","update":7194,
 "epochs":3,"best_accuracy":0.7708333333333334}
```

`2398 × 3 = 7194`，与 `finished.update` 及事件流最大 `update` 一致。`logs/g4-go-decision.md` 亦记载 2,398 updates/epoch、合计 7,194。

### 2.3 三次验证成绩

| epoch | update | accuracy | 换算 | loss |
|---|---|---|---|---|
| 0 | 2398 | `0.7638888888888888` | 110/144 | 0.7453556524382697 |
| 1 | 4796 | `0.7638888888888888` | 110/144 | 1.0444391263493646 |
| 2 | 7194 | `0.7708333333333334` | **111/144** | 1.053530157179921 |

`best_scores.json` 内容为 `{"count":144,"accuracy":0.7708333333333334,"benign_accuracy":0.7916666666666666,"injection_accuracy":0.7291666666666666,"loss":1.053530157179921}`，与 epoch 2 的 validation 完全一致，即"最佳"取最后一次验证。

### 2.4 数据量与排除记录

`preparation-audit.json`：`source_rows.train=76735`、`derived_rows.train=76729`（差 6）；`excluded_training_rows` 6 条，row_index 86/168/375 为 `normalized_exact_overlap_with_validation`，33340/38173/44553 为 `empty_or_invalid_prompt`。验证集 `source_sha256.valid.json` 与 `derived_sha256.valid.json` 相同（byte-identical），`audit.json` 的 `normalized_exact_overlap_count=0`、`schema_errors=[]`、`pass=true`、`test_files_opened=false`。

`config.json` 的 `train_sha256` / `valid_sha256` 与 `audit.json` 的 `train.sha256` / `valid.sha256` 逐字一致。

### 2.5 权重哈希

```
$ shasum -a 256 /Users/wjh/piguard-repro/runs/formal-v1/best_model.pth
3f284d8e2655ba9714ab2ab449645aa82f4953a1c7ec20cf62402dfb81af35ea  /Users/wjh/piguard-repro/runs/formal-v1/best_model.pth
$ echo $?
0
```

文件 `735,414,838` 字节（≈ 701 MiB），mtime `2026-11-10 12:44:15`，与 epoch 2 validation 时间一致。仅按字节计算哈希，未加载模型、未反序列化 state dict。

---

## 3. 记录层面的观察与差异（原样保留，交负责人裁决）

1. **`logs/model-weight-sha256.txt` 不是候选权重哈希。** 该文件内容为 `691d48a2800b926a19e3051def466fc2cca4f59a15e42ce4a0cf7f1b380b5e33  /Users/wjh/piguard-repro/models/deberta-v3-base/pytorch_model.bin`，指向的是**基础模型** DeBERTa-v3-base 的权重，与 Spec050 声明的 `best_model.pth` 哈希 `3f284d8e…` 是不同对象。Spec050 数值本身无差异；此处仅登记易混淆点，避免后续 Task08 取错哈希。

2. **`logs/formal-v1.log` 出现两次 `started_at`。** 第 1 行 `2026-11-09T19:00:50Z`、第 6 行 `2026-11-09T19:02:50Z`。`RUNLOG.md:17` 记载：首次尝试用 `nohup` 后执行环境在数据映射阶段清理了脱离会话的子进程，无 traceback、无训练事件/断点/退出码，产物保留在 `runs/formal-v1-launch-attempt-1/`；该尝试**未完成任何优化器更新，不计入训练**；随后改用受监控前台长会话。`events.jsonl` 只有 1 条 `started`（`resumed=false`）与 1 条 `finished`，与该说明一致。日志文本与事件流存在表述差异，按派工要求原样记录。

3. **样本数不在 `config.json`。** Task02 派工第 2 步把 `config.json` 与 `model-revision.txt`、`preparation-audit.json` 并列，但 `config.json` 只含 `epochs`、`batch_size`、`gradient_accumulation`、两个数据集哈希等，**不含训练/验证行数**。实测行数证据落在 `events.jsonl` 的 `started` 事件、`official-clean/audit.json` 与 `official-clean/preparation-audit.json` 的 `derived_rows`。派工路径描述与数据实际落点有差异，原样记录。

4. **`best_scores.json` 不写 `111/144`。** 文件里是 `accuracy: 0.7708333333333334`，需经 `× 144 = 111` 换算；前两次验证为 110/144。Spec050 的 "111/144" 是换算后的表述，非文件字面值。

---

## 4. 边界与未覆盖项

- 本记录仅覆盖 Task02 派工中「可先分派：本机复训证据核对」的 4 个步骤。Task02 的入口覆盖矩阵、授权与事件契约、M3 Max 加载冒烟、许可盘点、两次交付的 Go/No-Go 阻塞项**均仍待执行**。
- 执行授权边界、检测失败时敏感动作处置、上线阈值、最终评测口径由负责人定稿，本记录不作任何判定或建议性结论。
- 公开基准测试与产品端到端仍待执行；`test_files_opened=false`，未打开测试集文件；PINT 相关评测未授权，记 N/A。
- 权重、训练数据、完整断点保存在 Git 外；**本分支未上传任何模型产物**，本记录只含路径与数值。若后续在非本机环境核对，需提供这些文件的受控只读副本；其中哈希复算需 `best_model.pth` 本体（701 MiB）。
- 本记录不修改 Spec050 状态、Task02 状态、任何评审记录或变更日志。

---

## 5. 复核命令

```bash
cat  /Users/wjh/piguard-repro/logs/formal-v1.exit-code
tail -3 /Users/wjh/piguard-repro/runs/formal-v1/events.jsonl
cat  /Users/wjh/piguard-repro/runs/formal-v1/best_scores.json
cat  /Users/wjh/piguard-repro/runs/formal-v1/config.json
cat  /Users/wjh/piguard-repro/runs/official-clean/preparation-audit.json
cat  /Users/wjh/piguard-repro/logs/model-revision.txt
cat  /Users/wjh/piguard-repro/logs/upstream-commit.txt
shasum -a 256 /Users/wjh/piguard-repro/runs/formal-v1/best_model.pth
```
