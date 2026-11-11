"""研究页「耗时」显示口径静态契约（TDD）。

背景：会话列表项没有 duration_ms，旧 duration 函数回退到
``(completed_at || updated_at) - (started_at || created_at)``，把会话整个
生命周期（计划/审批/等待）当成任务执行耗时，出现「耗时 172463 秒」。
本轮口径：duration_ms 优先 / 活跃态 now-start 实时计时 / 未开始显示 —，
并彻底删除会话 updated_at 墙钟兜底。

门禁精确切出两个 duration 函数体（不整文件误判），并用一段旧实现反例证明
检测器能识别回归、非恒真、实现被删除时会报错而非静默通过。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
RESEARCH = (FRONTEND / "research-tasks.js").read_text(encoding="utf-8")
SESSION_UI = (FRONTEND / "research-session-ui.js").read_text(encoding="utf-8")

# 旧实现（会话墙钟兜底）作为反例，用于证明下面的门禁确实会失败、不是恒真断言。
LEGACY_WALL_CLOCK_BODY = """
  function durationText(item) {
    const duration = Number(item?.duration_ms);
    if (Number.isFinite(duration) && duration > 0) return formatElapsed(duration);
    const start = Date.parse(item?.started_at || item?.created_at || '');
    const end = Date.parse(item?.completed_at || item?.updated_at || '');
    if (Number.isFinite(start) && Number.isFinite(end) && end > start) return formatElapsed(end - start);
    return '—';
  }
"""

# 会话墙钟兜底的特征串：updated_at 参与耗时计算即命中。
WALL_CLOCK_MARKERS = (
    "item?.updated_at",
    "completed_at || item?.updated_at",
)


def _function_body(source: str, signature: str, next_signature: str) -> str:
    """精确切出单个函数体；签名缺失/实现被删会抛异常，不静默通过。"""
    start = source.index(signature)
    end = source.index(next_signature, start + len(signature))
    body = source[start:end]
    assert len(body) > 40, f"{signature} 函数体切片过短，实现可能被删除"
    return body


def _duration_bodies():
    return {
        "research-tasks.js::sessionDurationText": _function_body(
            RESEARCH,
            "function sessionDurationText(item) {",
            "function sessionProgressText(item) {",
        ),
        "research-session-ui.js::durationText": _function_body(
            SESSION_UI,
            "function durationText(item) {",
            "function progressText(item) {",
        ),
    }


def _has_session_wall_clock_fallback(body: str) -> bool:
    return any(marker in body for marker in WALL_CLOCK_MARKERS)


def test_detector_is_not_vacuous():
    """诚实性：旧实现必须被检测器判为违规，证明门禁能抓回归、非恒真。"""
    assert _has_session_wall_clock_fallback(LEGACY_WALL_CLOCK_BODY)
    assert "Date.now()" not in LEGACY_WALL_CLOCK_BODY
    # 旧实现同样有 `—` 与 duration_ms，单纯断言「含 —」不构成门禁，
    # 因此本文件的门禁落在「不含 updated_at」+「Date.now() 实时计时」+「活跃态集合」上。
    assert "return '—'" in LEGACY_WALL_CLOCK_BODY
    assert "item?.duration_ms" in LEGACY_WALL_CLOCK_BODY


def test_two_duration_functions_drop_session_wall_clock_fallback():
    """彻底删除 updated_at 会话墙钟兜底：两处函数都不再引用 updated_at。"""
    for name, body in _duration_bodies().items():
        assert not _has_session_wall_clock_fallback(body), (
            f"{name} 仍含 updated_at 会话墙钟兜底"
        )
        assert "Date.parse(item?.completed_at || item?.updated_at" not in body


def test_duration_ms_wins_before_live_clock():
    """duration_ms 优先分支存在，且排在活跃态实时计时之前。"""
    for name, body in _duration_bodies().items():
        assert "item?.duration_ms" in body, f"{name} 需优先读取 duration_ms"
        assert "duration > 0" in body, f"{name} 需校验 duration_ms 为正"
        assert "Date.now()" in body, f"{name} 活跃态需 now-start 实时计时"
        assert body.index("item?.duration_ms") < body.index("Date.now()"), (
            f"{name} duration_ms 必须先于实时计时判定"
        )


def test_not_started_returns_em_dash_and_active_states_are_explicit():
    """未开始/无基准返回 —；活跃态按明确 status 集合判定，不再用会话创建时间兜底。"""
    for name, body in _duration_bodies().items():
        assert "return '—'" in body, f"{name} 未开始须返回 —"
        assert "item?.status" in body, f"{name} 需按 status 判定活跃态"
        for status in ("running", "waiting_retry", "paused"):
            assert status in body, f"{name} 活跃态集合需含 {status}"
        # 非活跃态不得拿会话 created_at 当墙钟起点：created_at 只允许出现在
        # 活跃态 now-start 分支内（与 Date.now() 同一条件块）。
        assert "Date.now()" in body


def test_formatter_output_format_unchanged():
    """两个格式化函数保持原有「X 秒」输出格式，本轮不改。"""
    assert "${label} 秒" in RESEARCH
    assert "${label} 秒" in SESSION_UI
