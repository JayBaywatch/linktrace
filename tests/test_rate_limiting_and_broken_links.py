"""Tests for rate limiting, robots.txt support, and broken link tracking."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from linktrace import Crawler, Document, Spider


@pytest.mark.asyncio
class TestRateLimiting:
    """Test per-domain rate limiting."""

    async def test_rate_limit_enforces_delay(self):
        """Rate limiter should enforce configured delay between requests."""
        crawler = Crawler(request_delay=0.1)
        async with crawler:
            url1 = "https://example.com/page1"
            url2 = "https://example.com/page2"

            start = time.time()
            await crawler._rate_limit_domain(url1, 0.1)
            await crawler._rate_limit_domain(url2, 0.1)
            elapsed = time.time() - start

            assert elapsed >= 0.1, "Rate limiter should enforce delay"

    async def test_different_domains_concurrent(self):
        """Different domains should not be rate limited against each other."""
        crawler = Crawler(request_delay=0.1)
        async with crawler:

            async def measure_delay(domain, delay):
                start = time.time()
                await crawler._rate_limit_domain(f"https://{domain}/page", delay)
                return time.time() - start

            start_time = time.time()
            tasks = [
                measure_delay("example1.com", 0.1),
                measure_delay("example2.com", 0.1),
            ]
            await asyncio.gather(*tasks)
            total_time = time.time() - start_time

            assert total_time < 0.15, "Different domains should run concurrently"

    async def test_per_domain_locks_created(self):
        """Each domain should get its own lock."""
        crawler = Crawler()
        async with crawler:
            url1 = "https://example.com/page"
            url2 = "https://other.com/page"

            await crawler._rate_limit_domain(url1, 0.0)
            await crawler._rate_limit_domain(url2, 0.0)

            assert "example.com" in crawler._domain_locks
            assert "other.com" in crawler._domain_locks

    async def test_request_delay_parameter(self):
        """Crawler should accept request_delay parameter."""
        crawler = Crawler(request_delay=0.5)
        assert crawler.request_delay == 0.5


@pytest.mark.asyncio
class TestRobotsManager:
    """Test robots.txt parsing and rate limiting."""

    async def test_robots_manager_initialized(self):
        """RobotsManager should be initialized when respect_robots_txt=True."""
        crawler = Crawler(respect_robots_txt=True)
        async with crawler:
            assert crawler.robots_manager is not None

    async def test_robots_manager_not_initialized_when_disabled(self):
        """RobotsManager should not be initialized when respect_robots_txt=False."""
        crawler = Crawler(respect_robots_txt=False)
        async with crawler:
            assert crawler.robots_manager is None

    async def test_user_agent_configurable(self):
        """User-Agent should be configurable."""
        crawler = Crawler(user_agent="MyBot/1.0")
        assert crawler.user_agent == "MyBot/1.0"

    async def test_user_agent_header_set_in_requests(self):
        """User-Agent header should be set in HTTP requests."""
        crawler = Crawler(user_agent="TestBot/1.0")
        async with crawler:
            with patch("aiohttp.ClientSession.get") as mock_get:
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.headers = {}
                mock_response.text = AsyncMock(return_value="<html></html>")

                mock_cm = AsyncMock()
                mock_cm.__aenter__.return_value = mock_response
                mock_cm.__aexit__.return_value = None
                mock_get.return_value = mock_cm

                try:
                    await crawler.crawl_document_async("https://example.com")
                except Exception:
                    pass

                # Check that User-Agent header was passed
                assert mock_get.called
                call_kwargs = mock_get.call_args[1]
                assert "headers" in call_kwargs
                assert call_kwargs["headers"]["User-Agent"] == "TestBot/1.0"


class TestBrokenLinkTracking:
    """Test broken link tracking in Document model."""

    def test_document_has_broken_link_collections(self):
        """Document should have broken_internal_links and broken_external_links."""
        doc = Document("https://example.com", None)
        assert hasattr(doc, "broken_internal_links")
        assert hasattr(doc, "broken_external_links")
        assert doc.broken_internal_links == []
        assert doc.broken_external_links == []

    def test_broken_link_status_code(self):
        """BrokenLink should store status code."""
        from linktrace.Crawler import BrokenLink

        broken = BrokenLink("https://example.com", 404)
        assert broken.status_code == 404
        assert broken.url == "https://example.com"

    def test_broken_link_stored_on_error(self):
        """BrokenLink should store error status code."""
        from linktrace.Crawler import BrokenLink

        broken_404 = BrokenLink("https://example.com/notfound", 404)
        broken_500 = BrokenLink("https://example.com/error", 500)

        assert broken_404.status_code == 404
        assert broken_500.status_code == 500

    @pytest.mark.asyncio
    async def test_http_4xx_tracked_as_broken(self):
        """HTTP 4xx responses should return Document with broken link."""
        crawler = Crawler()
        async with crawler:
            with patch("aiohttp.ClientSession.get") as mock_get:
                mock_response = AsyncMock()
                mock_response.status = 404
                mock_response.headers = {}

                mock_cm = AsyncMock()
                mock_cm.__aenter__.return_value = mock_response
                mock_cm.__aexit__.return_value = None
                mock_get.return_value = mock_cm

                doc = await crawler.crawl_document_async("https://example.com/notfound")

                assert doc is not None
                assert doc.status_code == 404

    @pytest.mark.asyncio
    async def test_http_5xx_tracked_as_broken(self):
        """HTTP 5xx responses should return Document with broken link."""
        crawler = Crawler()
        async with crawler:
            with patch("aiohttp.ClientSession.get") as mock_get:
                mock_response = AsyncMock()
                mock_response.status = 500
                mock_response.headers = {}

                mock_cm = AsyncMock()
                mock_cm.__aenter__.return_value = mock_response
                mock_cm.__aexit__.return_value = None
                mock_get.return_value = mock_cm

                doc = await crawler.crawl_document_async("https://example.com/error")

                assert doc is not None
                assert doc.status_code == 500


class TestBackwardCompatibility:
    """Test backward compatibility with existing API."""

    def test_default_request_delay_is_zero(self):
        """Default request_delay should be 0 (no delay)."""
        crawler = Crawler()
        assert crawler.request_delay == 0.0

    def test_default_user_agent(self):
        """Default user agent should be set."""
        crawler = Crawler()
        assert crawler.user_agent == "WebCrawler/0.1.0"

    def test_default_respect_robots_txt_true(self):
        """Default respect_robots_txt should be True."""
        crawler = Crawler()
        assert crawler.respect_robots_txt is True

    def test_spider_default_parameters(self):
        """Spider should have default rate limiting parameters."""
        spider = Spider(start_url="https://example.com")
        assert spider.request_delay == 0.0
        assert spider.user_agent == "WebCrawler/0.1.0"
        assert spider.respect_robots_txt is True

    def test_spider_custom_parameters(self):
        """Spider should accept custom rate limiting parameters."""
        spider = Spider(
            start_url="https://example.com",
            request_delay=1.0,
            user_agent="MyBot/1.0",
            respect_robots_txt=False,
        )
        assert spider.request_delay == 1.0
        assert spider.user_agent == "MyBot/1.0"
        assert spider.respect_robots_txt is False

    @pytest.mark.asyncio
    async def test_existing_crawl_unaffected(self):
        """Existing crawls without rate limiting should work."""
        crawler = Crawler()
        async with crawler:
            with patch("aiohttp.ClientSession.get") as mock_get:
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.headers = {}
                mock_response.text = AsyncMock(
                    return_value="<html><title>Test</title></html>"
                )

                mock_cm = AsyncMock()
                mock_cm.__aenter__.return_value = mock_response
                mock_cm.__aexit__.return_value = None
                mock_get.return_value = mock_cm

                doc = await crawler.crawl_document_async("https://example.com")

                assert doc is not None
                assert doc.title == "Test"
