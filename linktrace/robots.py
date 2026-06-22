"""robots.txt parsing and rate limiting support."""

import asyncio
import logging
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import aiohttp


class RobotsManager:
    """Fetches and caches robots.txt for respectful rate-limited crawling."""

    def __init__(self, user_agent: str, session: aiohttp.ClientSession) -> None:
        """Initialize RobotsManager with user agent and HTTP session.

        Args:
            user_agent: User-Agent string to pass to robots.txt rules
            session: aiohttp ClientSession for fetching robots.txt files
        """
        self.user_agent = user_agent
        self.session = session
        self._robots_cache: dict[str, RobotFileParser | None] = {}
        self._fetch_locks: dict[str, asyncio.Lock] = {}
        self._logger = logging.getLogger(__name__)

    async def get_crawl_delay(self, url: str) -> float:
        """Get crawl delay for URL's domain from robots.txt.

        Returns crawl-delay if available, 0.0 otherwise.
        Falls back gracefully if robots.txt unavailable.
        """
        domain = urlparse(url).netloc
        parser = await self._get_robots_parser(domain)

        if parser is None:
            return 0.0

        try:
            crawl_delay = parser.crawl_delay(self.user_agent)
            if crawl_delay:
                return float(crawl_delay)

            request_rate = parser.request_rate(self.user_agent)
            if request_rate:
                return 1.0 / request_rate.requests * request_rate.seconds

            return 0.0
        except Exception as e:
            self._logger.debug(
                f"Error extracting delay from robots.txt for {domain}: {e}"
            )
            return 0.0

    async def is_allowed(self, url: str) -> bool:
        """Check if URL is allowed by robots.txt.

        Returns True if allowed or robots.txt unavailable (fail-open).
        """
        domain = urlparse(url).netloc
        parser = await self._get_robots_parser(domain)

        if parser is None:
            return True

        try:
            return parser.can_fetch(self.user_agent, url)
        except Exception as e:
            self._logger.debug(f"Error checking URL allowance for {url}: {e}")
            return True

    async def get_sitemaps(self, url: str) -> list[str]:
        """Return sitemap URLs declared in the domain's robots.txt.

        Returns an empty list if robots.txt is unavailable or declares none.
        """
        domain = urlparse(url).netloc
        parser = await self._get_robots_parser(domain)

        if parser is None:
            return []

        try:
            sitemaps = parser.site_maps()
            return list(sitemaps) if sitemaps else []
        except Exception as e:
            self._logger.debug(f"Error extracting sitemaps for {domain}: {e}")
            return []

    async def _get_robots_parser(self, domain: str) -> RobotFileParser | None:
        """Get cached robots.txt parser for domain, or fetch and cache it."""
        if domain in self._robots_cache:
            return self._robots_cache[domain]

        if domain not in self._fetch_locks:
            self._fetch_locks[domain] = asyncio.Lock()

        async with self._fetch_locks[domain]:
            if domain in self._robots_cache:
                return self._robots_cache[domain]

            parser: RobotFileParser | None = await self._fetch_robots_txt(domain)
            self._robots_cache[domain] = parser
            return parser

    async def _fetch_robots_txt(self, domain: str) -> RobotFileParser | None:
        """Fetch robots.txt from domain. Returns None if unavailable."""
        url = f"https://{domain}/robots.txt"

        try:
            async with self.session.get(
                url, timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    content = await response.text()
                    parser = RobotFileParser()
                    parser.parse(content.splitlines())
                    self._logger.debug(f"Fetched robots.txt from {domain}")
                    return parser
                else:
                    self._logger.debug(
                        f"robots.txt unavailable for {domain} (HTTP {response.status})"
                    )
                    return None
        except TimeoutError:
            self._logger.debug(f"Timeout fetching robots.txt from {domain}")
            return None
        except aiohttp.ClientError as e:
            self._logger.debug(f"Error fetching robots.txt from {domain}: {e}")
            return None
        except Exception as e:
            self._logger.debug(
                f"Unexpected error fetching robots.txt from {domain}: {e}"
            )
            return None
