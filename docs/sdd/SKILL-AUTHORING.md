# Skill 编写边界与分层归属（Skill Authoring）

> 本文件是 `AGENTS.md` 的外链文档，**只在编写或修改 `.agents/skills/*/SKILL.md` 时按需加载**。
> `AGENTS.md` 只保留「唯一落点」分层表与本文链接。

## 背景

`.agents/skills/*/SKILL.md` 曾多次混入研发分派纪律、Git 禁止项、研发台账回填与**不存在的角色名**，
造成规则双份维护、相互漂移。本文件的用途**只是划边界**——这些规则的正确写法已存在于
`AGENTS.md` 与 `.codebuddy/agents/*.md`，**此处不重复其内容，只声明「不得写进 Skill」**。

## Skill 只写领域编排协议

`.agents/skills/*/SKILL.md` **只允许**描述「如何获取/处理本领域数据」，即：

- **适用范围**：本协议管哪类任务、哪些来源（如 USENIX / DBLP），何时被读取。
- **输入契约**：调用方要提供什么（如关键词、年份、会议标识）。
- **编排决策点**：LLM 在哪几个节点做判断（如选源、是否进入下一阶段）。
- **固定发现链 / 下载链**：领域内的既定步骤顺序与依赖。
- **领域边界**：本协议不碰什么（如搜索阶段不 GET 任何 PDF）。
- **停止条件**：何时收手、何时降级、失败后是否可重试。

## 禁止写入 Skill 的内容（四类）

以下内容**一律不得**出现在任何 SKILL.md 中，无论新旧：

1. **研发分派纪律**：每次最多几个代码文件 / 多少行、要求返回哪些字段、先回传什么后回传什么、
   进展日志路径与格式 —— 这些属门禁与流程规则，写在 `AGENTS.md`「门禁执行硬规则」及相关段落。
2. **研发台账回填**：Task 编号流转、`.sdd/runtime/task-ledger.sqlite3` 等**研发过程产物**的回填要求
   （该能力本身尚未落地，更不得提前写进 Skill）。
3. **Git 操作禁止项**：`reset` / `stash` / `clean` / 自动 `push` / 合并 `main` 等 —— 统一由
   `AGENTS.md` 的「Git 规范」规定，Skill 中不得复述。
4. **不存在的角色名，以及对 spec / plan 研发过程文档的引用**：Skill 是复用资产，跨 spec 存活；
   引用某个 spec 的 task 文档或某个不存在的角色名，会在该 spec 归档后立刻变成死链与错误指令。

## 唯一落点（分层归属，不得交叉）

| 规则类型 | 唯一落点 |
|---|---|
| 通用研发纪律（门禁、分派、提交、日志、任务拆分） | **`AGENTS.md`** |
| 角色特有的分派约束与文件边界 | **`.codebuddy/agents/<role>.md`** |
| 领域编排协议（上面「只写什么」的六项） | **`.agents/skills/*/SKILL.md`** |

- 新规则先问「它属于哪一层」，再写到该层的**唯一**位置；**禁止同一规则在两处各写一份**。
- 发现 Skill 里出现上述四类内容时，处置方式是**删除该段并指向其唯一落点**，不是搬运到别处再留一份。

## 引用角色名必须真实存在

- 现有角色**只有 10 个**（以 `.codebuddy/agents/*.md` 实际文件为准）：
  `architect`、`backend-dev`、`backend-reviewer`、`backend-tester`、`doc-updater`、
  `frontend-dev`、`frontend-reviewer`、`frontend-tester`、`planner`、`tester`。
- **本项目不存在 `junior-dev`**（其 agent 定义已不存在，纯后端用 `backend-dev`、纯前端用 `frontend-dev`）。
  任何文档与 Skill **均不得**引用该角色名；历史归档文本（`docs/sdd/plans/`、`reviews/` 等）按归档处理，
  不随本规则改写，但**新写内容一律禁止**。
