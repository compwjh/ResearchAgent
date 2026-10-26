"""Headless DOM/CSS regression for hidden memory-document panels."""

from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def _function_source(name: str, next_name: str) -> str:
    start = APP.index(f"function {name}")
    end = min(
        candidate
        for candidate in (
            APP.find(f"\nfunction {next_name}", start),
            APP.find(f"\nasync function {next_name}", start),
        )
        if candidate >= 0
    )
    return APP[start:end]


def _memory_visibility_runtime() -> str:
    functions = "\n".join(
        (
            _function_source("setMemoryDocumentRevision", "updateMemoryDocumentCount"),
            _function_source("updateMemoryDocumentCount", "clearMemoryDocumentConflict"),
            _function_source("memoryDocumentLabelFor", "memoryDocumentDraft"),
            _function_source("memoryDocumentDraft", "memoryDocumentCode"),
            _function_source("clearMemoryDocumentConflict", "showMemoryDocumentConflict"),
            _function_source("showMemoryDocumentConflict", "showMemoryDocumentServerCopy"),
            _function_source("showMemoryDocumentServerCopy", "refreshMemoryDocumentKeepingDraft"),
            _function_source("renderMemoryDocument", "memoryDocumentQuery"),
        )
    )
    return f"""
      const memoryDocumentEditor = document.querySelector('#memory-document-editor');
      const memoryDocumentRevision = document.querySelector('#memory-document-revision');
      const memoryDocumentConflict = document.querySelector('#memory-document-conflict');
      const memoryDocumentConflictCopy = document.querySelector('#memory-document-conflict-copy');
      const memoryDocumentCount = document.querySelector('#memory-document-count');
      const memoryDocumentEmpty = document.querySelector('#memory-document-empty');
      const memoryDocumentLabel = document.querySelector('#memory-document-label');
      const memoryDocumentSaveButton = document.querySelector('#memory-document-save-button');
      const memoryScopeSelect = document.querySelector('#memory-scope-select');
      const memoryProjectSelect = document.querySelector('#memory-project-select');
      const memoryState = {{
        scope: 'global', projectId: null, revision: '', content: '', loaded: false,
        loading: false, saving: false,
      }};
      const MEMORY_DOCUMENT_LIMIT = 65536;
      {functions}
      window.__memoryVisibility = {{
        render: renderMemoryDocument,
        showConflict: showMemoryDocumentConflict,
        clearConflict: clearMemoryDocumentConflict,
        setLoaded(value) {{ memoryState.loaded = value; renderMemoryDocument(); }},
        setSuccess() {{ clearMemoryDocumentConflict(); renderMemoryDocument(); }},
      }};
    """


def _load_memory_visibility_fixture(page) -> None:
    page.set_content(
        f"""
        <!doctype html>
        <html lang="zh-CN">
          <head><meta charset="utf-8"><style>{STYLES}</style></head>
          <body>
            <section id="memory-view">
              <section class="memory-document-panel" aria-label="记忆文档编辑器">
                <h2 id="memory-document-label">MEMORY.md</h2>
                <code id="memory-document-revision" data-revision="">尚未读取</code>
                <textarea id="memory-document-editor"></textarea>
                <span id="memory-document-count">0 / 65536</span>
                <p class="memory-document-empty" id="memory-document-empty" hidden>文档为空</p>
                <button id="memory-document-save-button" type="button">保存文档</button>
                <section id="memory-document-conflict" role="alert" hidden>
                  <strong>服务器已有新版本</strong>
                  <p>当前编辑草稿已保留。</p>
                  <pre id="memory-document-conflict-copy"></pre>
                </section>
              </section>
              <select id="memory-scope-select"><option value="global">全局</option></select>
              <select id="memory-project-select"></select>
            </section>
          </body>
        </html>
        """,
        wait_until="load",
    )
    page.add_script_tag(content=_memory_visibility_runtime())


def test_memory_document_hidden_panels_follow_dom_state_in_chromium() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _load_memory_visibility_fixture(page)

        initial = page.locator("#memory-document-conflict").evaluate(
            "node => ({ hidden: node.hidden, display: getComputedStyle(node).display })"
        )
        empty = page.locator("#memory-document-empty").evaluate(
            "node => ({ hidden: node.hidden, display: getComputedStyle(node).display })"
        )
        assert initial == {"hidden": True, "display": "none"}
        assert empty == {"hidden": True, "display": "none"}

        page.evaluate(
            """() => {
              window.__memoryVisibility.setLoaded(true);
              window.__memoryVisibility.showConflict({
                data: { detail: { current_content: 'server revision' } },
              });
            }"""
        )
        conflict = page.locator("#memory-document-conflict").evaluate(
            "node => ({ hidden: node.hidden, display: getComputedStyle(node).display, copy: node.querySelector('pre').textContent })"
        )
        assert conflict == {"hidden": False, "display": "grid", "copy": "server revision"}

        page.evaluate("window.__memoryVisibility.clearConflict()")
        cleared = page.locator("#memory-document-conflict").evaluate(
            "node => ({ hidden: node.hidden, display: getComputedStyle(node).display })"
        )
        assert cleared == {"hidden": True, "display": "none"}

        page.evaluate(
            """() => {
              window.__memoryVisibility.showConflict({ data: { detail: { current_content: 'server revision' } } });
              window.__memoryVisibility.setSuccess();
            }"""
        )
        after_success = page.locator("#memory-document-conflict").evaluate(
            "node => ({ hidden: node.hidden, display: getComputedStyle(node).display })"
        )
        assert after_success == {"hidden": True, "display": "none"}
        browser.close()
