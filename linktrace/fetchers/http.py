"""Plain HTTP fetcher built on aiohttp. This is the Crawler's default."""

from __future__ import annotations

import aiohttp

from linktrace.fetchers.base import (
    FetchContext,
    Fetcher,
    FetchError,
    FetchResult,
    TransientFetchError,
)


class HttpFetcher(Fetcher):
    """Fetch pages with the Crawler's shared aiohttp session.

    This reproduces the crawler's original behaviour exactly: one GET per URL,
    body read only for 200 responses, timeouts and connection errors raised as
    :class:`~linktrace.fetchers.base.TransientFetchError` so the Crawler retries
    them with backoff.

    Args:
        session: Optional session to use instead of the Crawler's. Mostly
            useful in tests; normally leave it ``None``.
    """

    name = "http"

    def __init__(self, session: aiohttp.ClientSession | None = None) -> None:
        self._session = session

    async def open(self, ctx: FetchContext) -> None:
        if self._session is None:
            self._session = ctx.session

    async def fetch(self, url: str, headers: dict[str, str]) -> FetchResult:
        if self._session is None:
            raise RuntimeError(
                "HttpFetcher has no session. Use it through "
                "'async with Crawler(...)' or pass a session explicitly."
            )
        try:
            async with self._session.get(url, headers=headers) as response:
                status = response.status
                response_headers = dict(response.headers)
                body = await response.text() if status == 200 else None
        except (
            TimeoutError,
            aiohttp.ClientConnectorError,
            aiohttp.ServerTimeoutError,
        ) as e:
            raise TransientFetchError(f"{type(e).__name__}: {e}") from e
        except aiohttp.ClientError as e:
            raise FetchError(f"{type(e).__name__}: {e}") from e

        return FetchResult(
            url=url,
            status=status,
            headers=response_headers,
            body=body,
            fetcher=self.name,
        )
