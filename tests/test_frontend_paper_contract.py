"""Static contracts for the security paper discovery UI.

These checks intentionally avoid a browser dependency.  They protect the DOM
boundary between the paper renderer and its scoped stylesheet while keeping
paper metadata out of HTML string injection paths.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def test_paper_view_has_stable_render_targets() -> None:
    required_ids = {
        "papers-view",
        "paper-search-form",
        "paper-conference-list",
        "paper-results",
        "paper-results-toolbar",
        "paper-import-panel",
        "paper-import-items",
        "paper-login-queue",
        "paper-login-items",
        "paper-conference-dialog",
        "paper-search-progress",
        "paper-source-usenix",
        "paper-source-dblp",
        "paper-pagination",
        "paper-prev-page",
        "paper-next-page",
    }
    for element_id in required_ids:
        assert f'id="{element_id}"' in INDEX


def test_paper_content_renderer_uses_safe_dom_text_boundary() -> None:
    start = APP.index("function renderPaperResults")
    end = APP.index("function jumpToKnowledgeBase", start)
    results_renderer = APP[start:end]
    assert "innerHTML" not in results_renderer
    for field in ("paper-result-title", "paper-result-meta", "paper-result-abstract"):
        assert field in results_renderer
    assert "title.textContent" in results_renderer
    assert "meta.textContent" in results_renderer
    assert "abstract.textContent" in results_renderer

    batch_start = APP.index("function renderPaperBatch")
    batch_end = APP.index("async function paperLogin", batch_start)
    batch_renderer = APP[batch_start:batch_end]
    assert "innerHTML" not in batch_renderer
    assert "title.textContent" in batch_renderer
    assert "error.textContent" in batch_renderer


def test_async_search_uses_frozen_server_pagination_contract() -> None:
    assert "fetch('/api/papers/searches'" in APP
    assert "conference_ids: conferenceIds" in APP
    assert "body: JSON.stringify({ query, conference_ids: conferenceIds, years })" in APP
    assert "/api/papers/searches/${encodeURIComponent(searchId)}/results?page=" in APP
    assert "total_pages" in APP
    assert "has_next" in APP
    assert "generation" in APP
    assert "/api/papers/search'" not in APP
    assert "cached: '已使用缓存'" in APP
    assert "checking_cache: '正在检查本地目录'" in APP
    assert "fetching: '正在从该来源获取'" in APP
    assert "merging: '正在整理元数据'" in APP


def test_paper_error_text_covers_missing_codes_and_range_details() -> None:
    # 补齐的错误码映射必须出现在前端，避免回退到无信息量的固定兜底句。
    for code in (
        "UNSUPPORTED_CONFERENCE:",
        "SEARCH_NO_RESULTS:",
        "INVALID_PAGE:",
        "CATALOG_NOT_READY:",
        "CONFERENCE_NOT_FOUND:",
        "INVALID_ACCEPTED_YEAR:",
    ):
        assert code in APP
    # showPaperError 必须能消费后端下发的年份范围，渲染"仅支持 XXXX-XXXX"。
    assert "details.min_year" in APP
    assert "details.max_year" in APP


def test_paper_app_version_bumped() -> None:
    # 改动 app.js 后必须同步递增 ?v= 版本号，确保浏览器刷新缓存（回归护栏 A7）。
    assert "/assets/app.js?v=28" in INDEX
    assert "/assets/styles.css?v=28" in INDEX


def test_paper_import_status_resets_per_round() -> None:
    # P1-1/P1-2 回归：每次导入动作必须重置本轮累加器，且汇总只聚合本轮批次，
    # 避免同会话重复"添加到知识库"时成功数翻倍、旧批次污染汇总。
    import_start = APP.index("async function importPaperCandidates")
    import_end = APP.index("function paperBatchTerminal", import_start)
    import_fn = APP[import_start:import_end]

    # P1-1：directSuccess 必须在导入起始重置块内归零。
    assert "paperState.directSuccess = 0;" in import_fn
    # 本轮其余累加器同样在起始重置（skippedImports / failedGroups / lastImportError）。
    assert "paperState.skippedImports = skipped;" in import_fn

    # P1-2：必须记录本轮 batch_id 集合，供汇总过滤旧批次。
    assert "paperState.currentRoundBatchIds" in import_fn

    # renderImportSummary 必须按本轮集合过滤，而非聚合整个 batches Map。
    summary_start = APP.index("function renderImportSummary")
    summary_end = APP.index("async function changePaperPage", summary_start)
    summary_fn = APP[summary_start:summary_end]
    assert "paperState.currentRoundBatchIds" in summary_fn


def test_paper_submit_feedback_uses_pending_groups() -> None:
    # BUG-01：提交阶段文案必须取 pendingGroups（待提交分组数），不得依赖已创建批次数（旧口径恒为 0）。
    import_start = APP.index("async function importPaperCandidates")
    import_end = APP.index("function paperBatchTerminal", import_start)
    import_fn = APP[import_start:import_end]
    assert "paperState.pendingGroups = groups.size;" in import_fn

    summary_start = APP.index("function renderImportSummary")
    summary_end = APP.index("async function changePaperPage", summary_start)
    summary_fn = APP[summary_start:summary_end]
    assert "正在提交 ${paperState.pendingGroups}" in summary_fn
    assert "totalBatches + submitFailed" not in summary_fn


def test_paper_phase_computed_from_facts_not_self_guarded() -> None:
    # BUG-04：相位死锁修复——submitting 必须且仅由"确有未返回请求"(submitInflight>0) 决定，
    # 不再读取上一次 importPhase 参与判断；否则成功数为 0 时永远转不到 failed，状态栏永久停在"正在提交"。
    summary_start = APP.index("function renderImportSummary")
    summary_end = APP.index("async function changePaperPage", summary_start)
    summary_fn = APP[summary_start:summary_end]
    assert "if (paperState.submitInflight > 0)" in summary_fn
    assert "phase = 'submitting';" in summary_fn
    # 旧的自我守卫必须消失：用 importPhase 判断是否进入 failed。
    assert "paperState.importPhase !== 'submitting'" not in summary_fn
    # 成功数为 0、有失败项（或跳过）时必须落到 failed，不依赖上一次相位。
    assert "else if (totalFailed > 0 || skipped > 0)" in summary_fn
    assert "phase = 'failed';" in summary_fn
    # 部分成功仍保留。
    assert "else if (totalSuccess > 0 && totalFailed > 0)" in summary_fn


def test_paper_submit_window_shows_submitting_not_unfinished() -> None:
    # spec-021 task-05 P1 回归：进入提交循环、请求尚未返回期间（submitInflight > 0），
    # 状态栏必须显示"正在提交…"类文案，绝不可在初始窗口误显红色"导入未完成"。
    import_start = APP.index("async function importPaperCandidates")
    import_end = APP.index("function paperBatchTerminal", import_start)
    import_fn = APP[import_start:import_end]

    # 1) 已失效的乐观相位写入（先写相位、再被事实重算覆盖）必须消失。
    assert "setImportPhase('submitting')" not in import_fn
    assert "setImportPhase('failed')" not in import_fn

    # 2) 提交循环体内 submitInflight += 1 之后必须紧接一次 renderImportSummary()，
    #    确保"进入循环后、请求返回前"状态栏以事实重算为 submitting（而非 idle→导入未完成）。
    inc_idx = import_fn.index("paperState.submitInflight += 1;")
    dec_idx = import_fn.index("paperState.submitInflight -= 1;", inc_idx)
    assert "    renderImportSummary();" in import_fn[inc_idx:dec_idx], \
        "submitInflight 递增后必须立即 renderImportSummary 以刷新状态栏"

    # 3) 早期 return（groups.size===0）之后、提交 for 循环之前不得再渲染：
    #    旧代码在此处 submitInflight 仍为 0 时渲染出 phase='idle' → 红色"导入未完成"。
    gs_idx = import_fn.index("if (!groups.size) {")
    return_idx = import_fn.index("return;", gs_idx)
    loop_idx = import_fn.index("for (const [search_id", return_idx)
    between = import_fn[return_idx:loop_idx]
    assert "renderImportSummary" not in between, \
        "早期 return 与提交循环之间不得提前渲染（submitInflight 仍为 0 会误显导入未完成）"

    # 4) 状态机：submitInflight > 0 时相位必为 submitting，文案为"正在提交…"，
    #    且"导入未完成"只作为最低优先级 fallthrough（phase='idle' 之后），提交窗口不可达。
    summary_start = APP.index("function renderImportSummary")
    summary_end = APP.index("async function changePaperPage", summary_start)
    summary_fn = APP[summary_start:summary_end]
    assert "if (paperState.submitInflight > 0)" in summary_fn
    assert "phase = 'submitting';" in summary_fn
    assert "正在提交 ${paperState.pendingGroups} 个导入批次…" in summary_fn
    assert summary_fn.index("phase = 'idle';") < summary_fn.index("'导入未完成'")

    # 5) 轻量状态机模拟，证明提交窗口相位不是 idle/failed（'导入未完成' 文案来源）。
    def phase_for(submit_inflight, running_batches, total_success, total_failed, skipped):
        if submit_inflight > 0:
            return "submitting"
        if running_batches > 0:
            return "running"
        if total_success > 0 and total_failed > 0:
            return "partial_success"
        if total_success > 0:
            return "completed"
        if total_failed > 0 or skipped > 0:
            return "failed"
        return "idle"

    assert phase_for(1, 0, 0, 0, 0) == "submitting"
    assert phase_for(1, 0, 0, 0, 0) != "idle"


def test_paper_submit_inflight_counts_real_requests_only() -> None:
    # BUG-04：submitInflight 必须与实际发出的请求成对计数（请求前 +1，finally 中 -1），
    # 被 inFlightImports 去重 continue 掉的路径不得计数，否则计数漏减会重现死锁。
    import_start = APP.index("async function importPaperCandidates")
    import_end = APP.index("function paperBatchTerminal", import_start)
    import_fn = APP[import_start:import_end]
    assert "paperState.submitInflight += 1;" in import_fn
    assert "paperState.submitInflight -= 1;" in import_fn
    # 去重 continue 必须出现在计数递增之前，确保去重路径不计数。
    assert import_fn.index("if (paperState.inFlightImports.has(importKey)) continue;") < import_fn.index("paperState.submitInflight += 1;")


def test_paper_retry_shows_visible_progress_and_status() -> None:
    # BUG-04：重试必须全程可见——点击即登记 retryingBatchIds、状态栏给出"正在重试 N 项…"，
    # 卡片进行中态须覆盖"正在重试的批次"（即使是终态 failed），返回后清除登记。
    batch_start = APP.index("function renderPaperBatch")
    batch_end = APP.index("async function paperLogin", batch_start)
    batch_fn = APP[batch_start:batch_end]
    assert "paperState.retryingBatchIds.add(batchId);" in batch_fn
    assert "paperState.retryingBatchIds.delete(batchId);" in batch_fn
    # 进行中态公式：非终态 或 正在重试的批次。
    assert "!paperBatchTerminal(batch) || paperState.retryingBatchIds.has(batchId)" in batch_fn

    summary_start = APP.index("function renderImportSummary")
    summary_end = APP.index("async function changePaperPage", summary_start)
    summary_fn = APP[summary_start:summary_end]
    # 状态栏在重试期间给出"正在重试 N 项…"，不得出现"正在提交 0 个…"。
    assert "正在重试 ${paperState.retryingBatchIds.size}" in summary_fn


def test_paper_import_batch_progress_indicator() -> None:
    # 非终态批次卡片带进行中样式类，且 CSS 提供作用域内的动画规则（终态移除类即停止动画）。
    assert "is-progressing" in APP
    assert "#papers-view .paper-import-batch.is-progressing" in STYLES


def test_paper_status_text_covers_async_item_states() -> None:
    # spec-021：轮询可见的逐条状态文案必须齐全且与后端 ITEM_* 逐字对齐，避免 Unknown 漏出。
    for entry in (
        "queued: '排队中'",
        "downloading: '下载中'",
        "validating: '校验中'",
        "indexing: '建索引中'",
        "cancelled: '已取消'",
    ):
        assert entry in APP


def test_paper_error_text_covers_async_import_codes() -> None:
    # spec-021 Task03：新错误码必须映射为可行动文案，而非笼统的"导入批次失败"。
    assert "KB_STORAGE_LOCKED: '知识库存储被另一个实例占用，请关闭其他服务实例后重试'" in APP
    assert "DUPLICATE_IMPORT: '该论文已在导入批次中，请在原批次重试'" in APP


def test_paper_single_item_retry_button_present() -> None:
    # spec-021 Task04 步骤4：failed 条目除整批"重试失败项"外，追加单条"重试"按钮，
    # 调用新端点 /api/papers/import-items/{item_id}/retry，复用既有的 retryingBatchIds 机制。
    batch_start = APP.index("function renderPaperBatch")
    batch_end = APP.index("async function paperLogin", batch_start)
    batch_fn = APP[batch_start:batch_end]
    # 单条重试走新端点，路径拼接 item.item_id。
    assert "import-items/${encodeURIComponent(item.item_id)}/retry" in batch_fn
    # 每条 failed 条目带独立"重试"按钮（textContent 精确为'重试'，区别于整批'重试失败项'）。
    assert "textContent = '重试'" in batch_fn
    # 复用既有重试中集合：点击即登记、返回后清除（与整批重试同源机制）。
    assert "paperState.retryingBatchIds.add(batchId);" in batch_fn
    assert "paperState.retryingBatchIds.delete(batchId);" in batch_fn


def test_paper_batch_cancel_button_present() -> None:
    # spec-021 Task04 步骤5：批次级"取消"按钮仅当可取消态显示，调用既有 cancel 端点。
    batch_start = APP.index("function renderPaperBatch")
    batch_end = APP.index("async function paperLogin", batch_start)
    batch_fn = APP[batch_start:batch_end]
    assert "import-batches/${encodeURIComponent(batch.batch_id)}/cancel" in batch_fn
    assert "textContent = '取消'" in batch_fn
    # 仅 queued / waiting_login / failed 可取消（与后端 INVALID_STATE_TRANSITION 边界一致）。
    assert "['queued', 'waiting_login', 'failed']" in batch_fn


def test_paper_soft_import_hint_does_not_fail() -> None:
    # spec-021 Task04 步骤6：批次非终态且 updated_at 超阈值未变化时追加软提示，
    # 但不得谎报失败（不改 importPhase 判定）。
    assert "（仍在导入，可离开此页）" in APP
    # 软提示阈值常量（3 分钟）。
    assert "SLOW_IMPORT_MS" in APP
    summary_start = APP.index("function renderImportSummary")
    summary_end = APP.index("async function changePaperPage", summary_start)
    summary_fn = APP[summary_start:summary_end]
    # 软提示追加到 message，而非 importPhase 判定。
    assert "message += '（仍在导入，可离开此页）'" in summary_fn


def test_paper_direct_success_does_not_auto_jump() -> None:
    # BUG-03：单篇直达导入成功（后端返回 paper_id 而非 batch_id）后不得自动跳转知识库。
    # 自动跳转会执行 showView('kb') 隐藏 #papers-view，导致导入进度面板与论文信息一起消失；
    # 跳转只能由用户点击"在知识库中查看"触发。
    import_start = APP.index("async function importPaperCandidates")
    import_end = APP.index("function paperBatchTerminal", import_start)
    import_fn = APP[import_start:import_end]
    # 旧的自动跳转写法必须消失。
    assert "if (data.paper_id) jumpToKnowledgeBase(data.paper_id);" not in import_fn
    # 导入主流程内不得再出现任何跳转调用点（只允许存在于点击回调中）。
    assert "jumpToKnowledgeBase(" not in import_fn


def test_paper_direct_imports_rendered_in_panel() -> None:
    # BUG-03：直达成功论文必须进入"导入进度"面板展示——
    # 此前该分支只做 directSuccess += 1，从不调用任何渲染函数，面板里只剩计数、没有论文。
    assert "directImports" in APP
    assert "renderDirectImports" in APP
    direct_start = APP.index("function renderDirectImports")
    direct_end = APP.index("function selectPaperConference", direct_start)
    direct_fn = APP[direct_start:direct_end]
    # 该路径本就没有批次，标题固定为"直接导入"，不得伪造 batch_id。
    assert "直接导入" in direct_fn
    assert "batch_id" not in direct_fn
    # 必须提供点击式跳转入口（唯一的跳转触发点）。
    assert "在知识库中查看" in direct_fn
    assert "jumpToKnowledgeBase(item.paper_id)" in direct_fn
    # 只用 textContent / DOM API，禁止 innerHTML 拼接。
    assert "innerHTML" not in direct_fn


def test_paper_error_notice_and_status_states_have_css() -> None:
    # 错误提示升级为告警条，且整体状态语义色 class 必有对应 CSS 规则（regression-guard）。
    assert "#papers-view .paper-error" in STYLES
    assert "border-left: 3px solid #b42318" in STYLES
    for kind in ("running", "completed", "partial", "failed"):
        assert f"#papers-view .paper-status.is-{kind}" in STYLES


def test_paper_source_initial_placeholder_is_neutral() -> None:
    # 来源初始占位不再使用"等待开始"，改为中性"未开始"（避免与进度状态混淆）。
    assert "等待开始" not in INDEX
    assert "未开始" in INDEX


def test_paper_styles_cover_long_content_scrolling_and_focus() -> None:
    selectors = (
        "#papers-view .paper-search-form",
        "#papers-view .paper-conference-list",
        "#papers-view .paper-results",
        "#papers-view .paper-result-title",
        "#papers-view .paper-result-meta",
        "#papers-view .paper-import-items",
        "#papers-view .paper-login-queue",
        ".paper-conference-dialog",
        ".paper-conference-dialog .paper-managed-conferences",
        "#papers-view :is(button, input, textarea, select, [tabindex]):focus-visible",
    )
    for selector in selectors:
        assert selector in STYLES

    assert "overflow-wrap: anywhere" in STYLES
    assert "overflow-y: auto" in STYLES
    assert "@media (max-width: 760px)" in STYLES
    assert "@media (max-width: 430px)" in STYLES


def test_kb_upload_surfaces_stable_backend_error_code_and_message() -> None:
    upload_start = APP.index("function kbUploadErrorMessage")
    upload_end = APP.index("function appendKbMessage", upload_start)
    upload_handler = APP[upload_start:upload_end]
    assert "if (message && code) return `${message}（${code}）`;" in upload_handler
    assert "data.message" in upload_handler
    assert "data.error_code" in upload_handler
    assert "const error = new Error(kbUploadErrorMessage(data));" in upload_handler
    assert "error.code = data?.error_code || '';" in upload_handler
    assert "try { data = await response.json(); } catch (_) {}" in upload_handler
    assert "上传失败：${error.message}" in upload_handler
    assert "data.file_name}：${KB_STATUS_TEXT[data.status] || data.status}" in upload_handler
