"""Bounded browser collection with optional Playwright dependencies."""

import logging
import time
from urllib.parse import urlencode

from .parser import parse_page

logger = logging.getLogger(__name__)


def scrape_keyword(
    keyword: str,
    *,
    stop_event=None,
    timeout_seconds=60,
    max_scrolls=8,
    deadline=None,
) -> tuple[list, bool]:
    try:
        from playwright.sync_api import sync_playwright
        from playwright_stealth import Stealth
    except ImportError as exc:
        raise RuntimeError(
            "Threads browser collection requires the 'threads' extra and "
            "Playwright Chromium (python -m playwright install chromium)."
        ) from exc

    deadline = min(deadline or float("inf"), time.monotonic() + timeout_seconds)
    blocked = False

    def stopped():
        return (
            stop_event is not None and stop_event.is_set()
        ) or time.monotonic() >= deadline

    def wait(page, milliseconds):
        remaining = max(0, int((deadline - time.monotonic()) * 1000))
        if remaining:
            page.wait_for_timeout(min(milliseconds, remaining))

    if stopped():
        return [], False
    with Stealth().use_sync(sync_playwright()) as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            timeout=max(1, int((deadline - time.monotonic()) * 1000)),
            args=["--disable-dev-shm-usage", "--no-sandbox"],
        )
        try:
            context = browser.new_context(
                locale="en-US", timezone_id="Australia/Melbourne"
            )
            page = context.new_page()
            page.set_default_timeout(5000)

            def handle_response(response):
                nonlocal blocked
                if response.status in {403, 429}:
                    blocked = True
                    if stop_event is not None:
                        stop_event.set()

            page.on("response", handle_response)
            try:
                page.goto(
                    "https://www.threads.net/search?"
                    + urlencode({"q": keyword, "serp_type": "default"}),
                    wait_until="domcontentloaded",
                    timeout=max(
                        1, min(30000, int((deadline - time.monotonic()) * 1000))
                    ),
                )
                wait(page, 4000)
                if (
                    blocked
                    or "login" in page.url.lower()
                    or "Instagram" in page.title()
                ):
                    return [], True
                previous_height = None
                stagnant = 0
                for _ in range(max_scrolls):
                    if stopped() or blocked:
                        break
                    page.mouse.wheel(delta_x=0, delta_y=1500)
                    wait(page, 3000)
                    height = page.evaluate("document.body.scrollHeight")
                    stagnant = stagnant + 1 if height == previous_height else 0
                    previous_height = height
                    if stagnant >= 2:
                        break
                if blocked:
                    return [], True
                return parse_page(page.content()), False
            except Exception:
                logger.exception(
                    "Threads page collection failed for %s", keyword
                )
                raise
        finally:
            browser.close()
