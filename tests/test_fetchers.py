"""Tests for the pluggable fetcher layer (HTTP, routing, custom fetchers)."""

from unittest.mock import patch

import pytest

from linktrace import (
    Crawler,
    FetchContext,
    Fetcher,
    FetchError,
    FetchResult,
    HttpFetcher,
    RoutingFetcher,
    Spider,
    TransientFetchError,
    looks_like_spa_shell,
)

SPA_SHELL = """
<html><head><title>App</title></head>
<body>
  <noscript>You need to enable JavaScript to run this app.</noscript>
  <div id="root"></div>
  <script src="/static/bundle.js"></script>
</body></html>
"""

RENDERED = """
<html><head><title>App</title></head>
<body><div id="root"><a href="/listing/1">One</a><a href="/listing/2">Two</a></div>
</body></html>
"""

PLAIN = '<html><head><title>Plain</title></head><body><a href="/b">B</a></body></html>'


class FakeFetcher(Fetcher):
    """Scripted fetcher: ``responses`` maps url -> FetchResult or Exception."""

    name = "fake"

    def __init__(self, responses: dict, *, default_status: int = 404) -> None:
        self.responses = responses
        self.default_status = default_status
        self.calls: list[str] = []
        self.opened = False
        self.closed = False

    async def open(self, ctx: FetchContext) -> None:
        self.opened = True
        self.ctx = ctx

    async def close(self) -> None:
        self.closed = True

    async def fetch(self, url: str, headers: dict[str, str]) -> FetchResult:
        self.calls.append(url)
        value = self.responses.get(url)
        if isinstance(value, Exception):
            raise value
        if isinstance(value, list):  # sequence of outcomes, one per call
            value = value.pop(0)
            if isinstance(value, Exception):
                raise value
        if value is None:
            return FetchResult(url=url, status=self.default_status, fetcher=self.name)
        if isinstance(value, FetchResult):
            return value
        return FetchResult(url=url, status=200, body=value, fetcher=self.name)


# --------------------------------------------------------------------------
# Crawler <-> Fetcher contract
# --------------------------------------------------------------------------


