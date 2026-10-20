# Spec018 同范围修复合同

2026-10-21 架构师依据用户授权与技术BLOCK意见补充；技术复审GO前不编码。不新增公开API/数据模型，不实现持久重建任务。

## 被动导航分类

- 不执行任何action、JavaScript、导航、附件加载或网络访问，只读取对象字典和页引用。
- Catalog的AA/AcroForm仍非空即拒绝。OpenAction仅接受：合法本文件页目标数组，或只含可选`Type=/Action`、`S=/GoTo`、`D`的动作字典；`Next`、文件字段、未知键和未知动作拒绝。保持其他对象的危险特征扫描，不能仅从正则移除OpenAction后跳过扫描。
- 本次白名单最小形状为`[真实本文件页引用 /Fit]`；可选支持其他已有明确数值形状的本地目标，但不得为通过本例放行字符串/named destination。页引用需匹配当前文档实际page xref，目标数组不能多元素或附加动作；缺页、错误xref、远程目标、格式异常均不放行。
- 允许至多4层间接引用，记录visited xref防循环；单对象读取后限制16KiB、目标数组最多8项。超限/循环/无法读取或解析采用既有`PDF_PROVENANCE_UNAVAILABLE`失败语义；已识别危险/未知active结构保持`HOSTILE_FEATURES_NOT_EXECUTED` partial。不能执行对象来确认安全。
- 所有非空OpenAction都必须被此resolver核验；其他位置的OpenAction、危险名称/编码变体/动作链不得因本次白名单绕过。普通URI链接仅被动保留，不能fetch。

## 单文档发布顺序与失败关闭

1. 保留既有indexing状态，读取不可变原件hash H；解析/切分/写向量完成后再次核对原件hash与canonical source hash均为H，变化则`SOURCE_HASH_MISMATCH`，本轮不发布verified成功。
2. 按实际payload构建manifest，保留真实ready/partial/failed及错误；写入成功前绝不把metadata写indexed。内部manifest发布helper返回真实manifest摘要，单文档协调器延后generation刷新至metadata提交后，不另造发布器。
3. 通过已有严格schema/原子写入口，在一次metadata写中更新该chunker状态及hash：ready→indexed，partial→indexed_partial且保留稳定错误，failed→failed；顶层兼容status/chunk_count继续只跟随v1。verified只证明H与实际索引字节一致，不把partial变ready；只接受既有受控hash字段，不开放任意patch。
4. 复用现有publication mutation lock串行化manifest/metadata/marker提交；网络embedding不持有该锁。metadata后刷新并`require_generation()`复核marker与live摘要一致，再检查本文件hash与manifest一致，全部通过才返回本轮终态。部分完成仍返回partial语义，不能假装ready。
5. manifest写失败：进入受控failed，不先发布indexed/本轮verified。metadata提交失败：停止，不刷新marker使未完成组合合法化；marker/live不匹配继续fail-closed。generation刷新/复核失败：不得返回成功，尝试通过严格入口将目标chunker记failed/`INDEX_FINALIZE_REQUIRED`；若连失败写入也失败，保留marker/live不一致的拒绝状态，记录固定错误，不直接改marker或回填假的ready。
6. 失败状态写入若成功，可用既有digest刷新机制发布真实failed状态；必须再次确认gate不能把本次结果当ready。无需全库回滚、删原件或重写向量框架。任一不可证明原子边界的中间态不得被全文ready读路径接受。

实现复审补充：`PDF_SOURCE_HASH_MISMATCH`与`SOURCE_HASH_MISMATCH`统一进入持久mismatch失败语义，不能只靠暂时的marker/live差异。其他文档随后合法刷新marker后，本文件仍必须被拒绝。允许Spec043既有全文读门禁做最小一致性适配：canonical的verified/indexed hash与source hash一致、目标chunker真实indexed，且原有manifest/generation条件全部通过；没有这些条件不以旧ready清单补位。该适配不新增公开接口，不放宽门禁。

## 必须的精准测试

- 真实构造PDF：本例间接GoTo页引用/Fit及裸数组为ready；JS/Launch/GoToR/SubmitForm/ImportData/form/embedded仍partial；Next动作链、未知键/目标、非本文件页、循环/过深/过大/畸形结构不能ready。断言解析过程无网络/执行动作，原hostile及普通URI回归不退化。
- 真实临时manifest/generation store：ready/partial映射、源hash一致、v2不覆盖v1顶层；manifest写失败、metadata原子写失败、generation刷新和复核失败、索引期间原件变化均做故障注入，断言无假成功且全文gate拒绝中间态。
- 定向领域测试后独立安全复审；GO后才通过现有单文档v1 API恢复GAT并重跑Spec043全文分析及问答。保留此前失败run，不以mock代替真实恢复。
