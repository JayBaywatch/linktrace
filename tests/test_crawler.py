"""Tests for Crawler parsing logic."""

from WebCrawler import Crawler


class TestCrawlerParsing:
    """Test Crawler.parse_document method."""

    def test_parse_document_none_source(self):
        crawler = Crawler()
        doc = crawler.parse_document("https://example.com", None)
        assert doc.url == "https://example.com"
        assert doc.source is None
        assert doc.title == ""
        assert doc.internal_links == []
        assert doc.external_links == []

    def test_parse_document_extracts_title(self, sample_html):
        crawler = Crawler()
        doc = crawler.parse_document("https://example.com", sample_html)
        assert doc.title == "Test Page"

    def test_parse_document_extracts_links(self, sample_html):
        crawler = Crawler()
        doc = crawler.parse_document("https://internal.example.com/page", sample_html)
        # Should have both internal and external links
        assert len(doc.internal_links) > 0
        assert len(doc.external_links) > 0

    def test_parse_document_filters_javascript_links(self, sample_html):
        crawler = Crawler()
        doc = crawler.parse_document("https://example.com", sample_html)
        # JavaScript links should be filtered out
        for link in doc.links:
            assert "javascript:" not in link.url

    def test_parse_document_resolves_relative_urls(self):
        html = '<a href="/path/to/page">Link</a>'
        crawler = Crawler()
        doc = crawler.parse_document("https://example.com/other", html)
        assert len(doc.internal_links) == 1
        assert doc.internal_links[0].url == "https://example.com/path/to/page"

    def test_parse_document_deduplicates_links(self):
        html = """
            <a href="https://example.com/page1">Link 1</a>
            <a href="https://example.com/page1">Link 2</a>
        """
        crawler = Crawler()
        doc = crawler.parse_document("https://example.com", html)
        # Should have only one unique link (URL-based dedup)
        assert len(doc.internal_links) == 1

    def test_parse_document_separates_internal_external(self):
        html = """
            <a href="https://example.com/internal">Internal</a>
            <a href="https://other.com/external">External</a>
        """
        crawler = Crawler()
        doc = crawler.parse_document("https://example.com/page", html)
        # Check internal vs external
        assert any(
            link.url == "https://example.com/internal" for link in doc.internal_links
        )
        assert any(
            link.url == "https://other.com/external" for link in doc.external_links
        )


class TestCrawlerQueue:
    """Test Crawler queue management."""

    def test_queue_link_adds_to_queue(self):
        crawler = Crawler()
        crawler.queue_link("https://example.com/page1")
        assert "https://example.com/page1" in crawler._queue

    def test_queue_link_prevents_duplicates(self):
        crawler = Crawler()
        crawler.queue_link("https://example.com/page1")
        crawler.queue_link("https://example.com/page1")
        assert crawler._queue.count("https://example.com/page1") == 1

    def test_queue_link_excludes_visited(self):
        crawler = Crawler()
        crawler.visited_urls.add("https://example.com/page1")
        crawler.queue_link("https://example.com/page1")
        assert "https://example.com/page1" not in crawler._queue


class TestCrawlerDomainParts:
    """Test Crawler domain parsing helper."""

    def test_get_domain_parts_extracts_netloc(self):
        assert (
            Crawler.get_domain_parts("https://www.example.com/path")
            == "www.example.com"
        )
        assert Crawler.get_domain_parts("https://example.com") == "example.com"
