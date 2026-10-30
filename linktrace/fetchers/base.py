"""The pluggable "get me the page" step of a crawl.

A :class:`Fetcher` turns a URL into a :class:`FetchResult` (status, headers,
body). Everything else the :class:`~linktrace.Crawler.Crawler` does around that
step (robots.txt, per-domain rate limiting, retries, caching, link parsing)
is transport-agnostic, so swapping the fetcher is the only change needed to
crawl sites that plain HTTP cannot handle, such as JavaScript-rendered SPAs.

Built-in fetchers:

- :class:`~linktrace.fetchers.http.HttpFetcher` (default) uses aiohttp.
- :class:`~linktrace.fetchers.browser.BrowserFetcher` renders pages in a
  headless browser via Playwright.
- :class:`~linktrace.fetchers.routing.RoutingFetcher` tries HTTP first and
  escalates to the browser only for pages that look like SPA shells.

Writing your own is a matter of subclassing :class:`Fetcher` and implementing
:meth:`Fetcher.fetch`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiohttp


@dataclass
class FetchResult:
    """What a fetcher hands back to the Crawler for one URL.

    Attributes:
        url: The URL that was requested.
        status: HTTP status code of the final response.
        headers: Response headers.
        body: Page body as text, or ``None`` when the status was not 200.
        fetcher: Name of the fetcher that produced the body (``"http"``,
            ``"browser"``, ...). Recorded on the resulting ``Document``.
    """

    url: str
    status: int
    headers: dict[str, str] = field(default_factory=dict)
    body: str | None = None
    fetcher: str = "http"


@dataclass
class FetchContext:
    """Crawler-owned resources and settings handed to a fetcher on ``open``.

    Attributes:
        session: The Crawler's shared aiohttp session (connection pool, cookie
            jar, SSL context). Fetchers that speak plain HTTP should use it.
        request_timeout: Per-request timeout in seconds.
        user_agent: User-Agent string the crawl identifies itself with.
        ssl_verify: The Crawler's SSL setting (``True``, ``False`` or a CA path).
    """

    session: aiohttp.ClientSession
    request_timeout: float = 30
    user_agent: str = "linktrace/0.1.0"
    ssl_verify: bool | str = True


class FetchError(Exception):
    """A fetch failed in a way that retrying will not fix."""


class TransientFetchError(FetchError):
    """A fetch failed in a way that may succeed on retry (timeout, reset).

    The Crawler retries these with exponential backoff up to ``max_retries``.
    """


class Fetcher(ABC):
    """Base class for fetchers.

    Subclasses implement :meth:`fetch`. :meth:`open` and :meth:`close` are
    called once per crawl by the Crawler's async context manager and default
    to no-ops; override them to acquire and release resources (a browser, a
    connection pool, ...).

    Attributes:
        name: Short identifier recorded on ``FetchResult.fetcher`` and used to
            namespace cache entries. The default HTTP fetcher is ``"http"``.
    """

    name: str = "custom"

    async def open(self, ctx: FetchContext) -> None:  # noqa: B027 - opt-in hook
        """Acquire resources. Called once when the Crawler is entered."""

    async def close(self) -> None:  # noqa: B027 - opt-in hook
        """Release resources. Called once when the Crawler is exited."""

    @abstractmethod
    async def fetch(self, url: str, headers: dict[str, str]) -> FetchResult:
        """Fetch ``url`` and return a :class:`FetchResult`.

        Args:
            url: Absolute URL to fetch.
            headers: Request headers the Crawler wants sent (at minimum
                ``User-Agent``).

        Raises:
            TransientFetchError: for failures worth retrying.
            FetchError: for failures that are not.
        """
