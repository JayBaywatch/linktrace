"""Regression tests for the review findings on the pluggable-fetcher branch:
truncated streamed bodies, swallowed flush failures, rate limits on retries,
session rebinding, partial fetcher startup, export fields and redirect-aware
broken-link marking."""

import asyncio
import time

import pytest
from aiohttp import web

from linktrace import (
    Crawler,
    FetchContext,
    Fetcher,
    FetchResult,
    FlushError,
    HttpFetcher,
    Serializers,
    Spider,
)

PAGE = '<html><head><title>P</title></head><body><a href="/x">x</a></body></html>'


async def _serve(app: web.Application) -> tuple[web.AppRunner, str]:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    return runner, f"http://127.0.0.1:{runner.addresses[0][1]}"


class TestStreamedBodyIsReadToEof:
    async def test_slow_chunked_body_under_limit_is_complete(self):
        """A body arriving in several network chunks must not be truncated."""

        async def handler(request: web.Request) -> web.StreamResponse:
            resp = web.StreamResponse(headers={"Content-Type": "text/html"})
            resp.enable_chunked_encoding()
            await resp.prepare(request)
            await resp.write(b"<html><body>")
            for i in range(5):
                await asyncio.sleep(0.02)  # force separate chunks on the wire
                await resp.write(f'<a href="/p{i}">{i}</a>'.encode())
            await resp.write(b"</body></html>")
            await resp.write_eof()
            return resp

        app = web.Application()
        app.router.add_get("/slow", handler)
        runner, base = await _serve(app)
        try:
            async with Crawler(
                respect_robots_txt=False, max_response_bytes=10_000
            ) as crawler:
                result = await crawler.fetcher.fetch(f"{base}/slow", {})
                doc = await crawler.crawl_document_async(f"{base}/slow")
        finally:
            await runner.cleanup()
        assert result.body.endswith("</body></html>")
        assert doc is not None
        assert [link.url for link in doc.internal_links] == [
            f"{base}/p{i}" for i in range(5)
        ]

    async def test_slow_chunked_body_over_limit_still_rejected(self):
        from linktrace import ResponseTooLarge

        async def handler(request: web.Request) -> web.StreamResponse:
            resp = web.StreamResponse(headers={"Content-Type": "text/html"})
            resp.enable_chunked_encoding()
            await resp.prepare(request)
            for _ in range(10):
                await asyncio.sleep(0.01)
                await resp.write(b"y" * 100)
            await resp.write_eof()
            return resp

        app = web.Application()
        app.router.add_get("/stream", handler)
        runner, base = await _serve(app)
        try:
            async with Crawler(
                respect_robots_txt=False, max_response_bytes=500
            ) as crawler:
                with pytest.raises(ResponseTooLarge):
                    await crawler.fetcher.fetch(f"{base}/stream", {})
        finally:
            await runner.cleanup()


class TestFlushFailuresAbortTheCrawl:
    async def test_write_error_raises_flush_error(self, local_site, tmp_path):
        base = await local_site({"/": PAGE, "/x": PAGE})
        spider = Spider(
            f"{base}/",
            max_depth=1,
            flush_to=str(tmp_path / "out.jsonl"),
            respect_robots_txt=False,
        )

        async def broken_write(_doc):
            raise OSError("No space left on device")

        spider._flush_document = broken_write  # type: ignore[method-assign]
        with pytest.raises(FlushError, match="No space left") as exc:
            await spider.run_async()
        assert isinstance(exc.value.__cause__, OSError)
        assert spider._flush_file is None  # closed by the finally block

    async def test_flush_error_is_exported(self):
        import linktrace

        assert "FlushError" in linktrace.__all__


class TestRateLimitAppliesToRetries:
    async def test_retry_waits_for_domain_delay(self, local_site):
        base = await local_site({"/flaky": (503, "busy")})
        async with Crawler(
            respect_robots_txt=False,
            request_delay=0.3,
            max_retries=2,
            backoff_factor=0.01,  # type: ignore[arg-type]
            backoff_jitter=False,
        ) as crawler:
            start = time.monotonic()
            doc = await crawler.crawl_document_async(f"{base}/flaky")
            elapsed = time.monotonic() - start
        assert doc is not None and doc.status_code == 503
        # Two attempts: the second must respect the 0.3s per-domain delay
        # even though the backoff alone would only have waited 0.01s.
        assert elapsed >= 0.3