class TestCrawlerUsesFetcher:
    def test_default_fetcher_is_http(self):
        assert isinstance(Crawler().fetcher, HttpFetcher)
        assert Crawler().fetcher.name == "http"

    async def test_open_and_close_called_with_context(self):
        fetcher = FakeFetcher({})
        async with Crawler(
            fetcher=fetcher, user_agent="Bot/2", request_timeout=7, ssl_verify=False
        ) as crawler:
            assert fetcher.opened
            assert fetcher.ctx.session is crawler.session
            assert fetcher.ctx.user_agent == "Bot/2"
            assert fetcher.ctx.request_timeout == 7
            assert fetcher.ctx.ssl_verify is False
        assert fetcher.closed

    async def test_session_closed_if_open_fails(self):
        class Broken(FakeFetcher):
            async def open(self, ctx: FetchContext) -> None:
                raise RuntimeError("no browser")

        crawler = Crawler(fetcher=Broken({}))
        with pytest.raises(RuntimeError, match="no browser"):
            async with crawler:
                pass
        assert crawler.session is None

    async def test_document_built_from_fetch_result(self):
        fetcher = FakeFetcher({"https://x.test/": PLAIN})
        async with Crawler(fetcher=fetcher, respect_robots_txt=False) as crawler:
            doc = await crawler.crawl_document_async("https://x.test/")
        assert doc is not None
        assert doc.title == "Plain"
        assert doc.status_code == 200
        assert doc.fetcher == "fake"
        assert [link.url for link in doc.internal_links] == ["https://x.test/b"]
        assert fetcher.calls == ["https://x.test/"]

    async def test_user_agent_header_passed_to_fetcher(self):
        seen: dict[str, dict[str, str]] = {}

        class Recording(FakeFetcher):
            async def fetch(self, url: str, headers: dict[str, str]) -> FetchResult:
                seen[url] = headers
                return await super().fetch(url, headers)

        fetcher = Recording({"https://x.test/": PLAIN})
        async with Crawler(
            fetcher=fetcher, user_agent="Bot/9", respect_robots_txt=False
        ) as crawler:
            await crawler.crawl_document_async("https://x.test/")
        assert seen["https://x.test/"]["User-Agent"] == "Bot/9"

    async def test_non_200_returns_document_without_source(self):
        fetcher = FakeFetcher({}, default_status=404)
        async with Crawler(fetcher=fetcher, respect_robots_txt=False) as crawler:
            doc = await crawler.crawl_document_async("https://x.test/missing")
        assert doc is not None
        assert doc.status_code == 404
        assert doc.source is None
        assert doc.fetcher == "fake"

    async def test_transient_error_is_retried_then_succeeds(self):
        fetcher = FakeFetcher(
            {"https://x.test/": [TransientFetchError("reset"), PLAIN]}
        )
        with patch("asyncio.sleep") as sleep:
            async with Crawler(
                fetcher=fetcher, respect_robots_txt=False, max_retries=3
            ) as crawler:
                doc = await crawler.crawl_document_async("https://x.test/")
        assert doc is not None and doc.title == "Plain"
        assert len(fetcher.calls) == 2
        assert sleep.call_count == 1

    async def test_transient_error_exhausts_retries_returns_none(self):
        fetcher = FakeFetcher({"https://x.test/": TransientFetchError("timeout")})
        with patch("asyncio.sleep") as sleep:
            async with Crawler(
                fetcher=fetcher, respect_robots_txt=False, max_retries=3
            ) as crawler:
                doc = await crawler.crawl_document_async("https://x.test/")
        assert doc is None
        assert len(fetcher.calls) == 3
        assert sleep.call_count == 2

    async def test_fetch_error_is_not_retried(self):
        fetcher = FakeFetcher({"https://x.test/": FetchError("bad request")})
        async with Crawler(
            fetcher=fetcher, respect_robots_txt=False, max_retries=3
        ) as crawler:
            doc = await crawler.crawl_document_async("https://x.test/")
        assert doc is None
        assert len(fetcher.calls) == 1

    async def test_5xx_is_retried_with_backoff(self):
        """Docs promise 5xx retries; the last 5xx is returned if none succeed."""
        fetcher = FakeFetcher(
            {
                "https://x.test/": [
                    FetchResult("https://x.test/", 503, fetcher="fake"),
                    FetchResult("https://x.test/", 503, fetcher="fake"),
                    PLAIN,
                ]
            }
        )
        with patch("asyncio.sleep") as sleep:
            async with Crawler(
                fetcher=fetcher, respect_robots_txt=False, max_retries=3
            ) as crawler:
                doc = await crawler.crawl_document_async("https://x.test/")
        assert doc is not None and doc.status_code == 200
        assert len(fetcher.calls) == 3
        assert sleep.call_count == 2

    async def test_5xx_after_all_retries_returns_last_status(self):
        fetcher = FakeFetcher({}, default_status=500)
        with patch("asyncio.sleep"):
            async with Crawler(
                fetcher=fetcher, respect_robots_txt=False, max_retries=2
            ) as crawler:
                doc = await crawler.crawl_document_async("https://x.test/")
        assert doc is not None and doc.status_code == 500
        assert len(fetcher.calls) == 2


# --------------------------------------------------------------------------
# Cache namespacing
# --------------------------------------------------------------------------


class TestCacheNamespacing:
    async def test_http_fetcher_uses_legacy_cache_key(self, tmp_path):
        """Default fetcher keeps the pre-existing on-disk key layout."""
        from linktrace.cache import ResponseCache

        legacy = ResponseCache(str(tmp_path))
        await legacy.set("https://x.test/", 200, {}, PLAIN)

        fetcher = FakeFetcher({})
        fetcher.name = "http"  # pretend to be the default fetcher
        async with Crawler(
            fetcher=fetcher, cache_dir=str(tmp_path), respect_robots_txt=False
        ) as crawler:
            doc = await crawler.crawl_document_async("https://x.test/")
        assert doc is not None and doc.title == "Plain"
        assert fetcher.calls == []  # served from cache

    async def test_non_default_fetcher_does_not_read_http_cache(self, tmp_path):
        from linktrace.cache import ResponseCache

        legacy = ResponseCache(str(tmp_path))
        await legacy.set("https://x.test/", 200, {}, SPA_SHELL)

        fetcher = FakeFetcher({"https://x.test/": RENDERED})
        async with Crawler(
            fetcher=fetcher, cache_dir=str(tmp_path), respect_robots_txt=False
        ) as crawler:
            doc = await crawler.crawl_document_async("https://x.test/")
            assert doc is not None and len(doc.internal_links) == 2
            assert fetcher.calls == ["https://x.test/"]

            # Second request is served from the fetcher's own namespace and
            # remembers which fetcher produced it.
            doc2 = await crawler.crawl_document_async("https://x.test/")
        assert doc2 is not None and doc2.fetcher == "fake"
        assert fetcher.calls == ["https://x.test/"]


