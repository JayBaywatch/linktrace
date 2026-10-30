"""Tests for production guard rails: frontier, jitter, size limits, redirects,
cache pruning."""

import os
import time
from collections import deque
from unittest.mock import patch

import pytest
from aiohttp import web

from linktrace import (
    BrowserFetcher,
    Crawler,
    FetchContext,
    Fetcher,
    FetchResult,
    HttpFetcher,
    ResponseTooLarge,
    Spider,
)
from linktrace.cache import ResponseCache

PAGE = '<html><head><title>P</title></head><body><a href="/x">x</a></body></html>'


class TestFrontier:
    def test_to_visit_is_a_deque(self):
        spider = Spider("https://x.test/")
        assert isinstance(spider.to_visit, deque)
        assert list(spider.to_visit) == [("https://x.test/", 0)]

    async def test_bfs_and_dfs_order(self):
        order: dict[str, list[str]] = {"bfs": [], "dfs": []}

        class Recorder(Fetcher):
            name = "http"

            def __init__(self, bucket: list[str]) -> None:
                self.bucket = bucket

            async def fetch(self, url: str, headers: dict[str, str]) -> FetchResult:
                self.bucket.append(url)
                body = {
                    "https://x.test/": '<a href="/a">a</a><a href="/b">b</a>',
                    "https://x.test/a": '<a href="/a/1">a1</a>',
                    "https://x.test/b": '<a href="/b/1">b1</a>',
                }.get(url, "")
                return FetchResult(url, 200, body=body, fetcher="http")

        for strategy in ("bfs", "dfs"):
            spider = Spider(
                "https://x.test/",
                max_depth=3,
                max_concurrency=1,
                traversal_strategy=strategy,  # type: ignore[arg-type]
                fetcher=Recorder(order[strategy]),
                respect_robots_txt=False,
            )
            await spider.run_async()

        assert order["bfs"] == [
            "https://x.test/",
            "https://x.test/a",
            "https://x.test/b",
            "https://x.test/a/1",
            "https://x.test/b/1",
        ]
        # DFS pops the most recently discovered link first.
        assert order["dfs"][:3] == [
            "https://x.test/",
            "https://x.test/b",
            "https://x.test/b/1",
        ]


class TestBackoffJitter:
    def test_jittered_delay_within_equal_jitter_band(self):
        crawler = Crawler(backoff_factor=2)
        for attempt in range(4):
            base = 2**attempt * 2
            samples = {crawler._backoff_delay(attempt) for _ in range(200)}
            assert all(base / 2 <= s <= base for s in samples)
            assert len(samples) > 1, "jitter should vary"

    def test_jitter_can_be_disabled(self):
        crawler = Crawler(backoff_factor=2, backoff_jitter=False)
        assert [crawler._backoff_delay(a) for a in range(3)] == [2.0, 4.0, 8.0]

    async def test_sleep_receives_jittered_value(self):
        from linktrace import TransientFetchError

        class Flaky(Fetcher):
            name = "flaky"

            async def fetch(self, url, headers):
                raise TransientFetchError("nope")

        with patch("asyncio.sleep") as sleep:
            async with Crawler(
                fetcher=Flaky(), respect_robots_txt=False, max_retries=2
            ) as crawler:
                await crawler.crawl_document_async("https://x.test/")
        (delay,), _ = sleep.call_args
        assert 1.0 <= delay <= 2.0


