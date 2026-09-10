# 复盘：Spec017 后端限界上下文模块化（2026-09-08）

## 一、结果

Task02–Task08 全部完成，Spec017 转 `已完成`。

| 指标 | 结果 |
|---|---|
| 迁移文件 | 40+ 个（KB 10、论文发现 19、文章/聊天 6、observability 6、chat graph 1） |
| 引用改写 | 约 130 个文件次 |
| 删除旧包 | `services` / `domain` / `graphs` / `observability` |
| 全量测试 | 631 passed / 0 failed（迁移前 628） |
| OpenAPI 契约 | 与 Task02 冻结基线逐项一致（36 操作，0 差异） |
| ruff | 122 条，与迁移前持平 |
| 运行时 | 服务启动，首页/健康/KB/论文接口均 200 |

## 二、四条可复用经验

### 1. 模块化迁移前必须做「全形态」依赖扫描

迁移 `services/kb/prompts.py` 时按 `from ...services.kb.X import` 扫了依赖，
结果漏掉 `from ...services.kb import prompts`（把子模块当属性导入），测试侧共 15 行。
迁完立刻 ImportError，全量测试收集阶段就挂。

**规则化**：扫依赖必须覆盖三种形态——
`services.kb.X import`、 `services.kb import X`、以及字符串形式的 patch 目标
（`patch("backend.app.services.kb.store.get_paper")`）。只扫第一种必然漏。

### 2. 架构测试比人工核对更早发现边界违规

我为一个「顺手」的迁移动作（`ollama.py` → `platform/`）加了边界断言后，
**当场**捕获 `platform/ollama.py` import `backend.app.graphs.chat` ——
platform 反向依赖业务模块，属静态边界规则禁止项。这个依赖在代码里躺了很久，
人工评审从没指出过。

**规则化**：边界规则必须落成可执行断言。文字承诺与人工评审都会漏，
AST 扫描不会。本次 5 条断言覆盖：api 无模块级单例、api 不直连 infrastructure、
platform 不 import 业务模块、业务模块不 import 其它上下文 domain/infrastructure、
旧路径零 import。

### 3. 兼容转发文件不能用 `import *`

迁移期为让未更新的引用方继续工作，在旧路径留转发文件。用 `from X import *`
会创建**独立的模块对象**，后果有二：`patch.object(旧路径, ...)` 失效（实测 3 个测试失败），
且 `旧模块 is 新模块` 为 False。改用 `sys.modules[__name__] = _real` 让旧路径
直接别名到真实模块，两个问题同时解决。

**规则化**：转发/兼容层必须保证「同一对象」，用 sys.modules 别名，不要用 star import。

### 4. patch 目标必须随代码一起迁移

`run_chat` 从 `platform.ollama` 下沉到 `chat.application.chat_runner` 后，
测试里 `patch("backend.app.platform.ollama.chat_direct_stream")` 失效。
同理，若在新模块里用 `from ... import create_chat_model`，既有
`patch("backend.app.platform.ollama.create_chat_model")` 也会失效——
from-import 在导入期绑定，mock 改的是原模块属性。

**规则化**：① 迁移代码时同步迁移 patch 目标；② 需要保留 patch 点的调用，
用**模块属性**访问（`_ollama.create_chat_model(...)`）而非 from-import。
后者失效的后果不是报错，而是**静默打到真实模型**。

## 三、流程问题：Task03/05 的清单与实现有偏差

Task02 冻结的迁移清单标注 `observability/`（6 文件）与 `ollama*.py` 归属 Task03，
但 Task03 收口时未迁，直到 Task06/07 才补齐。

**规则化**：任务收口时必须拿「清单里承接任务=本任务」的条目逐行核对，
不能只看自己记得的部分。清单是收口的检查表，不是背景材料。

## 四、代行留痕

本次 Task08（评审、部署、复盘）由主模型代行：用户 2026-09-08 明确要求
「子 agent 都让你代行（临时要求）」。代行事实已写入
`docs/sdd/reviews/017-acceptance-review.md` 文首与签字栏，避免与独立评审混淆。

## 五、遗留（不阻塞收口）

1. **Reranker 降级**：本地缺 `data/models/qwen3-reranker-0.6b-q8_0.gguf`，
   服务以 RRF 模式运行。属 spec-014 既定降级，非本次引入。
2. **跨域 port 未实现**：`platform/ports.py` 只定义契约，
   `PaperImportPort` 的实现属 spec-015 范围（其 Task15–17 尚未分派）。
3. **受控入口偏宽**：`knowledge_base/application.py` 目前导出面沿用旧 facade 的
   全部对外契约（约 40 个符号）。后续应在 Task04/06 稳定后逐步收窄为语义化操作。
