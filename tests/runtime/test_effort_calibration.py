#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spec 026 / Task 06 — B9 校准提示缺失（静默降档）真实浏览器验证。

用 Playwright（.venv）驱动真机 Chromium 复现并验证：
  S1 显式选 xhigh -> 切到只支持 off 的模型 -> 必须弹提示且文案正确、档位=off
  S2 档位本来就合法时切模型 -> 不弹提示
  S3 显式选 xhigh -> 切到支持 xhigh 的模型 -> 不弹提示、档位保持 xhigh（B11）
  S4 载入不被当前模型支持的会话档位（B10）-> 校准 + 提示
  S5 提示只出现一次（自动隐藏后触发不相关刷新，不再弹）
  回归 R1 发送后 assistant 卡片 ~100ms 内出现
  回归 R2 真实 409 卡片文案正确且不含“连接失败”
  回归 R3 unknown 模型显示“能力未确认 | 重新检测”，除 off 外全禁用

运行：.venv/bin/python tests/runtime/test_effort_calibration.py
注意：模型切换触发真实能力探测，最坏 25s/次，已给足超时。
"""
import json
import sys
import time

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
M = {
    "default": "qwen3.8:27b",       # 支持 off/medium/xhigh，默认 xhigh
    "only_off": "deepseek-coder-v2:16b",  # 仅 off
    "all": "qwen3.5:9b",            # 全五档，默认 xhigh
    "unknown": "deepseek-coder:33b",  # unknown
}
EXPECT_NOTICE = "已因模型能力从『极高』调整为『关闭』"

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}  {detail}")


def wait_initial(page):
    page.goto(BASE + "/")
    # 等待首个模型能力探测完成：选择器可用且落到默认档 xhigh（qwen3.8）
    page.wait_for_function(
        "() => { const s=document.querySelector('#reasoning-effort-select'); "
        "return s && !s.disabled && s.value==='xhigh'; }",
        timeout=60000,
    )


def wait_model_loaded(page):
    # 能力探测：先 disabled(loading) 再 enabled(done)
    try:
        page.wait_for_function(
            "() => { const s=document.querySelector('#reasoning-effort-select'); return s && s.disabled; }",
            timeout=8000,
        )
    except Exception:
        pass
    page.wait_for_function(
        "() => { const s=document.querySelector('#reasoning-effort-select'); return s && !s.disabled; }",
        timeout=60000,
    )


def switch_model(page, model):
    page.select_option("#model-select", model)
    wait_model_loaded(page)


def select_effort(page, value):
    page.select_option("#reasoning-effort-select", value)


def notice_text(page):
    return page.evaluate(
        "() => { const n=document.querySelector('#reasoning-effort-notice'); "
        "return n ? (n.hidden ? '' : (n.textContent||'').trim()) : ''; }"
    )


def wait_notice(page, timeout=15000):
    page.wait_for_function(
        "() => { const n=document.querySelector('#reasoning-effort-notice'); "
        "return n && !n.hidden && (n.textContent||'').trim().length>0; }",
        timeout=timeout,
    )


def select_value(page):
    return page.evaluate("() => document.querySelector('#reasoning-effort-select').value")


# ---------------- 场景 ----------------
def scenario1(page):
    wait_initial(page)
    select_effort(page, "xhigh")           # 用户显式选 xhigh
    switch_model(page, M["only_off"])       # 切到只支持 off
    try:
        wait_notice(page)
    except Exception:
        check("S1 提示出现", False, f"notice 为空: {notice_text(page)!r}")
        return
    txt = notice_text(page)
    val = select_value(page)
    check("S1 提示出现", True, f"text={txt!r}")
    check("S1 文案正确", txt == EXPECT_NOTICE, f"text={txt!r}")
    check("S1 档位=off", val == "off", f"value={val!r}")


def fetch_supported(model, refresh=True):
    """向真实后端要该模型的能力集。

    注意：能力探测结果**不是确定性的** —— 探测用 ``num_predict:1`` 加
    ``message.thinking`` 是否非空来判定支持，模型正在加载/切换时会整档超时，
    返回缺档的结果并被缓存 300s。所以断言必须**自适应**真实返回的集合，
    不能硬编码「某模型一定支持 medium」。该不确定性属 Spec 027 范围，不在 026。
    """
    import urllib.parse
    import urllib.request
    url = f"{BASE}/api/chat/reasoning-options?model={urllib.parse.quote(model)}"
    if refresh:
        url += "&refresh=1"
    with urllib.request.urlopen(url, timeout=120) as resp:
        return json.load(resp)


def scenario2(page):
    wait_initial(page)
    caps = fetch_supported(M["all"])
    supported = list(caps.get("supported_efforts") or [])
    default = caps.get("default_effort")
    # 选一个「在新模型支持集内、且不是新模型默认档」的档位，才能区分
    # 「原样保留」与「被默认值替换」两种结果。
    candidates = [e for e in supported if e != default]
    if not candidates:
        check("S2 前置", False, f"{M['all']} 支持集不足: supported={supported} default={default}")
        return
    target = "medium" if "medium" in candidates else candidates[-1]
    print(f"    (S2 实测能力 supported={supported} default={default} -> 选定 target={target})")

    # 模拟「用户显式选择」：目标档位在当前模型上可能是禁用项，
    # 因此用 JS 赋值 + 真实 change 事件（等价于用户操作）。
    page.evaluate(
        """(v) => { const s=document.querySelector('#reasoning-effort-select');
                    s.value=v; s.dispatchEvent(new Event('change',{bubbles:true})); }""",
        target,
    )
    time.sleep(0.5)
    switch_model(page, M["all"])
    time.sleep(0.8)
    txt = notice_text(page)
    val = select_value(page)
    check("S2 无提示(合法保持)", txt == "", f"notice={txt!r}")
    check(f"S2 档位={target}", val == target, f"value={val!r}")


def scenario3(page):
    wait_initial(page)
    select_effort(page, "xhigh")            # 显式 xhigh
    switch_model(page, M["all"])            # qwen3.5 支持 xhigh
    time.sleep(0.6)
    txt = notice_text(page)
    val = select_value(page)
    check("S3 无提示(B11 显式保持)", txt == "", f"notice={txt!r}")
    check("S3 档位=xhigh", val == "xhigh", f"value={val!r}")


def scenario4(page):
    # B10：载入一个“保存档位不被当前模型支持”的会话 -> 校准 + 提示。
    # 会话由“发送首条消息”隐式创建（POST /api/conversations 不被允许），且创建于支持 xhigh 的
    # qwen3.8 上，故其保存档位=后端默认 xhigh（合法，无需 PATCH——PATCH 会按会话模型校验并 409）。
    # 再用一个全新验证页（conversationState 为空）把当前模型切到仅支持 off 的 deepseek，然后载入
    # 该会话 -> 触发 B10 校准 + 提示。用全新页可保证 (模型,会话) 组合此前未被校准过，
    # 避免一次性提示守卫（correctedKeys）误判为“已提示”。
    wait_initial(page)  # qwen3.8，默认 xhigh
    page.fill("#question", "ping")
    page.click("#send-button")
    page.wait_for_selector(".message.assistant", state="attached", timeout=20000)
    page.wait_for_function("() => conversationState && conversationState.conversationId", timeout=30000)
    cid = page.evaluate("() => conversationState.conversationId")
    if not cid:
        check("S4 创建会话", False, "无 conversationId")
        return
    vpage = page.context.new_page()
    try:
        vpage.goto(BASE + "/")
        vpage.wait_for_function(
            "() => { const s=document.querySelector('#reasoning-effort-select'); "
            "return s && !s.disabled && s.value==='xhigh'; }",
            timeout=60000,
        )
        vpage.select_option("#model-select", M["only_off"])  # convId=null -> key 'deepseek|'
        wait_model_loaded(vpage)
        vpage.evaluate("(id) => window.openConversationFromWorkspace(id)", cid)
        try:
            wait_notice(vpage, timeout=30000)
        except Exception:
            check("S4 B10 提示出现", False, f"notice 为空: {notice_text(vpage)!r}")
            return
        txt = notice_text(vpage)
        val = select_value(vpage)
        check("S4 B10 提示出现", True, f"text={txt!r}")
        check("S4 B10 文案正确", txt == EXPECT_NOTICE, f"text={txt!r}")
        check("S4 B10 档位=off", val == "off", f"value={val!r}")
    finally:
        try:
            vpage.request.delete(BASE + f"/api/conversations/{cid}")
        except Exception:
            pass
        vpage.close()


def scenario5(page):
    wait_initial(page)
    select_effort(page, "xhigh")
    switch_model(page, M["only_off"])
    wait_notice(page)
    txt1 = notice_text(page)
    # 等自动隐藏（>4s）
    page.wait_for_function(
        "() => { const n=document.querySelector('#reasoning-effort-notice'); "
        "return !n || n.hidden || !(n.textContent||'').trim(); }",
        timeout=10000,
    )
    # 触发一次“不相关刷新”（重新检测能力）
    page.evaluate("() => loadReasoningOptions(activeModel, {refresh:true})")
    time.sleep(1.0)
    txt2 = notice_text(page)
    val = select_value(page)
    check("S5 首次提示出现", txt1 == EXPECT_NOTICE, f"text1={txt1!r}")
    check("S5 刷新后不再弹", txt2 == "", f"notice2={txt2!r}")
    check("S5 档位仍=off", val == "off", f"value={val!r}")


# ---------------- 回归 ----------------
def reg1(page):
    wait_initial(page)
    page.fill("#question", "用一句话介绍 Ollama。")
    start = time.time()
    page.click("#send-button")
    page.wait_for_selector(".message.assistant", state="attached", timeout=5000)
    dt = (time.time() - start) * 1000
    check("R1 assistant 卡片出现", True, f"{dt:.0f}ms")
    check("R1 出现<1000ms", dt < 1000, f"{dt:.0f}ms")


def reg2(page):
    wait_initial(page)
    switch_model(page, M["only_off"])  # deepseek 仅 off
    # 强制把选择器值设为 xhigh（绕过 disabled）以触发真实 409
    page.evaluate("() => { document.querySelector('#reasoning-effort-select').value='xhigh'; }")
    page.fill("#question", "hi")
    page.click("#send-button")
    page.wait_for_function(
        "() => { const msgs=[...document.querySelectorAll('.message.assistant')]; "
        "return msgs.some(m => (m.textContent||'').includes('推理档位')); }",
        timeout=20000,
    )
    txt = page.evaluate(
        "() => { const msgs=[...document.querySelectorAll('.message.assistant')]; "
        "const m=msgs.find(x => (x.textContent||'').includes('推理档位')); "
        "return m ? m.textContent.trim() : ''; }"
    )
    check("R2 409 文案正确", "该模型不支持『极高』推理档位，可选：关闭" in txt, f"text={txt!r}")
    check("R2 不含连接失败", "连接失败" not in txt, f"text={txt!r}")


def reg3(page):
    wait_initial(page)
    switch_model(page, M["unknown"])  # deepseek-coder:33b
    state_txt = page.evaluate(
        "() => { const s=document.querySelector('#reasoning-effort-state'); return s ? s.textContent.trim() : ''; }"
    )
    has_recheck = page.evaluate("() => !!document.querySelector('button.reasoning-effort-recheck')")
    off_disabled = page.evaluate(
        "() => { const o=document.querySelector('#reasoning-effort-select option[value=\"off\"]'); return o ? o.disabled : null; }"
    )
    xhigh_disabled = page.evaluate(
        "() => { const o=document.querySelector('#reasoning-effort-select option[value=\"xhigh\"]'); return o ? o.disabled : null; }"
    )
    val = select_value(page)
    check("R3 状态含能力未确认", "能力未确认" in state_txt, f"state={state_txt!r}")
    check("R3 有重新检测", bool(has_recheck), f"recheck={has_recheck}")
    check("R3 off 可用", off_disabled is False, f"off_disabled={off_disabled}")
    check("R3 xhigh 禁用", xhigh_disabled is True, f"xhigh_disabled={xhigh_disabled}")
    check("R3 档位=off", val == "off", f"value={val!r}")


def main():
    cases = [
        ("scenario1", scenario1),
        ("scenario2", scenario2),
        ("scenario3", scenario3),
        ("scenario4", scenario4),
        ("scenario5", scenario5),
        ("reg1", reg1),
        ("reg2", reg2),
        ("reg3", reg3),
    ]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        for name, fn in cases:
            page = context.new_page()
            try:
                fn(page)
            except Exception as e:
                check(name, False, f"EXCEPTION: {e!r}")
            finally:
                page.close()
        context.close()
        browser.close()

    print("\n=== SUMMARY ===")
    npass = sum(1 for _, c, _ in results if c)
    print(f"{npass}/{len(results)} checks passed")
    for n, c, d in results:
        if not c:
            print(f"  FAILED: {n}  {d}")
    if npass != len(results):
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