# --------------------------------------------------------------------------
# HttpFetcher against a real local server
# --------------------------------------------------------------------------


class TestHttpFetcher:
    async def test_fetch_success(self, local_site):
        base = await local_site({"/": PLAIN})
        async with Crawler(respect_robots_txt=False) as crawler:
            result = await crawler.fetcher.fetch(f"{base}/", {"User-Agent": "t"})
        assert result.status == 200
        assert result.fetcher == "http"
        assert result.body is not None and "Plain" in result.body
        assert "Content-Type" in result.headers

    async def test_fetch_non_200_has_no_body(self, local_site):
        base = await local_site({"/gone": (410, "<h1>gone</h1>")})
        async with Crawler(respect_robots_txt=False) as crawler:
            result = await crawler.fetcher.fetch(f"{base}/gone", {})
        assert result.status == 410
        assert result.body is None

    async def test_connection_refused_is_transient(self):
        async with Crawler(respect_robots_txt=False, max_retries=1) as crawler:
            with pytest.raises(TransientFetchError):
                await crawler.fetcher.fetch("http://127.0.0.1:9/", {})

    async def test_unopened_fetcher_raises(self):
        with pytest.raises(RuntimeError, match="no session"):
            await HttpFetcher().fetch("https://x.test/", {})


# --------------------------------------------------------------------------
# SPA-shell heuristic
# --------------------------------------------------------------------------


class TestLooksLikeSpaShell:
    def _res(self, body, status=200):
        return FetchResult("https://x.test/", status, body=body)

    def test_noscript_javascript_hint(self):
        body = "<html><body><noscript>Enable JavaScript</noscript><a href='/a'>a</a>"
        assert looks_like_spa_shell(self._res(body))

    def test_empty_root_div(self):
        assert looks_like_spa_shell(self._res('<div id="root"></div>'))
        assert looks_like_spa_shell(self._res("<div id='app'>\n  </div>"))
        assert looks_like_spa_shell(self._res('<div id="__next"></div>'))

    def test_no_anchors_but_script_bundle(self):
        assert looks_like_spa_shell(self._res('<script src="/app.js"></script>'))

    def test_plain_html_is_not_a_shell(self):
        assert not looks_like_spa_shell(self._res(PLAIN))

    def test_populated_root_is_not_a_shell(self):
        assert not looks_like_spa_shell(self._res(RENDERED))

    def test_inline_script_without_bundle_is_not_a_shell(self):
        assert not looks_like_spa_shell(self._res("<script>var x=1</script><p>hi"))

    def test_non_200_or_empty_is_not_a_shell(self):
        assert not looks_like_spa_shell(self._res(SPA_SHELL, status=404))
        assert not looks_like_spa_shell(self._res(None))
        assert not looks_like_spa_shell(self._res(""))


# --------------------------------------------------------------------------
# RoutingFetcher
# --------------------------------------------------------------------------


