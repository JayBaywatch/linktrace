"""Tests for sitemap parsing and discovery."""

import pytest

from linktrace import SitemapParser

URLSET = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/a</loc></url>
  <url><loc>https://example.com/b</loc></url>
</urlset>
"""

SITEMAP_INDEX = b"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-1.xml</loc></sitemap>
  <sitemap><loc>https://example.com/sitemap-2.xml</loc></sitemap>
</sitemapindex>
"""

BARE_URLSET = b"""<urlset>
  <url><loc>https://example.com/bare</loc></url>
</urlset>
"""


class TestParse:
    def test_parse_urlset(self):
        kind, locs = SitemapParser.parse(URLSET)
        assert kind == "urlset"
        assert locs == ["https://example.com/a", "https://example.com/b"]

    def test_parse_index(self):
        kind, locs = SitemapParser.parse(SITEMAP_INDEX)
        assert kind == "index"
        assert locs == [
            "https://example.com/sitemap-1.xml",
            "https://example.com/sitemap-2.xml",
        ]

    def test_parse_namespaceless(self):
        kind, locs = SitemapParser.parse(BARE_URLSET)
        assert kind == "urlset"
        assert locs == ["https://example.com/bare"]

    def test_parse_garbage_returns_none(self):
        kind, locs = SitemapParser.parse(b"not xml at all <<<")
        assert kind is None
        assert locs == []


class FakeResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def read(self) -> bytes:
        return self._body


class FakeSession:
    """Minimal aiohttp-like session returning canned bodies per URL."""

    def __init__(self, responses: dict[str, tuple[int, bytes]]) -> None:
        self.responses = responses
        self.requested: list[str] = []

    def get(self, url: str, **kwargs):
        self.requested.append(url)
        status, body = self.responses.get(url, (404, b""))
        return FakeResponse(status, body)


@pytest.mark.asyncio
class TestDiscover:
    async def test_discover_flat_sitemap(self):
        session = FakeSession({"https://example.com/sitemap.xml": (200, URLSET)})
        parser = SitemapParser(session)  # type: ignore[arg-type]
        urls = await parser.discover("https://example.com/")
        assert urls == ["https://example.com/a", "https://example.com/b"]

    async def test_discover_nested_index(self):
        session = FakeSession(
            {
                "https://example.com/sitemap.xml": (200, SITEMAP_INDEX),
                "https://example.com/sitemap-1.xml": (200, URLSET),
                "https://example.com/sitemap-2.xml": (200, BARE_URLSET),
            }
        )
        parser = SitemapParser(session)  # type: ignore[arg-type]
        urls = await parser.discover("https://example.com/")
        assert urls == [
            "https://example.com/a",
            "https://example.com/b",
            "https://example.com/bare",
        ]

    async def test_discover_uses_robots_sitemaps(self):
        session = FakeSession({"https://example.com/custom-sitemap.xml": (200, URLSET)})
        parser = SitemapParser(session)  # type: ignore[arg-type]
        urls = await parser.discover(
            "https://example.com/",
            robots_sitemaps=["https://example.com/custom-sitemap.xml"],
        )
        assert urls == ["https://example.com/a", "https://example.com/b"]
        assert "https://example.com/sitemap.xml" not in session.requested

    async def test_discover_missing_sitemap_returns_empty(self):
        session = FakeSession({})
        parser = SitemapParser(session)  # type: ignore[arg-type]
        urls = await parser.discover("https://example.com/")
        assert urls == []
