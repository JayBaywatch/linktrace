"""Tests for Spider configurable concurrency, rules, and sitemap seeding."""

from typing import cast

import pytest

from linktrace import Crawler, CrawlRules, Document, Spider


class TestConcurrencyConfig:
    def test_defaults(self):
        spider = Spider(start_url="https://example.com")
        assert spider.max_concurrency == 10
        assert spider.max_connections == 100
        assert spider.max_connections_per_host == 10

    def test_custom_values(self):
        spider = Spider(
            start_url="https://example.com",
            max_concurrency=25,
            max_connections=200,
            max_connections_per_host=5,
        )
        assert spider.max_concurrency == 25
        assert spider.max_connections == 200
        assert spider.max_connections_per_host == 5

    def test_invalid_concurrency_raises(self):
        with pytest.raises(ValueError, match="max_concurrency"):
            Spider(start_url="https://example.com", max_concurrency=0)

    def test_connector_receives_limits(self):
        crawler = Crawler(max_connections=42, max_connections_per_host=7)
        assert crawler.max_connections == 42
        assert crawler.max_connections_per_host == 7


@pytest.mark.asyncio
class TestRulesIntegration:
    async def test_links_filtered_by_rules(self):
        rules = CrawlRules(exclude_path_prefixes=["/blog/"])
        spider = Spider(start_url="https://example.com", rules=rules)
        spider.to_visit = []

        keep = type("Link", (), {"url": "https://example.com/homes/1"})()
        drop = type("Link", (), {"url": "https://example.com/blog/post"})()
        doc = Document("https://example.com/", "")
        doc.internal_links = [keep, drop]

        class FakeCrawler:
            async def crawl_document_async(self, url: str) -> Document:
                return doc

        crawler = cast(Crawler, FakeCrawler())
        await spider.crawl_and_collect("https://example.com/", 0, crawler)

        queued = [u for u, _ in spider.to_visit]
        assert "https://example.com/homes/1" in queued
        assert "https://example.com/blog/post" not in queued


@pytest.mark.asyncio
class TestSitemapSeeding:
    async def test_seed_from_sitemaps_applies_rules(self):
        rules = CrawlRules(blocked_extensions=["pdf"])
        spider = Spider(start_url="https://example.com", rules=rules, use_sitemaps=True)
        spider.to_visit = []

        class FakeCrawler:
            async def discover_sitemap_urls(self, base_url: str) -> list[str]:
                return [
                    "https://example.com/a",
                    "https://example.com/flyer.pdf",
                    "https://example.com/a",  # duplicate
                ]

        crawler = cast(Crawler, FakeCrawler())
        await spider._seed_from_sitemaps(crawler)

        queued = [u for u, _ in spider.to_visit]
        assert queued == [("https://example.com/a")]
        assert all(depth == 0 for _, depth in spider.to_visit)

    async def test_seed_failure_is_non_fatal(self):
        spider = Spider(start_url="https://example.com", use_sitemaps=True)
        spider.to_visit = []

        class FakeCrawler:
            async def discover_sitemap_urls(self, base_url: str) -> list[str]:
                raise RuntimeError("boom")

        crawler = cast(Crawler, FakeCrawler())
        await spider._seed_from_sitemaps(crawler)  # should not raise
        assert spider.to_visit == []
