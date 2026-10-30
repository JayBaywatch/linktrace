"""Tests for BrowserFetcher against a local JavaScript-rendered page.

Skipped automatically when Playwright or its Chromium build is not installed
(``pip install 'linktrace[browser]' && playwright install chromium``).
"""

import time

import pytest

from linktrace import BrowserFetcher, Crawler, RoutingFetcher, Spider

pytest.importorskip("playwright", reason="playwright not installed")

# An SPA-style page: no anchors in the HTML, links injected by script.
SPA_HOME = """
<html><head><title>Listings</title></head>
<body>
  <noscript>You need to enable JavaScript to run this app.</noscript>
  <div id="root"></div>
  <script>
    document.getElementById('root').innerHTML =
      '<a href="/listing/1">One</a><a href="/listing/2">Two</a>' +
      '<a href="https://other.example/x">Ext</a>';
    document.title = 'Listings (rendered)';
  </script>
</body></html>
"""
LISTING = "<html><head><title>Listing</title></head><body><p>house</p></body></html>"
PLAIN = '<html><head><title>Plain</title></head><body><a href="/listing/1">1</a>'


@pytest.fixture
async def chromium_available():
    """Skip when the Chromium build has not been downloaded."""
    from playwright.async_api import Error, async_playwright

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=True)
        except Error as e:
            pytest.skip(f"Chromium not installed: {str(e).splitlines()[0]}")
        await browser.close()


@pytest.mark.usefixtures("chromium_available")
class TestBrowserFetcher:
    async def test_renders_javascript_links(self, local_site):
        base = await local_site({"/": SPA_HOME, "/listing/1": LISTING})

        # Plain HTTP sees an empty shell...
        async with Crawler(respect_robots_txt=False) as crawler:
            plain = await crawler.crawl_document_async(f"{base}/")
        assert plain is not None
        assert plain.internal_links == []
        assert plain.fetcher == "http"

        # ...the browser sees the rendered DOM.
        async with Crawler(
            fetcher=BrowserFetcher(), respect_robots_txt=False
        ) as crawler:
            doc = await crawler.crawl_document_async(f"{base}/")
        assert doc is not None
        assert doc.fetcher == "browser"
        assert doc.status_code == 200
        assert doc.title == "Listings (rendered)"
        assert [link.url for link in doc.internal_links] == [
            f"{base}/listing/1",
            f"{base}/listing/2",
        ]
        assert [link.url for link in doc.external_links] == ["https://other.example/x"]

    async def test_non_200_status_propagates(self, local_site):
        base = await local_site({"/missing": (404, "<h1>nope</h1>")})
        async with Crawler(
            fetcher=BrowserFetcher(), respect_robots_txt=False, max_retries=1
        ) as crawler:
            doc = await crawler.crawl_document_async(f"{base}/missing")
        assert doc is not None
        assert doc.status_code == 404
        assert doc.source is None

    async def test_wait_for_selector(self, local_site):
        base = await local_site({"/": SPA_HOME})
        fetcher = BrowserFetcher(
            wait_until="domcontentloaded", wait_for_selector="a[href]"
        )
        async with Crawler(fetcher=fetcher, respect_robots_txt=False) as crawler:
            doc = await crawler.crawl_document_async(f"{base}/")
        assert doc is not None and len(doc.internal_links) == 2

    async def test_routing_escalates_only_spa_pages(self, local_site):
        base = await local_site(
            {"/": SPA_HOME, "/listing/1": LISTING, "/listing/2": LISTING}
        )
        routing = RoutingFetcher()
        spider = Spider(
            f"{base}/", max_depth=1, fetcher=routing, respect_robots_txt=False
        )
        docs = await spider.run_async()
        by_url = {d.url: d for d in docs}
        assert by_url[f"{base}/"].fetcher == "browser"
        assert by_url[f"{base}/listing/1"].fetcher == "http"
        assert by_url[f"{base}/listing/2"].fetcher == "http"
        assert routing.escalations == 1

    async def test_unopened_fetcher_raises(self):
        with pytest.raises(RuntimeError, match="not open"):
            await BrowserFetcher().fetch("https://x.test/", {})

    def test_max_pages_validated(self):
        with pytest.raises(ValueError):
            BrowserFetcher(max_pages=0)

    async def test_error_page_skips_selector_wait(self, local_site):
        """A 404 must not burn the selector timeout and become a retry."""
        base = await local_site({"/missing": (404, "<h1>nope</h1>")})
        fetcher = BrowserFetcher(
            wait_until="domcontentloaded", wait_for_selector="#never-appears"
        )
        async with Crawler(
            fetcher=fetcher, respect_robots_txt=False, request_timeout=5, max_retries=1
        ) as crawler:
            start = time.monotonic()
            doc = await crawler.crawl_document_async(f"{base}/missing")
            elapsed = time.monotonic() - start
        assert doc is not None and doc.status_code == 404
        assert elapsed < 4  # did not wait out the 5s selector timeout

    async def test_size_limit_counts_utf8_bytes(self, local_site):
        from linktrace import ResponseTooLarge

        # 600 chars of a 2-byte character: under a 1000-char limit by length,
        # over it by bytes once the HTML wrapper is added.
        page = "<html><body><p>" + "é" * 600 + "</p></body></html>"
        base = await local_site({"/wide": page})
        async with Crawler(
            fetcher=BrowserFetcher(), respect_robots_txt=False, max_response_bytes=1000
        ) as crawler:
            with pytest.raises(ResponseTooLarge) as exc:
                await crawler.fetcher.fetch(f"{base}/wide", {})
        assert exc.value.size > 1200
