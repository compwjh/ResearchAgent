import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path('/Users/wjh/ResearchAgent')
BASE = 'http://127.0.0.1:8000'
raw = (ROOT / 'artifacts/spec044-sse-rag-success.txt').read_text()
sources_frame = None
for line in raw.splitlines():
    line = line.strip()
    if not line.startswith('data: '):
        continue
    try:
        obj = json.loads(line[6:])
    except ValueError:
        continue
    if obj.get('type') == 'sources':
        sources_frame = obj
        break
assert sources_frame, 'no sources frame'
sources = sources_frame['sources'][:2]

result = {'endpoint': BASE, 'source_count': len(sources),
          'source_sample': {k: sources[0].get(k) for k in ('document_id', 'chunk_id', 'chunk_index', 'file_name')}}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    console_errors = []
    page_errors = []
    page.on('console', lambda msg: console_errors.append(msg.text) if msg.type == 'error' else None)
    page.on('pageerror', lambda exc: page_errors.append(str(exc)))
    page.goto(BASE, wait_until='domcontentloaded', timeout=60000)
    page.wait_for_function("() => !!window.__kbInspectionController && !!window.ConversationResearch", timeout=60000)
    result['controller_ready'] = True
    result['locate_fn_ready'] = page.evaluate("() => typeof window.locateKnowledgeChunk === 'function'")

    setup = page.evaluate("""(sources) => {
      const container = document.createElement('div');
      container.className = 'conversation-sources';
      container.id = 'spec044-e2e-sources';
      document.body.appendChild(container);
      window.__spec044E2E = { calls: [] };
      const renderer = window.ConversationResearch.createSourceRenderer({
        document, container,
        onLocateChunk: (payload) => {
          window.__spec044E2E.calls.push({
            documentId: payload.documentId,
            chunkId: payload.chunkId,
            chunkIndex: payload.source ? payload.source.chunk_index : null,
          });
          return window.locateKnowledgeChunk(payload);
        },
      });
      renderer.render(sources);
      const link = container.querySelector('.conversation-source-link-row a');
      const button = container.querySelector('.conversation-source-button');
      const locate = container.querySelector('.conversation-source-locate-button');
      return {
        pdf_text: link ? link.textContent : null,
        pdf_target: link ? link.getAttribute('target') : null,
        pdf_rel: link ? link.getAttribute('rel') : null,
        pdf_href: link ? link.getAttribute('href') : null,
        expand_exists: !!button,
        locate_exists: !!locate,
        locate_text: locate ? locate.textContent : null,
      };
    }""", sources)
    result['render'] = setup

    page.click('#spec044-e2e-sources .conversation-source-button')
    page.click('#spec044-e2e-sources .conversation-source-locate-button')
    try:
        page.wait_for_function(
            "() => document.querySelectorAll('.kb-chunk-item[data-chunk-id]').length > 0",
            timeout=60000,
        )
        result['chunks_rendered'] = True
    except Exception as exc:
        result['chunks_rendered'] = False
        result['chunks_wait_error'] = str(exc)[:300]
    page.wait_for_timeout(1500)

    result['after_click'] = page.evaluate("""() => {
      const controller = window.__kbInspectionController;
      const tab = document.getElementById('kb-tab-inspection');
      const select = document.getElementById('kb-inspection-document');
      const nodes = Array.from(document.querySelectorAll('.kb-chunk-item[data-chunk-id]'));
      const current = nodes.filter((n) => n.getAttribute('aria-current') === 'true'
        || n.classList.contains('is-active') || n.classList.contains('is-selected'));
      const status = document.querySelector('.chat-state');
      return {
        tab_selected: tab ? tab.getAttribute('aria-selected') : null,
        doc_select_value: select ? select.value : null,
        doc_option_count: select ? select.options.length : 0,
        chunk_nodes: nodes.length,
        highlighted_count: current.length,
        highlighted_chunk_index: current.length ? current[0].getAttribute('data-chunk-index') : null,
        highlighted_chunk_id: current.length ? current[0].getAttribute('data-chunk-id') : null,
        pending_focus: controller && controller.state ? controller.state.pendingFocusChunkId : 'NO_CONTROLLER',
        locate_calls: window.__spec044E2E ? window.__spec044E2E.calls : [],
        chat_state: status ? status.textContent : null,
      };
    }""")
    result['console_errors'] = console_errors
    result['page_errors'] = page_errors
    browser.close()

out = ROOT / 'artifacts/spec044-b-domain-e2e.json'
out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(result, ensure_ascii=False, indent=2))
