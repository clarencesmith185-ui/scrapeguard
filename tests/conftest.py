from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


@pytest.fixture(scope="session")
def browser():
    # These are real browser tests: a missing Chromium installation is a failure.
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    context = browser.new_context()
    page = context.new_page()
    page.set_default_timeout(2000)
    yield page
    context.close()


@pytest.fixture
def fixtures():
    return Path(__file__).parent / "fixtures"
