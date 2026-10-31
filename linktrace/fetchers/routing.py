"""Route each URL to a fetcher: cheap HTTP by default, a browser when needed."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable

from linktrace.fetchers.base import FetchContext, Fetcher, FetchResult
from linktrace.fetchers.http import HttpFetcher

# "You need to enable JavaScript to run this app." and friends.
_NOSCRIPT_JS = re.compile(r"<noscript[^>]*>.*?javascript.*?</noscript>", re.I | re.S)
_ANCHOR = re.compile(r"<a\s[^>]*href\s*=", re.I)
_SCRIPT_SRC = re.compile(r"<script[^>]*\ssrc\s*=", re.I)
# An empty mount point: <div id="root"></div>, <div id="app"></div>, ...
_EMPTY_ROOT = re.compile(
    r"<(?:div|main|section)\s[^>]*id\s*=\s*[\"'](?:root|app|__next|___gatsby|"
    r"__nuxt|svelte|ember)[\"'][^>]*>\s*</(?:div|main|section)>",
    re.I,
)


def looks_like_spa_shell(result: FetchResult) -> bool:
    """Heuristic: does this HTTP response look like an un-rendered SPA shell?

    Returns ``True`` when the body is a successful (200) response that shows
    any of the classic signs of a client-rendered app:

    - a ``<noscript>`` block mentioning JavaScript,
    - an empty mount element such as ``<div id="root"></div>``,
    - no ``<a href>`` at all but at least one external ``<script src>``.

    Cheap regex checks only; no DOM parsing.
    """
    if result.status != 200 or not result.body:
        return False
    body = result.body
    if _NOSCRIPT_JS.search(body):
        return True
    if _EMPTY_ROOT.search(body):
        return True
    if not _ANCHOR.search(body) and _SCRIPT_SRC.search(body):
        return True
    return False


class RoutingFetcher(Fetcher):
    """Pick a fetcher per URL, with optional escalation after the fact.

    Every URL goes to ``default`` (plain HTTP unless told otherwise) except:

    - URLs matching any regex in ``render_patterns`` or for which
      ``route(url)`` returns ``True`` go straight to ``fallback``.
    - After a ``default`` fetch, if ``escalate(result)`` returns ``True`` the
      URL is fetched again with ``fallback`` and that result wins. The default
      predicate is :func:`looks_like_spa_shell`; pass ``None`` to disable.

    ``fallback`` is created lazily as a
    :class:`~linktrace.fetchers.browser.BrowserFetcher` if not supplied, so
    Playwright is only required when a URL actually reaches it.

    Args:
        default: Fetcher used first. Defaults to :class:`HttpFetcher`.
        fallback: Fetcher used for routed or escalated URLs. Defaults to
            ``BrowserFetcher()``.
        render_patterns: Regexes; matching URLs skip ``default`` entirely.
        route: Callable ``(url) -> bool``; ``True`` skips ``default``.
        escalate: Callable ``(FetchResult) -> bool`` evaluated on ``default``
            results. ``None`` disables escalation.
    """

    name = "routing"

    def __init__(
        self,
        default: Fetcher | None = None,
        fallback: Fetcher | None = None,
        *,
        render_patterns: Iterable[str] = (),
        route: Callable[[str], bool] | None = None,
        escalate: Callable[[FetchResult], bool] | None = looks_like_spa_shell,
    ) -> None:
        self.default: Fetcher = default if default is not None else HttpFetcher()
        if fallback is None:
            from linktrace.fetchers.browser import BrowserFetcher

            fallback = BrowserFetcher()
        self.fallback: Fetcher = fallback
        self._render_re = [re.compile(p) for p in render_patterns]
        self.route = route
        self.escalate = escalate
        self.escalations = 0

    async def open(self, ctx: FetchContext) -> None:
        await self.default.open(ctx)
        await self.fallback.open(ctx)

    async def close(self) -> None:
        await self.fallback.close()
        await self.default.close()

    def needs_render(self, url: str) -> bool:
        """True if ``url`` is routed directly to the fallback fetcher."""
        if any(r.search(url) for r in self._render_re):
            return True
        return bool(self.route and self.route(url))

    async def fetch(self, url: str, headers: dict[str, str]) -> FetchResult:
        if self.needs_render(url):
            return await self.fallback.fetch(url, headers)

        result = await self.default.fetch(url, headers)
        if self.escalate is not None and self.escalate(result):
            self.escalations += 1
            return await self.fallback.fetch(url, headers)
        return result
