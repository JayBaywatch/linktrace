"""Plain HTTP fetcher built on aiohttp. This is the Crawler's default."""

from __future__ import annotations

import logging

import aiohttp

from linktrace.fetchers.base import (
    FetchContext,
    Fetcher,
    FetchError,
    FetchResult,
    ResponseTooLarge,
    TransientFetchError,
)

logger = logging.getLogger(__name__)

_INHERIT = object()  # sentinel: take max_response_bytes from the FetchContext


class HttpFetcher(Fetcher):
    """Fetch pages with the Crawler's shared aiohttp session.

    One GET per URL; the body is read only for 200 responses and never beyond
    ``FetchContext.max_response_bytes`` (a ``Content-Length`` above the limit
    is rejected before any body is read). Timeouts and connection errors are
    raised as :class:`~linktrace.fetchers.base.TransientFetchError` so the
    Crawler retries them with backoff. Redirects are followed by aiohttp; the
    served URL is reported as ``FetchResult.final_url`` and logged.

    Args:
        session: Optional session to use instead of the Crawler's. Mostly
            useful in tests; normally leave it ``None``.
        max_response_bytes: Override the Crawler's body limit for this fetcher
            (``None`` disables it). Left unset, the Crawler's value applies.
    """

    name = "http"

    def __init__(
        self,
        session: aiohttp.ClientSession | None = None,
        *,
        max_response_bytes: int | None | object = _INHERIT,
    ) -> None:
        self._session = session
        self._user_session = session is not None
        self._max_bytes_override = max_response_bytes
        self._max_bytes: int | None = (
            None if max_response_bytes is _INHERIT else max_response_bytes  # type: ignore[assignment]
        )

    async def open(self, ctx: FetchContext) -> None:
        # Always rebind to the Crawler's current session unless the caller
        # supplied one: a fetcher instance may be reused across crawls, and
        # the previous Crawler closed its session on exit.
        if not self._user_session:
            self._session = ctx.session
        if self._max_bytes_override is _INHERIT:
            self._max_bytes = ctx.max_response_bytes

    async def close(self) -> None:
        if not self._user_session:
            self._session = None

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
                final_url = str(response.url)
                if response.history:
                    chain = " -> ".join(str(r.url) for r in response.history)
                    logger.debug(f"Redirect: {chain} -> {final_url}")
                body = await self._read_body(url, response) if status == 200 else None
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
            final_url=final_url,
        )

    async def _read_body(self, url: str, response: aiohttp.ClientResponse) -> str:
        """Read the body as text without buffering more than the size limit."""
        limit = self._max_bytes
        if limit is None:
            return await response.text()

        declared = response.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > limit:
            raise ResponseTooLarge(url, limit, int(declared))

        # StreamReader.read(n) returns whatever is buffered, up to n bytes, so
        # a single call can hand back only the first network chunk. Keep
        # reading until EOF or until the body provably exceeds the limit.
        chunks: list[bytes] = []
        received = 0
        while received <= limit:
            chunk = await response.content.read(limit + 1 - received)
            if not chunk:
                break
            chunks.append(chunk)
            received += len(chunk)
        if received > limit:
            raise ResponseTooLarge(url, limit)
        raw = b"".join(chunks)

        try:
            encoding = response.get_encoding()
        except RuntimeError:
            encoding = "utf-8"
        return raw.decode(encoding, errors="replace")