class TestRoutingFetcher:
    def _pair(self):
        http = FakeFetcher({"https://x.test/": SPA_SHELL, "https://x.test/p": PLAIN})
        http.name = "http"
        browser = FakeFetcher(
            {"https://x.test/": RENDERED, "https://x.test/p": RENDERED}
        )
        browser.name = "browser"
        return http, browser

    async def test_opens_and_closes_both(self):
        http, browser = self._pair()
        routing = RoutingFetcher(http, browser)
        async with Crawler(fetcher=routing, respect_robots_txt=False):
            assert http.opened and browser.opened
        assert http.closed and browser.closed

    async def test_escalates_spa_shell_to_fallback(self):
        http, browser = self._pair()
        routing = RoutingFetcher(http, browser)
        async with Crawler(fetcher=routing, respect_robots_txt=False) as crawler:
            doc = await crawler.crawl_document_async("https://x.test/")
        assert doc is not None
        assert doc.fetcher == "browser"
        assert len(doc.internal_links) == 2
        assert http.calls == ["https://x.test/"]
        assert browser.calls == ["https://x.test/"]
        assert routing.escalations == 1

    async def test_plain_page_stays_on_default(self):
        http, browser = self._pair()
        routing = RoutingFetcher(http, browser)
        async with Crawler(fetcher=routing, respect_robots_txt=False) as crawler:
            doc = await crawler.crawl_document_async("https://x.test/p")
        assert doc is not None and doc.fetcher == "http"
        assert browser.calls == []
        assert routing.escalations == 0

    async def test_render_patterns_skip_default(self):
        http, browser = self._pair()
        routing = RoutingFetcher(http, browser, render_patterns=[r"/p$"])
        async with Crawler(fetcher=routing, respect_robots_txt=False) as crawler:
            doc = await crawler.crawl_document_async("https://x.test/p")
        assert doc is not None and doc.fetcher == "browser"
        assert http.calls == []

    async def test_route_callable_skips_default(self):
        http, browser = self._pair()
        routing = RoutingFetcher(http, browser, route=lambda url: url.endswith("/p"))
        assert routing.needs_render("https://x.test/p")
        assert not routing.needs_render("https://x.test/")

    async def test_escalation_can_be_disabled(self):
        http, browser = self._pair()
        routing = RoutingFetcher(http, browser, escalate=None)
        async with Crawler(fetcher=routing, respect_robots_txt=False) as crawler:
            doc = await crawler.crawl_document_async("https://x.test/")
        assert doc is not None and doc.fetcher == "http"
        assert browser.calls == []

    def test_defaults_to_http_and_browser(self):
        from linktrace import BrowserFetcher

        routing = RoutingFetcher()
        assert isinstance(routing.default, HttpFetcher)
        assert isinstance(routing.fallback, BrowserFetcher)

    async def test_spider_end_to_end_with_routing(self):
        http = FakeFetcher(
            {"https://x.test/": SPA_SHELL, "https://x.test/listing/1": PLAIN}
        )
        http.name = "http"
        browser = FakeFetcher({"https://x.test/": RENDERED})
        browser.name = "browser"
        spider = Spider(
            "https://x.test/",
            max_depth=1,
            fetcher=RoutingFetcher(http, browser),
            respect_robots_txt=False,
        )
        docs = await spider.run_async()
        by_url = {d.url: d for d in docs}
        assert by_url["https://x.test/"].fetcher == "browser"
        assert by_url["https://x.test/listing/1"].fetcher == "http"
        assert by_url["https://x.test/listing/2"].status_code == 404


# --------------------------------------------------------------------------
# Hash-router SPAs
# --------------------------------------------------------------------------


class TestHashRoutes:
    def test_normalize_strips_fragments_by_default(self):
        assert Crawler.normalize_url("https://x.test/#/about") == "https://x.test/"
        assert Crawler.normalize_url("https://x.test/p#top") == "https://x.test/p"

    def test_normalize_keeps_route_fragments_when_asked(self):
        assert (
            Crawler.normalize_url("https://x.test/#/about", keep_hash_routes=True)
            == "https://x.test/#/about"
        )
        assert (
            Crawler.normalize_url("https://x.test#!/a", keep_hash_routes=True)
            == "https://x.test/#!/a"
        )
        # Plain in-page anchors are still dropped.
        assert (
            Crawler.normalize_url("https://x.test/p#top", keep_hash_routes=True)
            == "https://x.test/p"
        )

    def test_parse_document_extracts_hash_routes(self):
        html = '<a href="#/about">About</a><a href="#top">Top</a><a href="/x">X</a>'
        default = Crawler().parse_document("https://x.test/", html)
        assert [link.url for link in default.internal_links] == ["https://x.test/x"]

        keep = Crawler(keep_hash_routes=True).parse_document("https://x.test/", html)
        assert [link.url for link in keep.internal_links] == [
            "https://x.test/#/about",
            "https://x.test/x",
        ]

    def test_spider_threads_option_through(self):
        spider = Spider("https://x.test/#/home", keep_hash_routes=True)
        assert spider.start_url == "https://x.test/#/home"
        assert Spider("https://x.test/#/home").start_url == "https://x.test/"
