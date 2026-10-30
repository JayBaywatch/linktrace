"""Headless-browser fetcher built on Playwright, for JavaScript-rendered sites.

Requires the optional ``browser`` extra::

    pip install "linktrace[browser]"
    playwright install chromium

Playwright is imported lazily inside :meth:`BrowserFetcher.open`, so importing
this module (or ``linktrace`` itself) never requires it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any, Literal

from linktrace.fetchers.base import (
    FetchContext,
    Fetcher,
    FetchError,
    FetchResult,
    ResponseTooLarge,
    TransientFetchError,
)

WaitUntil = Literal["commit", "domcontentloaded", "load", "networkidle"]

_INSTALL_HINT = (
    "BrowserFetcher requires Playwright. Install it with:\n"
    "    pip install 'linktrace[browser]'\n"
    "    playwright install chromium"
)


class BrowserFetcher(Fetcher):
    """Render each page in a headless browser and return the resulting DOM.

    One browser and one browser context are shared for the whole crawl; each
    fetch opens a fresh page (tab), navigates, waits for the page to settle,
    serialises ``document.documentElement.outerHTML`` and closes the tab.
    Concurrency is capped independently of the Spider's ``max_concurrency``
    because rendered pages are far more expensive than HTTP requests.

    Args:
        browser: Playwright browser type: ``"chromium"`` (default),
            ``"firefox"`` or ``"webkit"``.
        headless: Run without a visible window (default ``True``).
        wait_until: When to consider navigation finished. ``"networkidle"``
            (default) waits until no network requests for 500ms, which is the
            most reliable choice for SPAs. Use ``"domcontentloaded"`` plus
            ``wait_for_selector`` for sites with long-polling connections that
            never go idle.
        wait_for_selector: Optional CSS selector to wait for after navigation,
            e.g. ``"a[href]"`` or ``"#listings .card"``.
        settle_ms: Extra fixed delay after the waits above, for apps that
            render in a second pass. Default ``0``.
        max_pages: Maximum tabs open at once (default ``4``).
        timeout: Navigation timeout in seconds. Defaults to the Crawler's
            ``request_timeout``.
        block_resources: Playwright resource types to abort so pages render
            faster. Default blocks images, media and fonts. Pass an empty
            tuple to load everything.
        viewport: ``{"width": ..., "height": ...}`` for the browser context.
        launch_args: Extra command-line args for the browser binary.
        ignore_https_errors: Skip TLS verification. Defaults to ``True`` only
            when the Crawler was created with ``ssl_verify=False``.
    """

    name = "browser"

    def __init__(
        self,
        *,
        browser: Literal["chromium", "firefox", "webkit"] = "chromium",
        headless: bool = True,
        wait_until: WaitUntil = "networkidle",
        wait_for_selector: str | None = None,
        settle_ms: int = 0,
        max_pages: int = 4,
        timeout: float | None = None,
        block_resources: Iterable[str] = ("image", "media", "font"),
        viewport: dict[str, int] | None = None,
        launch_args: list[str] | None = None,
        ignore_https_errors: bool | None = None,
    ) -> None:
        if max_pages < 1:
            raise ValueError(f"max_pages must be >= 1, got {max_pages}.")
        self.browser_type = browser
        self.headless = headless
        self.wait_until: WaitUntil = wait_until
        self.wait_for_selector = wait_for_selector
        self.settle_ms = settle_ms
        self.max_pages = max_pages
        self.timeout = timeout
        self.block_resources = frozenset(block_resources)
        self.viewport = viewport
        self.launch_args = launch_args or []
        self.ignore_https_errors = ignore_https_errors

        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._semaphore: asyncio.Semaphore | None = None
        self._max_bytes: int | None = None
        self._timeout_ms: float = 30_000
        self._timeout_error: type[Exception] = Exception
        self._playwright_error: type[Exception] = Exception

    async def open(self, ctx: FetchContext) -> None:
        try:
            from playwright.async_api import Error as PlaywrightError
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
            from playwright.async_api import async_playwright
        except ImportError as e:  # pragma: no cover - exercised only w/o extra
            raise ImportError(_INSTALL_HINT) from e

        self._timeout_error = PlaywrightTimeoutError
        self._playwright_error = PlaywrightError
        self._timeout_ms = (self.timeout or ctx.request_timeout) * 1000
        self._max_bytes = ctx.max_response_bytes

        self._playwright = await async_playwright().start()
        launcher = getattr(self._playwright, self.browser_type)
        try:
            self._browser = await launcher.launch(
                headless=self.headless, args=self.launch_args
            )
        except PlaywrightError as e:
            await self._playwright.stop()
            self._playwright = None
            raise RuntimeError(
                f"Could not launch {self.browser_type}: {e}\n"
                f"Run 'playwright install {self.browser_type}' to download it."
            ) from e

        ignore_https = (
            self.ignore_https_errors
            if self.ignore_https_errors is not None
            else ctx.ssl_verify is False
        )
        context_kwargs: dict[str, Any] = {
            "user_agent": ctx.user_agent,
            "ignore_https_errors": ignore_https,
        }
        if self.viewport:
            context_kwargs["viewport"] = self.viewport
        self._context = await self._browser.new_context(**context_kwargs)

        if self.block_resources:
            blocked = self.block_resources

            async def _route(route: Any) -> None:
                if route.request.resource_type in blocked:
                    await route.abort()
                else:
                    await route.continue_()

            await self._context.route("**/*", _route)

        self._semaphore = asyncio.Semaphore(self.max_pages)

    async def close(self) -> None:
        for closer in (self._context, self._browser):
            if closer is not None:
                try:
                    await closer.close()
                except Exception:  # pragma: no cover - best-effort teardown
                    pass
        if self._playwright is not None:
            await self._playwright.stop()
        self._context = self._browser = self._playwright = None
        self._semaphore = None

    async def fetch(self, url: str, headers: dict[str, str]) -> FetchResult:
        if self._context is None or self._semaphore is None:
            raise RuntimeError(
                "BrowserFetcher is not open. Use it through "
                "'async with Crawler(...)' so open()/close() are called."
            )

        async with self._semaphore:
            page = await self._context.new_page()
            try:
                # User-Agent is fixed at context level; forward anything else.
                extra = {k: v for k, v in headers.items() if k.lower() != "user-agent"}
                if extra:
                    await page.set_extra_http_headers(extra)

                try:
                    response = await page.goto(
                        url, wait_until=self.wait_until, timeout=self._timeout_ms
                    )
                    if self.wait_for_selector:
                        await page.wait_for_selector(
                            self.wait_for_selector, timeout=self._timeout_ms
                        )
                    if self.settle_ms:
                        await page.wait_for_timeout(self.settle_ms)
                    body = await page.content()
                except self._timeout_error as e:
                    raise TransientFetchError(f"Browser timeout: {e}") from e
                except self._playwright_error as e:
                    raise FetchError(f"Browser error: {e}") from e

                # goto() returns None for same-document navigations; treat as OK.
                status = response.status if response is not None else 200
                response_headers = (
                    await response.all_headers() if response is not None else {}
                )
                final_url = page.url
            finally:
                await page.close()

        if self._max_bytes is not None and len(body) > self._max_bytes:
            raise ResponseTooLarge(url, self._max_bytes, len(body))

        return FetchResult(
            url=url,
            status=status,
            headers=dict(response_headers),
            body=body if status == 200 else None,
            fetcher=self.name,
            final_url=final_url,
        )
