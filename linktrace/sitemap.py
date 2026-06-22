"""Sitemap discovery and parsing.

Discovers page URLs from XML sitemaps so the Spider can seed its queue from a
site's own document inventory rather than relying purely on link-following.
Handles ``/sitemap.xml``, ``Sitemap:`` declarations in robots.txt, sitemap
*index* files and arbitrarily nested sitemaps (with loop and depth guards).
"""

import logging

import aiohttp
import lxml.etree


class SitemapParser:
    """Fetches and parses XML sitemaps, returning the page URLs they list."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        user_agent: str = "linktrace/0.1.0",
        logger: logging.Logger | None = None,
        max_sitemaps: int = 50,
        max_depth: int = 5,
    ) -> None:
        """Initialize the parser.

        Args:
            session: aiohttp session used to fetch sitemap documents.
            user_agent: User-Agent sent with sitemap requests.
            logger: Logger to use; defaults to this module's logger.
            max_sitemaps: Hard cap on the number of sitemap documents fetched,
                guarding against pathological sitemap indexes.
            max_depth: Maximum nesting depth for sitemap-index recursion.
        """
        self.session = session
        self.user_agent = user_agent
        self._logger = logger or logging.getLogger(__name__)
        self.max_sitemaps = max_sitemaps
        self.max_depth = max_depth

    async def discover(
        self, base_url: str, robots_sitemaps: list[str] | None = None
    ) -> list[str]:
        """Discover page URLs for ``base_url`` from its sitemaps.

        Candidate sitemaps come from robots.txt ``Sitemap:`` declarations when
        provided, otherwise from the conventional ``/sitemap.xml`` location.

        Returns:
            A de-duplicated list of page URLs, preserving discovery order.
        """
        from urllib.parse import urljoin

        if robots_sitemaps:
            candidates = list(robots_sitemaps)
        else:
            candidates = [urljoin(base_url, "/sitemap.xml")]

        page_urls: list[str] = []
        seen_pages: set[str] = set()
        visited_sitemaps: set[str] = set()
        fetched = 0

        # Iterative worklist so a sitemap index can enqueue its children.
        worklist: list[tuple[str, int]] = [(c, 0) for c in candidates]
        while worklist:
            sitemap_url, depth = worklist.pop(0)
            if sitemap_url in visited_sitemaps or depth > self.max_depth:
                continue
            visited_sitemaps.add(sitemap_url)

            if fetched >= self.max_sitemaps:
                self._logger.debug(
                    f"Sitemap limit ({self.max_sitemaps}) reached; stopping discovery"
                )
                break
            fetched += 1

            kind, locs = await self._fetch_and_parse(sitemap_url)
            if kind == "index":
                for loc in locs:
                    if loc not in visited_sitemaps:
                        worklist.append((loc, depth + 1))
            elif kind == "urlset":
                for loc in locs:
                    if loc not in seen_pages:
                        seen_pages.add(loc)
                        page_urls.append(loc)

        self._logger.debug(
            f"Sitemap discovery for {base_url}: "
            f"{len(page_urls)} URLs from {fetched} sitemap(s)"
        )
        return page_urls

    async def _fetch_and_parse(self, url: str) -> tuple[str | None, list[str]]:
        """Fetch a sitemap and return ``(kind, locs)``.

        ``kind`` is ``"index"`` for a sitemap index, ``"urlset"`` for a page
        listing, or ``None`` when the document could not be fetched or parsed.
        """
        try:
            headers = {"User-Agent": self.user_agent}
            async with self.session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                if response.status != 200:
                    self._logger.debug(
                        f"Sitemap unavailable: {url} (HTTP {response.status})"
                    )
                    return None, []
                content = await response.read()
        except (TimeoutError, aiohttp.ClientError) as e:
            self._logger.debug(f"Error fetching sitemap {url}: {e}")
            return None, []

        return self.parse(content)

    @staticmethod
    def parse(content: bytes) -> tuple[str | None, list[str]]:
        """Parse sitemap XML bytes into ``(kind, locs)``.

        Namespace-agnostic: matches ``<loc>`` elements by local name so both
        namespaced and bare sitemaps work.
        """
        try:
            root = lxml.etree.fromstring(content)
        except lxml.etree.XMLSyntaxError:
            return None, []

        tag = lxml.etree.QName(root).localname if root.tag is not None else ""
        locs = [
            text.strip()
            for text in root.xpath("//*[local-name()='loc']/text()")
            if text and text.strip()
        ]

        if tag == "sitemapindex":
            return "index", locs
        if tag == "urlset":
            return "urlset", locs
        return None, []
