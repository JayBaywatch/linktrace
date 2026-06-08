"""Tests for WebCrawler models: Document, HtmlLink, BrokenLink, CrawlException."""

import pytest

from WebCrawler import BrokenLink, CrawlException, Document, HtmlLink


class TestHtmlLink:
    """Test HtmlLink model and comparison operators."""

    def test_htmllink_creation(self):
        link = HtmlLink("https://example.com", "Example")
        assert link.url == "https://example.com"
        assert link.text == "Example"

    def test_htmllink_schema_property(self):
        link = HtmlLink("https://example.com", "Example")
        assert link.schema == "https"

        http_link = HtmlLink("http://example.com", "Example")
        assert http_link.schema == "http"

    def test_htmllink_description_property(self):
        link = HtmlLink("https://example.com", "Example Description")
        assert link.description == "Example Description"

    def test_htmllink_repr(self):
        link = HtmlLink("https://example.com", "Text")
        assert "htmllink" in repr(link)
        assert "https://example.com" in repr(link)

    def test_htmllink_equality_with_url_string(self):
        link = HtmlLink("https://example.com", "Text")
        assert link == "https://example.com"
        assert not (link != "https://example.com")

    def test_htmllink_equality_with_another_link(self):
        link1 = HtmlLink("https://example.com", "Text 1")
        link2 = HtmlLink("https://example.com", "Text 2")
        assert link1 == link2

    def test_htmllink_inequality(self):
        link1 = HtmlLink("https://example.com", "Text")
        link2 = HtmlLink("https://other.com", "Text")
        assert link1 != link2

    def test_htmllink_comparison_operators(self):
        link_a = HtmlLink("https://a.com", "A")
        link_b = HtmlLink("https://b.com", "B")
        assert link_a < link_b
        assert link_b > link_a
        assert not (link_a > link_b)

    def test_htmllink_hash(self):
        link1 = HtmlLink("https://example.com", "Text 1")
        link2 = HtmlLink("https://example.com", "Text 2")
        # Same URL = same hash
        assert hash(link1) == hash(link2)
        # Can be used in sets
        link_set = {link1, link2}
        assert len(link_set) == 1


class TestDocument:
    """Test Document model."""

    def test_document_creation(self):
        doc = Document("https://example.com", "<html></html>")
        assert doc.url == "https://example.com"
        assert doc.source == "<html></html>"
        assert doc.title == ""
        assert doc.status_code == 0
        assert doc.response_headers == {}

    def test_document_domain_extraction(self):
        doc = Document("https://www.github.com/path", None)
        assert doc.domain == "github"

        doc2 = Document("https://subdomain.example.co.uk", None)
        assert doc2.domain == "example"

    def test_document_lists_initialized(self):
        doc = Document("https://example.com", None)
        assert doc.internal_links == []
        assert doc.external_links == []
        assert doc.links == []


class TestBrokenLink:
    """Test BrokenLink model."""

    def test_brokenlink_creation(self):
        broken = BrokenLink("https://broken.com", 404)
        assert broken.url == "https://broken.com"
        assert broken.status_code == 404
        assert broken.text == "404"

    def test_brokenlink_inherits_from_htmllink(self):
        broken = BrokenLink("https://broken.com", 500)
        assert isinstance(broken, HtmlLink)
        assert broken.schema == "https"


class TestCrawlException:
    """Test CrawlException."""

    def test_crawl_exception_creation(self):
        exc = CrawlException("https://example.com", "Failed to fetch")
        assert exc.url == "https://example.com"
        assert exc.message == "Failed to fetch"

    def test_crawl_exception_is_exception(self):
        exc = CrawlException("https://example.com", "Error")
        assert isinstance(exc, Exception)

    def test_crawl_exception_raised(self):
        with pytest.raises(CrawlException) as exc_info:
            raise CrawlException("https://example.com", "Test error")
        assert exc_info.value.url == "https://example.com"
        assert exc_info.value.message == "Test error"
