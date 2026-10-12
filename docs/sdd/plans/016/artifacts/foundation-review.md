# Task04 基础模块独立审查

- 评审者：protocol_review
- 角色：architect
- 模型：gpt-6-luna xhigh（任务要求）
- 范围：只读 scripts/sdd_tasks/documents.py、store.py、locks.py、atomic.py 与 docs/sdd/TASK-PROTOCOL.md
- 结论：基础层 **未通过**。发现两个 P1；其余发现需在相应实现/协议边界收敛后复核。本报告不代表 catalog、claim/recovery 生命周期或 Task04 整体通过。

## P1 — 旧数据库只校验列名，缺少约束结构校验

位置：store.py:122–147；协议要求见 TASK-PROTOCOL.md:190。

initialize() 对现有 v1 数据库只比较每张表的列名集合。它不核验主键、唯一约束、外键、NOT NULL、索引/索引列，也不检查既有行的外键或数据库完整性。只要 migration 表中查询到的版本集合是 {1}，一组列名吻合但约束缺失的“伪 v1”库就会被接受。后续代码不能再依赖 schema 声明保障并发与引用完整性。

**可复现例：**构造 SQLite 库，为 _REQUIRED_COLUMNS 中每张表按要求创建所有列但不声明任何 PK、UNIQUE 或 FK；schema_migrations.version 用 INTEGER，插入一行 version=1 并 commit。调用 initialize(conn) 会成功。随后对 leases 插入两行相同 task_id、不同 run_id 也会成功；对没有对应 tasks/runs 的外键值写入也会成功。

**必要修复：**现有库必须核验完整 schema shape：sqlite_master 中对象、table_info 的列名/类型/nullability/PK 顺序、foreign_key_list、index_list/index_info 的唯一性与列顺序；并执行 foreign_key_check 与合适的完整性检查。约束或数据不符时按不可信旧库拒绝，不能就地自动修复或降级接受。

## P1 — 数据库、维护锁和原子写入口会跟随 symlink

位置：store.py:91–104、locks.py:36–49、atomic.py:10–29、documents.py:165–170；协议要求路径 containment 与逐级 symlink 检查见 TASK-PROTOCOL.md:51。

这些入口没有把 symlink-safe containment 作为自身前置条件或强制校验：

- connect() 的 mkdir 和 SQLite open 会跟随 runtime 父目录 symlink，也会打开 task-ledger.sqlite3 symlink 指向的库；紧接着的 WAL pragma 会改写目标库。
- maintenance_lock() 的 mkdir 与 Path.open("a+b") 会跟随 common-dir 下的 sdd 或 ledger.lock symlink。锁可被重定向到仓库外，也可因路径被替换而让不同进程锁住不同 inode，失去公共互斥。
- atomic_write() 不接收授权 root，也不拒绝 symlink 父目录；若 path.parent 位于 symlink 目录下，临时文件和 os.replace 都会落到链接目标目录。
- parse_task() 对传入的 Markdown 路径直接 open()，没有拒绝 Task 文件 symlink；当前 API 也没有 repo root 参数来验证它。

**可复现例：**令 <common-dir>/sdd 指向 /tmp/external-sdd，调用 maintenance_lock(repo) 后实际打开 /tmp/external-sdd/ledger.lock。令 <main-root>/.sdd/runtime/task-ledger.sqlite3 为指向 /tmp/other.sqlite3 的 symlink，调用 connect() 会打开并配置目标库。令一个写入目录组件为 symlink，调用 atomic_write(linkdir/file, ...) 会在链接目标创建临时文件并替换目标。将某个 Task Markdown 路径替换成仓库外文件的 symlink，再调用 parse_task() 会读取链接目标。

**必要修复：**让这些边界都依赖同一可信 root，并在 open/replace 时拒绝路径组件与目标文件 symlink；对锁采用 dirfd 相对的 no-follow 打开并核对普通文件/inode，对 SQLite 检查数据库及父目录的授权根 containment，对原子写把 API 收紧为 root-relative 路径并避免校验到使用之间可换 symlink 的 TOCTOU。parse_task 要么接收/绑定可信 repo root，要么由强制调用约定保证传入的是已经验证的普通文件路径。

## P2 — Prompt parser 接受缺少 fenced block 和无禁止动作的 Prompt

位置：documents.py:66–80、documents.py:118–142；协议要求见 TASK-PROTOCOL.md:87–106。

当 Prompt 中完全没有 fenced block 时，_prompt_blocks() 返回 [prompt]，所以只要原始文本含七个标签，parser 就会当作合法分派 Prompt。Forbidden 只做非空检查，Forbidden: none 也会通过。这两种都不符合协议对 fenced text/prompt 块与明确禁止项的要求。

