"""Standalone browser runner; the inspection API also accepts your own Page."""

from __future__ import annotations

from playwright.sync_api import Error, sync_playwright

from .config import Config
from .engine import inspect_page
from .models import Report, ScrapeGuardError, TargetResult
from .storage import Baseline


def run(config: Config, baseline: Baseline | None = None, *, headed: bool = False) -> Report:
    """Visit each target in a fresh context and return all results, including page failures."""
    if baseline is not None and baseline.fingerprint != config.fingerprint:
        raise ScrapeGuardError(
            "Config differs from baseline; review changes then baseline --force."
        )
    results = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not headed)
            try:
                for target in config.targets:
                    context = browser.new_context()
                    try:
                        page = context.new_page()
                        page.set_default_timeout(target.timeout_ms)
                        response = page.goto(
                            target.url, wait_until="domcontentloaded", timeout=target.timeout_ms
                        )
                        if response is not None and response.status >= 400:
                            results.append(
                                TargetResult(
                                    target.name,
                                    target.url,
                                    error=f"HTTP {response.status}; check URL/access.",
                                )
                            )
                            continue
                        if target.wait_for:
                            page.locator(f"css={target.wait_for}").first.wait_for(state="attached")
                        if target.settle_ms:
                            page.wait_for_timeout(target.settle_ms)
                        results.append(
                            inspect_page(
                                page, target, baseline.targets[target.name] if baseline else None
                            )
                        )
                    except Error as exc:
                        results.append(
                            TargetResult(
                                target.name,
                                target.url,
                                error=(
                                    f"Navigation/readiness failed: {exc}. "
                                    "Check URL and wait_for/timeout_ms."
                                ),
                            )
                        )
                    finally:
                        context.close()
            finally:
                browser.close()
    except Error as exc:
        raise ScrapeGuardError(
            f"Browser could not start or complete: {exc}\n"
            "Install Chromium with: python -m playwright install chromium"
        ) from exc
    return Report(results, "check" if baseline else "baseline")
