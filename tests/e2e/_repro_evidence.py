"""Spec034 Task12 真实服务证据脚本：驱动批准后流程，捕获网络请求作为证据。

仅用于本机复现（不影响既有 pytest 套件）。需先启动后端 uvicorn :8000。
复用 e2e 的 approve 流程，并通过 page.on('request') 记录所有请求，
重点统计新建 Task 的 /report 与 /events(SSE) 请求数量，以及时间线面板 hidden 状态。
"""
import sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"
REQUESTS = []


def _log_response(resp):
    u = resp.url
    if "/commands" in u:
        try:
            body = resp.json()
        except Exception:
            body = "<non-json>"
        print(f"[resp] {u} -> {body}")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(base_url=BASE)
        page = ctx.new_page()
        page.on("request", lambda r: REQUESTS.append(r.url))
        page.on("response", lambda r: _log_response(r))

        page.goto("/")
        page.click('a.nav-item[data-view="research"]')
        page.wait_for_selector("#research-view:not([hidden])", timeout=15000)

        page.fill("#research-goal", "LLM 安全对齐方向的综述调研（Task12 证据复现）")
        page.fill("#research-year-from", "2020")
        page.fill("#research-year-to", "2024")
        page.select_option("#research-quality", "balanced")
        page.fill("#research-target-count", "5")
        page.click("#research-create-button")

        # 创建前记录已有 task-id，用于识别「新建 Task」
        before_ids = page.eval_on_selector_all(
            "#research-task-list .research-task-card[data-task-id]:not([data-task-id=''])",
            "els => els.map(e => e.getAttribute('data-task-id'))",
        )

        # 等待会话打开（详情状态非空）
        page.wait_for_function(
            "() => { const el=document.querySelector('#research-detail-status');"
            "const s=el&&el.getAttribute('data-status');"
            "return s && s!=='' && s!=='未选择'; }",
            timeout=60000,
        )
        after_create_ids = page.eval_on_selector_all(
            "#research-task-list .research-task-card[data-task-id]:not([data-task-id=''])",
            "els => els.map(e => e.getAttribute('data-task-id'))",
        )
        print(f"[repro] task ids right after create: {after_create_ids}")

        # 等待计划生成完成
        page.wait_for_function(
            "() => { const s=document.querySelector('#research-detail-status')?.getAttribute('data-status');"
            "return s==='plan_pending_approval'||s==='running'||s==='partial'||s==='completed'||s==='failed'; }",
            timeout=300000,
        )
        status = page.get_attribute("#research-detail-status", "data-status") or ""
        print(f"[repro] status after plan gen: {status!r}")

        # 计划待审批则批准（等待按钮可见并点击；点击后必须离开 plan_pending_approval）
        if status == "plan_pending_approval":
            sel = "#research-session-approvals .send-button.research-session-command"
            try:
                page.wait_for_selector(sel, state="visible", timeout=30000)
                page.click(sel, timeout=30000)
            except Exception as e:
                print(f"[repro] playwright click failed ({e}); fallback to JS click")
                page.evaluate(
                    "const b=document.querySelector('#research-session-approvals .send-button.research-session-command'); if(b) b.click();"
                )
            try:
                page.wait_for_function(
                    "() => { const s=document.querySelector('#research-detail-status')?.getAttribute('data-status');"
                    "return s && s!=='plan_pending_approval'; }",
                    timeout=120000,
                )
            except Exception as e:
                print(f"[repro] approval did not leave plan_pending_approval: {e}")
            status = page.get_attribute("#research-detail-status", "data-status") or ""
            print(f"[repro] status after approval: {status!r}")

        # 等待新 Task 卡片出现（批准后才进入列表，且不在创建后初始列表里）
        page.wait_for_function(
            """(before) => {
                const cur = Array.from(document.querySelectorAll(
                    "#research-task-list .research-task-card[data-task-id]:not([data-task-id=''])"));
                return cur.some(e => !before.includes(e.getAttribute('data-task-id')));
            }""",
            arg=after_create_ids,
            timeout=120000,
        )
        new_tid = page.evaluate(
            """(before) => {
                const cur = Array.from(document.querySelectorAll(
                    "#research-task-list .research-task-card[data-task-id]:not([data-task-id=''])"));
                const f = cur.find(e => !before.includes(e.getAttribute('data-task-id')));
                return f ? f.getAttribute('data-task-id') : null;
            }""",
            after_create_ids,
        )
        print(f"[repro] new task id: {new_tid!r}")
        all_ids = page.eval_on_selector_all(
            "#research-task-list .research-task-card[data-task-id]:not([data-task-id=''])",
            "els => els.map(e => e.getAttribute('data-task-id'))",
        )
        print(f"[repro] ALL task ids after approval: {all_ids}")
        if new_tid:
            sel = f"#research-task-list .research-task-card[data-task-id='{new_tid}']"
            try:
                page.wait_for_selector(sel, state="visible", timeout=10000)
                page.click(sel, timeout=10000)
            except Exception as e:
                print(f"[repro] card click skipped ({e}); relying on auto-select after approval")

        # 等待时间线面板渲染（hidden=false）
        try:
            page.wait_for_function(
                "() => { const el=document.querySelector('#research-timeline-section');"
                "return !!el && !el.hasAttribute('hidden'); }",
                timeout=600000,
            )
            timeline_rendered = True
        except Exception:
            timeline_rendered = False
        hidden = page.evaluate(
            "() => { const el=document.querySelector('#research-timeline-section'); return el ? el.hasAttribute('hidden') : null; }"
        )
        print(f"[repro] timeline rendered={timeline_rendered} hidden={hidden}")

        # 统计新 Task 的请求
        prefix = f"/api/research-tasks/{new_tid}" if new_tid else None
        report_reqs = [u for u in REQUESTS if prefix and u.startswith(prefix + "/report")]
        events_reqs = [u for u in REQUESTS if prefix and u.startswith(prefix + "/events")]
        all_rt = sorted(set(u for u in REQUESTS if "/api/research-tasks/" in u))
        print("[repro] ALL /api/research-tasks/ requests:")
        for u in all_rt:
            print("   ", u)
        print(f"[repro] new task report requests: {len(report_reqs)} -> {report_reqs[:3]}")
        print(f"[repro] new task SSE /events requests (pipes): {len(events_reqs)} -> {events_reqs[:3]}")

        ok = timeline_rendered and len(events_reqs) >= 1 and len(report_reqs) >= 1 and len(events_reqs) == 1
        print(f"[repro] EVIDENCE_OK={ok} (timeline={timeline_rendered}, report={len(report_reqs)}, sse_pipes={len(events_reqs)})")
        browser.close()
        sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