**可复现例：**合法 metadata 设置 validation_commands: []，prompt marker 内容直接写：

~~~text
Role: backend-dev
Read: none
Allowed paths: ["scripts/sdd_tasks"]
Forbidden: none
Validation: none
Result: 写完整结果 JSON 到 {{RESULT_PATH}}
Return schema: sdd-run-result/v1
~~~

_prompt_blocks() 走无 fence 分支，七标签和字段交叉检查均通过，parse_task_text() 接受该定义。

**必要修复：**无 fence 时拒绝；对 Forbidden 使用协议明确、可机械解析的最小语法（例如要求以 不得 / Do not / Never 开头并带动作文本），并用负例 fixture 固定行为。若产品希望允许自然语言任意写法，则需先收窄协议对“明确禁止动作”的机器校验承诺。

## P2 — 路径解析器与写入路径检查不一致

位置：documents.py:58–63 与 atomic.py:49–68。

_repo_path() 未拒绝 NUL，也只拒绝开头的 Windows drive 形式；例如 dir/file:stream 会被 parser 接受，但 contained() 会拒绝所有冒号，包含 NUL 的路径也会在 parser 通过后到后续 Path/OS 操作才失败。由此同一 Task 会被 parse 判为合法、到读写阶段才变成非结构化错误。

**可复现例：**在 metadata allowed_paths 与 Prompt Allowed paths 同时填 "dir/file:stream"，parser 的 _repo_path() 接受；之后 contained(root, "dir/file:stream") 抛 path_escape。同理 "dir\u0000file" 通过 _repo_path() 的当前字符检查，但 contained() 拒绝。

**必要修复：**集中到同一个 POSIX repo-relative validator，并让 parser 与文件 API 共享它；把所有会在实际读写阶段拒绝的字符/路径形态在 parse 阶段稳定拒绝。

## P2 — atomic_write() 在目录 fsync 错误时会抛错，但新内容已经替换

位置：atomic.py:17–38。

文件 fsync 成功后 os.replace() 发生在第 24 行；之后父目录打开或 fsync 若失败，函数仍抛 OSError，但目的路径在当前进程可见时通常已经是新内容。调用方从异常类型无法判断“原文件未变”还是“replace 已发生、目录项耐久性未确认”。这对 journal/Task 写入的重试和失败标记语义有影响。

**可复现例：**令 os.fsync 第一次调用正常、第二次（父目录）抛 OSError；atomic_write(path, "new") 抛异常，但 path.read_text() 返回 new。

**必要修复：**明确错误阶段语义：在 replace 前失败可视为未提交；replace 后目录 fsync 失败必须报告“状态不确定/已替换但耐久性未知”，调用方按 journal 的 expected hash 重读核对，禁止盲目回滚或按“未写入”覆盖。可用带 phase/replaced 字段的专用异常表达。

## P2 — connect() 在拒绝未知 schema 前先改 WAL 模式

位置：store.py:91–104；schema-version 停止要求见 TASK-PROTOCOL.md:190。

connect() 对任何可打开的已有库先运行 PRAGMA journal_mode=WAL，而 initialize() 的版本/shape 检查要由调用方稍后执行。未知版本最终会被拒绝，但拒绝前库可能已从 DELETE journal 切为 WAL 并生成 WAL/SHM 状态；这不是修复 schema，但它让“拒绝不可信旧库”带有先写后拒绝的副作用。connect() 也没有核实 pragma 实际返回是否为 wal。

**可复现例：**建一个 journal_mode=DELETE 的库、写入 schema_migrations.version=99，调用 connect(path)，再调用 initialize(conn) 得到 unknown_schema_version；重新打开库查询 PRAGMA journal_mode 可观察到连接阶段已做 WAL 切换。

**必要修复：**先只读/无副作用地检查既有库的版本与完整 shape，通过后再启用 WAL；新库可在 schema 创建事务中按既定顺序设置。检查 WAL pragma 的返回值，不满足协议时稳定失败。不要自动迁移或修复拒绝的旧库。

## 未覆盖范围

本次不评 catalog/rebuild、leases/claim、summary 重建、complete/recovery 或整体 Spec016；这些不应借本基础切片评审标记为通过。原子写与 symlink 问题修复后，仍需在独立测试中覆盖：伪 v1 schema、schema 外键坏行、目标 DB symlink、common-dir/sdd 与 ledger.lock symlink、原子写各阶段 I/O 故障、缺 fence 与 Forbidden: none。