class TestHttpFetcherSessionRebinding:
    async def test_fetcher_instance_survives_two_crawlers(self, local_site):
        base = await local_site({"/": PAGE})
        fetcher = HttpFetcher()
        async with Crawler(fetcher=fetcher, respect_robots_txt=False) as c1:
            assert (await c1.crawl_document_async(f"{base}/")) is not None
        async with Crawler(fetcher=fetcher, respect_robots_txt=False) as c2:
            doc = await c2.crawl_document_async(f"{base}/")
        assert doc is not None and doc.title == "P"

    async def test_spider_can_run_twice_with_same_fetcher(self, local_site):
        base = await local_site({"/": PAGE, "/x": PAGE})
        fetcher = HttpFetcher()
        spider = Spider(
            f"{base}/", max_depth=1, fetcher=fetcher, respect_robots_txt=False
        )
        first = len(await spider.run_async())
        assert first == 2
        # Reset crawl state and go again with the same (now re-opened) fetcher.
        spider.visited.clear()
        spider.in_progress.clear()
        spider.to_visit.append((f"{base}/", 0))
        second = await spider.run_async()
        assert len(second) > first  # documents accumulate; no "Session is closed"

    async def test_user_supplied_session_is_kept(self):
        import aiohttp

        session = aiohttp.ClientSession()
        try:
            fetcher = HttpFetcher(session=session)
            async with Crawler(fetcher=fetcher, respect_robots_txt=False):
                assert fetcher._session is session
            assert fetcher._session is session  # close() does not drop it
        finally:
            await session.close()


class TestPartialStartupIsCleanedUp:
    async def test_fetcher_closed_when_open_fails(self):
        class Exploding(Fetcher):
            name = "boom"

            def __init__(self) -> None:
                self.closed = False

            async def open(self, ctx: FetchContext) -> None:
                raise RuntimeError("no browser")

            async def close(self) -> None:
                self.closed = True

            async def fetch(self, url, headers):  # pragma: no cover
                raise AssertionError

        fetcher = Exploding()
        crawler = Crawler(fetcher=fetcher, respect_robots_txt=False)
        with pytest.raises(RuntimeError, match="no browser"):
            async with crawler:
                pass
        assert fetcher.closed
        assert crawler.session is None


class TestExportsCarryFinalUrl:
    def _doc(self):
        c = Crawler()
        doc = c.parse_document("https://x.test/a", PAGE, base_url="https://x.test/b")
        doc.final_url = "https://x.test/b"
        return doc

    def test_document_to_dict(self):
        data = Serializers.document_to_dict(self._doc())
        assert data["url"] == "https://x.test/a"
        assert data["final_url"] == "https://x.test/b"

    def test_flattened_rows(self):
        rows = Serializers([self._doc()])._flatten_documents()
        assert rows and all(r["final_url"] == "https://x.test/b" for r in rows)


class TestBrokenLinksViaRedirect:
    async def test_link_to_redirect_target_is_marked_broken(self):
        class Site(Fetcher):
            name = "http"

            async def fetch(self, url, headers):
                if url == "https://x.test/":
                    return FetchResult(
                        url,
                        200,
                        body='<a href="/a">a</a><a href="/b">b</a>',
                        fetcher="http",
                    )
                if url == "https://x.test/a":
                    # /a redirects to /b, which is gone.
                    return FetchResult(
                        url, 404, fetcher="http", final_url="https://x.test/b"
                    )
                return FetchResult(url, 200, body="", fetcher="http")

        # One URL at a time so /a's redirect marks /b visited before /b is
        # popped; /b's status is then only known through the redirect.
        spider = Spider(
            "https://x.test/",
            max_depth=1,
            fetcher=Site(),
            respect_robots_txt=False,
            max_concurrency=1,
        )
        docs = await spider.run_async()
        home = next(d for d in docs if d.url == "https://x.test/")
        broken = {b.url: b.status_code for b in home.broken_internal_links}
        assert broken == {"https://x.test/a": 404, "https://x.test/b": 404}

    async def test_direct_fetch_wins_over_redirect_status(self):
        class Site(Fetcher):
            name = "http"

            async def fetch(self, url, headers):
                if url == "https://x.test/":
                    return FetchResult(
                        url,
                        200,
                        body='<a href="/b">b</a><a href="/a">a</a>',
                        fetcher="http",
                    )
                if url == "https://x.test/a":
                    return FetchResult(
                        url, 500, fetcher="http", final_url="https://x.test/b"
                    )
                return FetchResult(url, 200, body="", fetcher="http")

        spider = Spider(
            "https://x.test/",
            max_depth=1,
            fetcher=Site(),
            respect_robots_txt=False,
            max_concurrency=1,
        )
        docs = await spider.run_async()
        home = next(d for d in docs if d.url == "https://x.test/")
        # /b was fetched directly (200) before /a's redirect reported 500 for it.
        assert {b.url for b in home.broken_internal_links} == {"https://x.test/a"}
