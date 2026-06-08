"""Tests for Crawler parsing logic."""

from linktrace import Crawler


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


class TestProtocolHandling:
    """Test handling of dangerous protocols and external resource links."""

    def test_filters_javascript_lowercase(self):
        """JavaScript URLs with lowercase protocol should be filtered."""
        html = '<a href="javascript:void(0)">Link</a>'
        crawler = Crawler()
        doc = crawler.parse_document("https://example.com", html)
        assert len(doc.links) == 0, "Lowercase javascript: should be filtered"

    def test_filters_javascript_uppercase(self):
        """JavaScript URLs with uppercase protocol might bypass simple filter."""
        html = "<a href=\"JavaScript:alert('xss')\">Link</a>"
        crawler = Crawler()
        doc = crawler.parse_document("https://example.com", html)
        # This tests if uppercase JavaScript bypasses the filter
        # The current implementation is case-sensitive!
        assert len(doc.links) == 0, "Uppercase JavaScript: should be filtered"

    def test_filters_javascript_mixed_case(self):
        """JavaScript URLs with mixed case might bypass simple filter."""
        html = '<a href="jAvAsCrIpT:void(0)">Link</a>'
        crawler = Crawler()
        doc = crawler.parse_document("https://example.com", html)
        assert len(doc.links) == 0, "Mixed case jAvAsCrIpT: should be filtered"

    def test_filters_data_urls(self):
        """Data URLs (potential XSS vectors) should be filtered."""
        html = "<a href=\"data:text/html,<script>alert('xss')</script>\">Link</a>"
        crawler = Crawler()
        doc = crawler.parse_document("https://example.com", html)
        assert len(doc.links) == 0, "data: URLs should be filtered by scheme check"

    def test_filters_vbscript(self):
        """VBScript protocol should be filtered."""
        html = "<a href=\"vbscript:msgbox('xss')\">Link</a>"
        crawler = Crawler()
        doc = crawler.parse_document("https://example.com", html)
        assert len(doc.links) == 0, "vbscript: should be filtered by scheme check"

    def test_filters_file_protocol(self):
        """File protocol should be filtered."""
        html = '<a href="file:///etc/passwd">Link</a>'
        crawler = Crawler()
        doc = crawler.parse_document("https://example.com", html)
        assert len(doc.links) == 0, "file: should be filtered by scheme check"

    def test_filters_mailto_links(self):
        """Mailto links should be filtered."""
        html = '<a href="mailto:user@example.com">Email</a>'
        crawler = Crawler()
        doc = crawler.parse_document("https://example.com", html)
        assert len(doc.links) == 0, "mailto: should be filtered by scheme check"

    def test_filters_tel_links(self):
        """Tel links should be filtered."""
        html = '<a href="tel:+1234567890">Phone</a>'
        crawler = Crawler()
        doc = crawler.parse_document("https://example.com", html)
        assert len(doc.links) == 0, "tel: should be filtered by scheme check"

    def test_filters_anchor_only_links(self):
        """Links that are just anchors (#) should be filtered."""
        html = '<a href="#anchor">Anchor</a>'
        crawler = Crawler()
        doc = crawler.parse_document("https://example.com", html)
        # Anchor-only links start with # which is in skip_words
        assert len(doc.links) == 0, "Anchor-only links should be filtered"

    def test_filters_empty_href(self):
        """Empty href attributes should be filtered."""
        html = '<a href="">Empty</a>'
        crawler = Crawler()
        doc = crawler.parse_document("https://example.com", html)
        assert len(doc.links) == 0, "Empty href should be filtered"

    def test_allows_http_https_ftp(self):
        """Valid HTTP, HTTPS, and FTP URLs should be allowed."""
        html = """
        <a href="http://example.com/page">HTTP</a>
        <a href="https://example.com/page">HTTPS</a>
        <a href="ftp://example.com/file">FTP</a>
        """
        crawler = Crawler()
        doc = crawler.parse_document("https://example.com", html)
        assert len(doc.links) == 3, "HTTP, HTTPS, FTP should all be allowed"

    def test_protocol_edge_cases_comprehensive(self, protocol_edge_cases_html):
        """Comprehensive test with all dangerous protocols."""
        crawler = Crawler()
        doc = crawler.parse_document("https://example.com", protocol_edge_cases_html)
        # Should only have safe HTTP/HTTPS/FTP links
        safe_links = doc.links
        for link in safe_links:
            scheme = link.url.split("://")[0].lower()
            assert scheme in [
                "http",
                "https",
                "ftp",
            ], f"Unexpected scheme: {scheme} in {link.url}"
