# -*- coding: utf-8 -*-
"""深度研究 Intake「逐轮引导式询问」前端静态契约（TDD / RED → GREEN）。

跨端契约：`intake-guided-questions-contract.md` 第 2.4 / 2.5 / 3 节。
守：
  1. `INTAKE_FIELD_LABELS` 补 4 个新 profile 字段，既有 SOURCE/CONFIRMATION 映射不破坏；
  2. 新增 `.conversation-intake-prompt` 区块的 DOM class ↔ `styles.css` 双向存在；
  3. 回答协议 4 种文本格式（2.5）经 `sendConversationMessage(text,{appendUser:true})` 发出，
     自定义输入 trim / 去控制字符 / 限长 400；
  4. `prompt=null` 隐藏区块，且 `:2126-2140` 的 `/plans/generate` 触发条件原样不动；
  5. active_conflict 三选项与 `INTAKE_CHOICE_LABELS` 既有逻辑不回归；
  6. 用户输入零 `innerHTML`；资源版本号已升、生效引用唯一；
  7. 执行级行为（渲染 / 点击发消息 / 协议文本）由 `test_intake_guided_questions_behavior.js`
     经 subprocess + node:vm 驱动。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")
HARNESS = Path(__file__).resolve().parent / "test_intake_guided_questions_behavior.js"

# 本批次升版后的生效版本（app.js 77 → 78；styles.css 保持 77，本轮未改样式）。
APP_JS_VERSION = 78
STYLES_VERSION = 77

# 新增 prompt 区块的 DOM class：必须在 app.js 真实渲染、在 styles.css 有选择器。
PROMPT_CLASSES = (
    "conversation-intake-prompt",
    "conversation-intake-prompt-head",
    "conversation-intake-prompt-progress",
    "conversation-intake-prompt-label",
    "conversation-intake-prompt-question",
    "conversation-intake-prompt-choices",
    "conversation-intake-prompt-choice",
    "conversation-intake-prompt-custom",
    "conversation-intake-prompt-custom-input",
    "conversation-intake-prompt-custom-submit",
    "conversation-intake-prompt-quick",
    "conversation-intake-prompt-quick-action",
    "is-recommended",
    "is-selected",
    "is-loading",
)


def _block(start_marker: str, end_marker: str) -> str:
    """返回 app.js 中从 start_marker 到 end_marker 的连续源码片段。"""
    start = APP.index(start_marker)
    end = APP.index(end_marker, start)
    return APP[start:end]


def _prompt_impl() -> str:
    """逐轮询问新增实现（纯函数 + renderIntakePrompt）连续块。"""
    return _block("const INTAKE_CUSTOM_MAX", "function createConversationIntake")


# ---- 1. 字段标签与既有映射 -------------------------------------------------
def test_four_new_intake_field_labels_are_present() -> None:
    for token in (
        "capability_profile: '能力配置'",
        "budget_profile: '预算配置'",
        "report_profile: '报告配置'",
        "degradation_policy: '降级策略'",
    ):
        assert token in APP, f"INTAKE_FIELD_LABELS 缺少 {token!r}"


def test_existing_source_and_confirmation_labels_are_not_broken() -> None:
    for token in (
        "user_explicit: '用户明确'",
        "context_inferred: '上下文推断'",
        "system_default: '系统默认'",
        "unconfirmed: '待确认'",
        "confirmed: '已确认'",
        "not_required: '无需确认'",
    ):
        assert token in APP, f"既有 LABELS 映射被破坏：{token!r}"


# ---- 2. DOM class ↔ CSS 双向契约 -------------------------------------------
def test_prompt_classes_are_rendered_by_js_and_defined_in_css() -> None:
    for name in PROMPT_CLASSES:
        assert f"'{name}'" in APP or f'"{name}"' in APP, f"app.js 未真实渲染 class {name!r}"
        assert f".{name}" in STYLES, f"styles.css 缺少 .{name} 选择器（DOM 契约双向存在）"


def test_prompt_container_is_created_in_create_conversation_intake() -> None:
    creator = _block("function createConversationIntake", "function updateConversationIntake")
    assert "className = 'conversation-intake-prompt'" in creator
    assert "promptBlock.hidden = true" in creator, "默认隐藏，等 SSE 帧带 prompt 才显示"
    assert "conversation-intake-prompt" in creator


def test_css_rules_are_scoped_to_the_intake_panel() -> None:
    """新增规则使用既有 `.conversation-intake-*` 同级作用域，不污染全局。"""
    for name in PROMPT_CLASSES[:12]:
        assert f".{name}" in STYLES
    # 推荐态/选中态/提交态都限定在 prompt 区块的按钮上，不是裸全局状态类。
    assert ".conversation-intake-prompt-choice.is-recommended" in STYLES
    assert ".conversation-intake-prompt-choice.is-selected" in STYLES
    assert ".conversation-intake-prompt-choice.is-loading" in STYLES


# ---- 3. 回答协议（契约 2.5，逐字） -----------------------------------------
def test_answer_protocol_literals_are_frozen() -> None:
    impl = _prompt_impl()
    for token in (
        "【研究参数】",
        "[intake:",
        "use_recommended",
        "use_all_recommended",
        "__all__",
        "全部采用推荐",
        "custom:",
        "（推荐）",
        "：用推荐",
    ):
        assert token in impl, f"回答协议字面量缺失：{token!r}"


def test_answer_helpers_are_pure_and_use_prompt_key() -> None:
    impl = _prompt_impl()
    for signature in (
        "function sanitizeIntakeCustom(",
        "function intakeAnswerText(",
        "function intakeChoiceAnswer(",
        "function intakeQuickAnswer(",
        "function intakeCustomAnswer(",
        "function renderIntakePrompt(",
    ):
        assert signature in impl, f"缺少 {signature}"
    assert "prompt.key" in impl, "协议 key 必须取 prompt.key（「都按推荐」固定 __all__）"
    assert "choice.id" in impl, "候选 value 必须取 choice.id"


def test_answers_go_through_the_existing_conversation_message_channel() -> None:
    updater = _block("function updateConversationIntake", "function collapseConversationIntake")
    assert "renderIntakePrompt(" in updater
    assert "sendConversationMessage(text, { appendUser: true })" in updater, (
        "点候选/快捷按钮/自定义输入都须复用 sendConversationMessage(text,{appendUser:true})"
    )
    assert "payload.quick_actions" in updater
    assert "payload.progress" in updater


def test_custom_text_is_trimmed_bounded_and_control_char_free() -> None:
    impl = _prompt_impl()
    sanitizer = _block("function sanitizeIntakeCustom(", "function intakeAnswerText(")
    assert "400" in sanitizer or "INTAKE_CUSTOM_MAX" in sanitizer, "自定义文本须限长 ≤400"
    assert "trim()" in sanitizer
    assert r"\u0000" in sanitizer, "须去掉换行与控制字符"
    assert r"\u007f" in sanitizer
    assert "[" in sanitizer and "]" in sanitizer, "方括号须清洗，避免破坏 [intake:...] 解析"
    assert "slice(0, INTAKE_CUSTOM_MAX)" in sanitizer


# ---- 4. prompt=null 与 /plans/generate 既有路径 ----------------------------
def test_plan_generation_is_gated_on_prompt_null_not_missing() -> None:
    """联调裁决 5.3：触发条件由 !missingNames.length 改为 !prompt。"""
    updater = _block("function updateConversationIntake", "function collapseConversationIntake")
    assert "payload.prompt" in updater
    assert "promptNode.hidden = true" in updater, "prompt=null 时隐藏整个区块（既有行为不变）"
    assert "renderIntakePrompt(promptNode" in updater
    trigger = (
        "if (status === 'intake' && !prompt && panel.dataset.researchSessionId\n"
        "      && !assistantMessage.querySelector('.conversation-research-plan')\n"
        "      && panel.dataset.planRequested !== 'true') {"
    )
    assert trigger in updater, "/plans/generate 须以 !prompt 为门槛，逐轮询问期间不得提前生成计划"
    assert "!missingNames.length && panel.dataset.researchSessionId" not in updater, "旧的 missing 门槛须移除"
    assert "/plans/generate" in updater
    # 老投影无 prompt 键 → 归一化为 null，历史回放仍按原行为触发（兼容不变）。
    assert "payload.prompt && typeof payload.prompt === 'object' ? payload.prompt : null" in updater


# ---- 4b. 联调裁决 5.3 / 5.4 / 5.5 -------------------------------------------
def test_intake_status_label_reports_guided_progress_when_prompt_present() -> None:
    """裁决 5.4：存在 prompt 时显示逐轮进度，不显示「参数已齐」。"""
    label_fn = _block("function intakeStatusLabel(", "function prepareNewResearchDraft(")
    assert "正在确认研究参数" in label_fn
    assert "prompt.index" in label_fn and "prompt.total" in label_fn, "进度取 prompt.index / prompt.total"
    updater = _block("function updateConversationIntake", "function collapseConversationIntake")
    assert "intakeStatusLabel(status, missingNames, " in updater, "调用处须把当前帧 prompt 传给状态文案"


def test_finalize_counts_visible_prompt_block_as_user_action() -> None:
    """裁决 5.4：逐轮询问期间面板不折叠、dataset.status 不改成 completed。"""
    finalizer = _block("function finalizeConversationIntake", "function setIntakeEditStatus(")
    assert ".conversation-intake-prompt:not([hidden])" in finalizer, "仅「可见」引导区块才算待用户操作"
    assert "hasPrompt" in finalizer and "needsUserAction" in finalizer
    for token in (
        "'clarification', 'active_conflict'", ".conversation-intake-missing:not([hidden])",
        ".conversation-intake-choice", "hasMissing", "hasChoices", "!needsUserAction",
    ):
        assert token in finalizer, f"finalizeConversationIntake 既有语义被破坏：{token!r}"


def test_sanitize_strips_semicolons_like_brackets() -> None:
    """裁决 5.5：半角分号与 [ / ] 同等剥离；协议文本格式本身不变。"""
    sanitizer = _block("function sanitizeIntakeCustom(", "function intakeAnswerText(")
    replace_lines = [ln for ln in sanitizer.splitlines() if ".replace(" in ln]
    assert any(";" in ln for ln in replace_lines), "半角分号须与 [ / ] 一起在 replace 清洗规则里剥离"
    assert "[" in sanitizer and "]" in sanitizer, "方括号清洗不得回归"
    impl = _prompt_impl()
    assert "return `【研究参数】${readable} [intake:${key}=${value}]`;" in impl, "协议文本格式本身不变"


# ---- 5. active_conflict 三选项不回归 ---------------------------------------
def test_active_conflict_choices_and_labels_are_untouched() -> None:
    for token in (
        "modify_current: '修改当前研究'",
        "cancel_then_new: '取消后新建'",
        "new_conversation: '在新会话研究'",
    ):
        assert token in APP, f"INTAKE_CHOICE_LABELS 被破坏：{token!r}"
    choices_seg = _block(
        "const choicesNode = panel.querySelector('.conversation-intake-choices')",
        "// A historical Intake projection",
    )
    assert "INTAKE_CHOICE_LABELS[choice?.id]" in choices_seg
    assert "button.dataset.intakeChoice = choice.id" in choices_seg
    assert "handleConversationIntakeChoice(assistantMessage, button, choice.id)" in choices_seg
    assert "className = 'secondary-button btn-outline conversation-intake-choice'" in choices_seg
    # 新区块不得触碰 .conversation-intake-choices 的 render/replaceChildren。
    assert ".conversation-intake-choices" not in _prompt_impl()


# ---- 6. XSS 与 CSS 作用域 --------------------------------------------------
def test_prompt_renderer_never_uses_inner_html() -> None:
    impl = _prompt_impl()
    assert "innerHTML" not in impl, "用户输入渲染一律 textContent / input.value"
    assert "insertAdjacentHTML" not in impl
    assert "document.write" not in impl
    assert "textContent" in impl
    updater = _block("function updateConversationIntake", "function collapseConversationIntake")
    assert "innerHTML" not in updater


def test_no_new_script_tag_is_introduced() -> None:
    assert INDEX.count("<script src=") == 10, "不得引入新 <script>（既有契约冻结）"


# ---- 7. 资源版本号 ---------------------------------------------------------
def test_asset_versions_are_bumped_and_live_refs_are_unique() -> None:
    assert f'href="/assets/styles.css?v={STYLES_VERSION}"' in INDEX
    assert f'src="/assets/app.js?v={APP_JS_VERSION}"' in INDEX
    live_css = re.findall(r'<link rel="stylesheet" href="/assets/styles\.css\?v=(\d+)"', INDEX)
    live_app = re.findall(r'<script src="/assets/app\.js\?v=(\d+)"', INDEX)
    assert live_css == [str(STYLES_VERSION)], f"生效 styles.css 版本唯一：{live_css}"
    assert live_app == [str(APP_JS_VERSION)], f"生效 app.js 版本唯一：{live_app}"
    # 历史兼容 marker 不动
    assert "styles.css?v=62" in INDEX and "app.js?v=31" in INDEX
    assert "research-tasks.js?v=28" in INDEX, "计划面板推荐候选（上一轮成果）资源不回归"


# ---- 8. 执行级行为探针 -----------------------------------------------------
def test_intake_guided_questions_behavior_harness_passes() -> None:
    node = shutil.which("node")
    if not node:
        import pytest
        pytest.skip("node executable not found on PATH")
    assert HARNESS.exists()
    env = dict(os.environ)
    env.setdefault("NODE_OPTIONS", "")
    result = subprocess.run(
        [node, str(HARNESS)], cwd=str(ROOT), capture_output=True, text=True, timeout=120, env=env,
    )
    assert result.returncode == 0, (
        "intake guided questions 行为探针失败：\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    assert "ok - intake guided questions contract" in result.stdout, result.stdout
