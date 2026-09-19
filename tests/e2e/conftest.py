"""spec028–031 端到端测试固件：Playwright 真实浏览器。

约定：
- 浏览器由同步 API 管理，不依赖 pytest-playwright 插件。
- 服务地址默认 http://localhost:8000，可用环境变量 E2E_BASE_URL 覆盖。
- 仅当 RUN_E2E=1 时测试才运行（见 test_research_lifecycle_e2e.py 的 pytestmark）。
"""
import os

import pytest
from playwright.sync_api import sync_playwright, Browser

BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def browser() -> Browser:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(base_url=BASE_URL)
    page = context.new_page()
    yield page
    context.close()
