"""Browser contracts for the production chat composer layout."""

from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def _production_composer_markup() -> str:
    start = INDEX.index('<form class="composer" id="chat-form">')
    end = INDEX.index("</form>", start) + len("</form>")
    return INDEX[start:end]


def _load_production_composer(page, width: int) -> None:
    page.set_viewport_size({"width": width, "height": 900})
    page.set_content(
        f"""
        <!doctype html>
        <html lang="zh-CN">
          <head><meta charset="utf-8"><style>{STYLES}</style></head>
          <body>
            <section class="workspace has-started" aria-label="聊天窗口">
              <section class="chat-panel">
                <div class="messages" id="messages"></div>
                {_production_composer_markup()}
              </section>
            </section>
            <script>
              window.__submitCount = 0;
              document.querySelector('#chat-form').addEventListener('submit', (event) => {{
                event.preventDefault();
                window.__submitCount += 1;
              }});
            </script>
          </body>
        </html>
        """,
        wait_until="load",
    )


def test_composer_styles_keep_input_on_full_row_and_footer_on_wrapping_row() -> None:
    composer_start = STYLES.index(".composer {", STYLES.index("/* ===== 上下文占比"))
    composer_end = STYLES.index("}", composer_start)
    composer_rule = STYLES[composer_start : composer_end + 1]
    textarea_start = STYLES.index(".composer textarea {", composer_start)
    textarea_end = STYLES.index("}", textarea_start)
    textarea_rule = STYLES[textarea_start : textarea_end + 1]
    footer_start = STYLES.index(".composer-footer {", textarea_end)
    footer_end = STYLES.index("}", footer_start)
    footer_rule = STYLES[footer_start : footer_end + 1]

    assert "flex-direction: column" in composer_rule
    assert "align-items: stretch" in composer_rule
    assert "min-width: 0" in composer_rule
    assert "width: 100%" in textarea_rule
    assert "min-width: 0" in textarea_rule
    assert "width: 100%" in footer_rule
    assert "min-width: 0" in footer_rule
    assert 'href="/assets/styles.css?v=62"' in INDEX


def test_map_question_prefill_stays_editable_without_length_or_autosend_contract_changes() -> None:
    textarea_start = INDEX.index('<textarea id="question"')
    textarea_end = INDEX.index(">", textarea_start)
    textarea_tag = INDEX[textarea_start : textarea_end + 1]
    draft_start = APP.index("function applyConversationDraft")
    draft_end = APP.index("function openConversationFromWorkspace", draft_start)
    draft_block = APP[draft_start:draft_end]

    assert "maxlength" not in textarea_tag.lower()
    assert "input.value = draft" in draft_block
    assert "sendConversationMessage" not in draft_block


@pytest.mark.parametrize("width", [1440, 639, 375, 320])
def test_production_composer_keeps_controls_inside_viewport(width: int) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        _load_production_composer(page, width)

        textarea_box = page.locator("#question").bounding_box()
        composer_box = page.locator("#chat-form").bounding_box()
        assert textarea_box is not None
        assert composer_box is not None
        assert textarea_box["width"] >= composer_box["width"] * 0.9
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

        for selector in ("#context-meter", "#reasoning-effort-select", "#model-select", "#send-button"):
            box = page.locator(selector).bounding_box()
            assert box is not None, selector
            assert box["x"] >= 0, selector
            assert box["x"] + box["width"] <= width + 1, selector

        page.close()
        browser.close()


def test_long_production_draft_stays_intact_and_scrolls_at_cap_without_submit() -> None:
    from playwright.sync_api import sync_playwright

    draft = "DualGATs：" + ("关于本篇论文的研究问题、方法、主要结论和局限。" * 180)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 639, "height": 900})
        _load_production_composer(page, 639)
        page.locator("#question").fill(draft)
        metrics = page.locator("#question").evaluate(
            """(input) => {
              input.style.height = 'auto';
              input.style.height = `${Math.min(input.scrollHeight, 176)}px`;
              const style = window.getComputedStyle(input);
              return {
                value: input.value,
                clientHeight: input.clientHeight,
                scrollHeight: input.scrollHeight,
                renderedHeight: input.getBoundingClientRect().height,
                overflowY: style.overflowY,
              };
            }"""
        )

        assert metrics["value"] == draft
        assert len(metrics["value"]) == len(draft)
        assert metrics["renderedHeight"] <= 176
        assert metrics["scrollHeight"] > metrics["clientHeight"]
        assert metrics["overflowY"] == "auto"
        assert page.evaluate("window.__submitCount") == 0

        page.close()
        browser.close()