class TestResponseSizeLimit:
    async def test_default_limit_propagates_to_fetcher(self):
        async with Crawler(respect_robots_txt=False) as crawler:
            assert isinstance(crawler.fetcher, HttpFetcher)
            assert crawler.fetcher._max_bytes == 10 * 1024 * 1024
        async with Crawler(respect_robots_txt=False, max_response_bytes=None) as c:
            assert c.fetcher._max_bytes is None

    async def test_fetcher_override_wins(self):
        fetcher = HttpFetcher(max_response_bytes=5)
        async with Crawler(fetcher=fetcher, respect_robots_txt=False):
            assert fetcher._max_bytes == 5

    async def test_content_length_over_limit_rejected_before_read(self, local_site):
        base = await local_site({"/big": "x" * 1000})
        async with Crawler(respect_robots_txt=False, max_response_bytes=100) as crawler:
            with pytest.raises(ResponseTooLarge) as exc:
                await crawler.fetcher.fetch(f"{base}/big", {})
        assert exc.value.size == 1000
        assert exc.value.limit == 100

    async def test_streamed_body_over_limit_rejected(self):
        """A chunked response without Content-Length is cut off at the limit."""

        async def handler(request: web.Request) -> web.StreamResponse:
            resp = web.StreamResponse(headers={"Content-Type": "text/html"})
            resp.enable_chunked_encoding()
            await resp.prepare(request)
            for _ in range(20):
                await resp.write(b"y" * 100)
            await resp.write_eof()
            return resp

        app = web.Application()
        app.router.add_get("/stream", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = runner.addresses[0][1]
        try:
            async with Crawler(
                respect_robots_txt=False, max_response_bytes=500
            ) as crawler:
                with pytest.raises(ResponseTooLarge):
                    await crawler.fetcher.fetch(f"http://127.0.0.1:{port}/stream", {})
        finally:
            await runner.cleanup()

    async def test_under_limit_is_fine_and_decoded(self, local_site):
        base = await local_site({"/": PAGE})
        async with Crawler(respect_robots_txt=False, max_response_bytes=10_000) as c:
            doc = await c.crawl_document_async(f"{base}/")
        assert doc is not None and doc.title == "P"

    async def test_too_large_is_not_retried_and_returns_none(self, local_site):
        base = await local_site({"/big": "x" * 1000})
        with patch("asyncio.sleep") as sleep:
            async with Crawler(
                respect_robots_txt=False, max_response_bytes=100, max_retries=3
            ) as crawler:
                doc = await crawler.crawl_document_async(f"{base}/big")
        assert doc is None
        assert sleep.call_count == 0

    async def test_browser_fetcher_honours_limit(self, local_site):
        pytest.importorskip("playwright")
        base = await local_site({"/": PAGE})
        try:
            async with Crawler(
                fetcher=BrowserFetcher(),
                respect_robots_txt=False,
                max_response_bytes=10,
                max_retries=1,
            ) as crawler:
                doc = await crawler.crawl_document_async(f"{base}/")
        except RuntimeError as e:  # Chromium not installed
            pytest.skip(str(e))
        assert doc is None


class TestRedirects:
    async def test_final_url_recorded_and_links_resolve_against_it(self, local_site):
        pages = {
            "/old": (302, ""),
            "/new/index": '<title>New</title><a href="sibling">s</a>',
        }
        base = await local_site(pages)

        # local_site serves a plain 302 without Location; build a real redirect.
        async def redirect(request: web.Request) -> web.Response:
            raise web.HTTPFound(location=f"{base}/new/index")

        app = web.Application()
        app.router.add_get("/old", redirect)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        rport = runner.addresses[0][1]
        try:
            async with Crawler(respect_robots_txt=False) as crawler:
                doc = await crawler.crawl_document_async(
                    f"http://127.0.0.1:{rport}/old"
                )
        finally:
            await runner.cleanup()

        assert doc is not None
        assert doc.url == f"http://127.0.0.1:{rport}/old"
        assert doc.final_url == f"{base}/new/index"
        assert doc.redirected
        assert doc.title == "New"
        # Relative link resolved against the served URL, not the requested one.
        assert [link.url for link in doc.links] == [f"{base}/new/sibling"]
        # ...and classified internal relative to the served host.
        assert doc.internal_links and not doc.external_links

    def test_not_redirected_by_default(self):
        doc = Crawler().parse_document("https://x.test/", PAGE)
        assert doc.final_url == "https://x.test/"
        assert not doc.redirected

    async def test_spider_marks_redirect_target_visited(self):
        class Redirecting(Fetcher):
            name = "http"

            def __init__(self) -> None:
                self.calls: list[str] = []

            async def fetch(self, url, headers):
                self.calls.append(url)
                if url == "https://x.test/":
                    return FetchResult(
                        url,
                        200,
                        body='<a href="/home">h</a><a href="/other">o</a>',
                        fetcher="http",
                        final_url="https://x.test/home",
                    )
                return FetchResult(url, 200, body="", fetcher="http")

        fetcher = Redirecting()
        spider = Spider(
            "https://x.test/", max_depth=2, fetcher=fetcher, respect_robots_txt=False
        )
        docs = await spider.run_async()
        # /home was served as the redirect target of "/", so it is not refetched.
        assert fetcher.calls == ["https://x.test/", "https://x.test/other"]
        assert "https://x.test/home" in spider.visited
        assert {d.url for d in docs} == {"https://x.test/", "https://x.test/other"}

    async def test_cache_round_trips_final_url(self, tmp_path):
        class Redirecting(Fetcher):
            name = "http"
            calls = 0

            async def fetch(self, url, headers):
                Redirecting.calls += 1
                return FetchResult(
                    url, 200, body=PAGE, fetcher="http", final_url="https://x.test/b"
                )

        for _ in range(2):
            async with Crawler(
                fetcher=Redirecting(), cache_dir=str(tmp_path), respect_robots_txt=False
            ) as crawler:
                doc = await crawler.crawl_document_async("https://x.test/a")
            assert doc is not None and doc.final_url == "https://x.test/b"
        assert Redirecting.calls == 1


class TestCachePrune:
    async def test_prune_removes_expired_entries(self, tmp_path):
        cache = ResponseCache(str(tmp_path), ttl_seconds=60)
        await cache.set("https://x.test/fresh", 200, {}, "f")
        await cache.set("https://x.test/stale", 200, {}, "s")
        stale = cache._cache_path("https://x.test/stale")
        old = time.time() - 120
        os.utime(stale, (old, old))

        removed = await cache.prune()
        assert removed == 1
        assert not stale.exists()
        assert await cache.get("https://x.test/fresh") is not None

    async def test_prune_enforces_max_bytes_oldest_first(self, tmp_path):
        cache = ResponseCache(str(tmp_path), ttl_seconds=3600, max_bytes=1)
        for i, url in enumerate(["https://x.test/1", "https://x.test/2"]):
            await cache.set(url, 200, {}, "body" * 50)
            path = cache._cache_path(url)
            os.utime(path, (time.time() - 100 + i, time.time() - 100 + i))

        removed = await cache.prune()
        assert removed == 2  # both exceed a 1-byte cap; oldest evicted first

        cache.max_bytes = None
        await cache.set("https://x.test/3", 200, {}, "x")
        assert await cache.prune() == 0

    async def test_crawler_prunes_on_enter(self, tmp_path):
        cache = ResponseCache(str(tmp_path), ttl_seconds=60)
        await cache.set("https://x.test/stale", 200, {}, "s")
        stale = cache._cache_path("https://x.test/stale")
        os.utime(stale, (time.time() - 120, time.time() - 120))

        async with Crawler(
            cache_dir=str(tmp_path), cache_ttl=60, respect_robots_txt=False
        ):
            pass
        assert not stale.exists()

    def test_cache_options_thread_through_spider(self):
        spider = Spider("https://x.test/", cache_ttl=5, cache_max_bytes=10)
        assert spider.cache_ttl == 5 and spider.cache_max_bytes == 10


class TestFetchContextDefaults:
    def test_context_carries_limit(self):
        ctx = FetchContext(session=None)  # type: ignore[arg-type]
        assert ctx.max_response_bytes == 10 * 1024 * 1024
