import asyncio
import logging
import random
import ssl
from urllib.parse import urldefrag, urljoin, urlparse

import aiohttp
import lxml.etree
import lxml.html
import tldextract

from linktrace._version import DEFAULT_USER_AGENT
from linktrace.cache import ResponseCache
from linktrace.fetchers.base import (
    FetchContext,
    Fetcher,
    FetchError,
    FetchResult,
    TransientFetchError,
)
from linktrace.fetchers.http import HttpFetcher
from linktrace.robots import RobotsManager


class HtmlLink:
    def __init__(self, url: str, text: str) -> None:
        self.url = url
        self.text = text

    @property
    def schema(self) -> str:
        return urlparse(self.url).scheme

    @property
    def description(self) -> str:
        return self.text

    def __repr__(self) -> str:
        return f"htmllink(url={self.url!r})"

    def __hash__(self) -> int:
        return hash(self.url)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, HtmlLink):
            return self.url == other.url
        return self.url == other

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __lt__(self, other: "HtmlLink | str") -> bool:
        return self.url < (other.url if isinstance(other, HtmlLink) else other)

    def __gt__(self, other: "HtmlLink | str") -> bool:
        return self.url > (other.url if isinstance(other, HtmlLink) else other)


class Document:
    def __init__(self, url: str, source: str | None) -> None:
        self.url = url
        self.source = source
        self.title: str = ""
        self.internal_links: list[HtmlLink] = []
        self.external_links: list[HtmlLink] = []
        self.links: list[HtmlLink] = []
        self.broken_internal_links: list[BrokenLink] = []
        self.broken_external_links: list[BrokenLink] = []
        self.status_code: int = 0
        self.response_headers: dict[str, str] = {}
        self.dom: object = None
        # Which fetcher produced ``source``: "http" (raw response) or
        # "browser" (rendered DOM), or a custom fetcher's name.
        self.fetcher: str = "http"
        # URL actually served after redirects (equals ``url`` when none).
        self.final_url: str = url

    @property
    def redirected(self) -> bool:
        """True if the server redirected this request to a different URL."""
        return self.final_url != self.url

    @property
    def domain(self) -> str:
        return tldextract.extract(self.url).domain


class CrawlException(Exception):
    def __init__(self, url: str, msg: str, **kw: object) -> None:
        self.url = url
        self.message = msg
        super().__init__(url, msg, **kw)


class BrokenLink(HtmlLink):
    def __init__(self, url: str, status: int) -> None:
        self.status_code = status
        super().__init__(url, str(status))


class Crawler:
    def __init__(
        self,
        log_level: int = logging.DEBUG,
        log_name: str | None = None,
        ssl_verify: bool | str = True,
        verify_hostname: bool = True,
        request_timeout: int = 30,
        cache_dir: str | None = None,
        max_retries: int = 3,
        backoff_factor: int = 2,
        request_delay: float = 0.0,
        user_agent: str = DEFAULT_USER_AGENT,
        respect_robots_txt: bool = True,
        max_connections: int = 100,
        max_connections_per_host: int = 10,
        fetcher: Fetcher | None = None,
        keep_hash_routes: bool = False,
        max_response_bytes: int | None = 10 * 1024 * 1024,
        backoff_jitter: bool = True,
        cache_ttl: int = 86400,
        cache_max_bytes: int | None = None,
    ) -> None:
        self._logger = logging.getLogger(log_name if log_name else __name__)
        self._logger.setLevel(log_level)

        # Guard rails for long or adversarial crawls.
        self.max_response_bytes = max_response_bytes
        self.backoff_jitter = backoff_jitter

        # Pluggable transport. HttpFetcher reproduces the classic behaviour;
        # BrowserFetcher / RoutingFetcher add JavaScript rendering.
        self.fetcher: Fetcher = fetcher if fetcher is not None else HttpFetcher()
        # Keep "#/..." and "#!..." fragments (hash-router SPAs) instead of
        # stripping every fragment during URL normalization.
        self.keep_hash_routes = keep_hash_routes
        self.visited_urls: set[str] = set()
        self._queue: list[str] = []
        self._links: list[HtmlLink] = []
        self._broken_links: list[BrokenLink] = []

        # Session configuration
        self.session: aiohttp.ClientSession | None = None
        self.ssl_verify: bool | str = ssl_verify  # bool or str(path to CA cert)
        self.verify_hostname: bool = verify_hostname
        self.request_timeout: int = request_timeout
        self.max_retries: int = max_retries
        self.backoff_factor: int = backoff_factor

        # Rate limiting and robots.txt
        self.request_delay: float = request_delay
        self.user_agent: str = user_agent
        self.respect_robots_txt: bool = respect_robots_txt
        self.max_connections: int = max_connections
        self.max_connections_per_host: int = max_connections_per_host
        self.robots_manager: RobotsManager | None = None
        self._domain_locks: dict[str, asyncio.Lock] = {}
        self._last_request_time: dict[str, float] = {}

        # Caching (opt-in)
        self.cache: ResponseCache | None = (
            ResponseCache(cache_dir, ttl_seconds=cache_ttl, max_bytes=cache_max_bytes)
            if cache_dir
            else None
        )

        # Cookies handled automatically via CookieJar in session (created lazily)
        self._cookie_jar: aiohttp.CookieJar | None = None

    async def __aenter__(self) -> "Crawler":
        """Enter async context manager: create session, then open the fetcher."""
        if self.cache:
            removed = await self.cache.prune()
            if removed:
                self._logger.debug(f"Pruned {removed} expired/excess cache entries")

        self.session = await self._create_session()
        try:
            await self.fetcher.open(
                FetchContext(
                    session=self.session,
                    request_timeout=self.request_timeout,
                    user_agent=self.user_agent,
                    ssl_verify=self.ssl_verify,
                    max_response_bytes=self.max_response_bytes,
                )
            )
        except Exception:
            # Release whatever the fetcher managed to start (e.g. a browser
            # process whose context creation failed) before giving up.
            try:
                await self.fetcher.close()
            except Exception:  # pragma: no cover - best-effort teardown
                pass
            await self.session.close()
            self.session = None
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit async context manager: close the fetcher, then the session."""
        try:
            await self.fetcher.close()
        finally:
            if self.session:
                await self.session.close()

    async def _create_session(self) -> aiohttp.ClientSession:
        """Create persistent aiohttp session with SSL context, connector, timeouts."""
        # Create cookie jar now (requires event loop)
        if self._cookie_jar is None:
            self._cookie_jar = aiohttp.CookieJar()

        ssl_context = self._build_ssl_context()

        connector = aiohttp.TCPConnector(
            limit=self.max_connections,
            limit_per_host=self.max_connections_per_host,
            ttl_dns_cache=300,
            ssl=ssl_context,
        )

        session = aiohttp.ClientSession(
            connector=connector,
            cookie_jar=self._cookie_jar,
            timeout=aiohttp.ClientTimeout(total=self.request_timeout),
        )

        # Initialize RobotsManager if robots.txt respect enabled
        if self.respect_robots_txt:
            self.robots_manager = RobotsManager(self.user_agent, session)

        return session

    def _build_ssl_context(self) -> ssl.SSLContext:
        """Build SSL context with flexible verification options.

        Supports:
        - ssl_verify=True (default): verify certs with system CA bundle
        - ssl_verify=False: disable verification (insecure, for testing)
        - ssl_verify="/path/to/ca.pem": verify with custom CA bundle (corporate proxies)
        """
        context = ssl.create_default_context()

        if self.ssl_verify is False:
            # Completely disable verification (INSECURE)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            self._logger.warning(
                "SSL certificate verification disabled. "
                "This is insecure and should only be used for testing."
            )
        elif isinstance(self.ssl_verify, str):
            # Load custom CA bundle (corporate proxy scenario)
            try:
                context.load_verify_locations(self.ssl_verify)
                self._logger.debug(f"Loaded custom CA bundle: {self.ssl_verify}")
            except FileNotFoundError:
                self._logger.error(f"CA bundle not found: {self.ssl_verify}")
                raise
            except ssl.SSLError as e:
                self._logger.error(f"Error loading CA bundle: {e}")
                raise
        # else: ssl_verify=True, use defaults (CERT_REQUIRED + system CA bundle)

        # Optionally disable hostname checking (independent of cert verification)
        if not self.verify_hostname:
            context.check_hostname = False
            self._logger.warning(
                "Hostname verification disabled. "
                "This weakens security and should only be used for testing."
            )

        return context

    async def _rate_limit_domain(self, url: str, delay: float) -> None:
        """Enforce per-domain rate limiting using asyncio.Lock.

        Ensures delay seconds pass between requests to same domain.
        """
        import time

        domain = urlparse(url).netloc

        # Get or create lock for domain
        if domain not in self._domain_locks:
            self._domain_locks[domain] = asyncio.Lock()

        async with self._domain_locks[domain]:
            now = time.time()
            last_time = self._last_request_time.get(domain, 0.0)
            time_since_last = now - last_time

            if time_since_last < delay:
                wait_time = delay - time_since_last
                self._logger.debug(
                    f"Rate limit: waiting {wait_time:.2f}s before {domain}"
                )
                await asyncio.sleep(wait_time)

            self._last_request_time[domain] = time.time()

    async def crawl_document_async(self, url: str) -> Document | None:
        """Fetch and parse a document with retries, with optional caching."""
        if not self.session:
            raise RuntimeError(
                "Crawler.session not initialized. "
                "Use 'async with Crawler(...) as crawler:' context manager."
            )

        # Check cache first. Non-default fetchers get their own namespace so a
        # cached raw HTTP shell never satisfies a request for a rendered page.
        cache_ns = None if self.fetcher.name == HttpFetcher.name else self.fetcher.name
        if self.cache:
            cached = await self.cache.get(url, namespace=cache_ns)
            if cached:
                self._logger.debug(f"Cache hit for {url}")
                final_url = cached.final_url or url
                doc = self.parse_document(url, cached.content, base_url=final_url)
                doc.status_code = cached.status_code
                doc.response_headers = cached.response_headers
                doc.fetcher = cached.fetcher
                doc.final_url = final_url
                return doc

        # Check robots.txt before fetching
        if self.respect_robots_txt and self.robots_manager:
            if not await self.robots_manager.is_allowed(url):
                self._logger.info(f"Disallowed by robots.txt: {url}")
                doc = Document(url, None)
                doc.status_code = 403
                return doc

        # Get effective delay (robots.txt or configured)
        if self.respect_robots_txt and self.robots_manager:
            delay = await self.robots_manager.get_crawl_delay(url)
        else:
            delay = self.request_delay

        # Fetch with retries. Transient errors and 5xx responses are retried
        # with exponential backoff; other failures return immediately. The
        # per-domain rate limit applies to every attempt, not just the first,
        # so a retry never hits the host sooner than the configured delay.
        headers = {"User-Agent": self.user_agent}
        result: FetchResult | None = None
        for attempt in range(self.max_retries):
            last_attempt = attempt >= self.max_retries - 1
            await self._rate_limit_domain(url, delay)
            try:
                self._logger.debug(f"Fetching {url} (attempt {attempt + 1})")
                result = await self.fetcher.fetch(url, headers)
            except TransientFetchError as e:
                if last_attempt:
                    self._logger.error(
                        f"Failed to fetch {url} after {self.max_retries} attempts: {e}"
                    )
                    return None
                await self._backoff(url, attempt, f"Transient error: {e}")
                continue
            except FetchError as e:
                self._logger.error(f"Client error while fetching {url}: {e}")
                return None
            except Exception as e:
                self._logger.error(f"Unexpected error while fetching {url}: {e}")
                raise

            if 500 <= result.status < 600 and not last_attempt:
                await self._backoff(url, attempt, f"HTTP {result.status}")
                continue
            break

        if result is None:  # pragma: no cover - max_retries < 1
            return None

        final_url = url
        if result.final_url:
            final_url = self.normalize_url(
                result.final_url, keep_hash_routes=self.keep_hash_routes
            )
            if final_url != url:
                self._logger.info(f"Redirected: {url} -> {final_url}")

        if result.status != 200:
            self._logger.error(f"Failed to fetch {url}: HTTP {result.status}")
            doc = Document(url, None)
            doc.status_code = result.status
            doc.response_headers = result.headers
            doc.fetcher = result.fetcher
            doc.final_url = final_url
            return doc

        doc = self.parse_document(url, result.body, base_url=final_url)
        doc.status_code = result.status
        doc.response_headers = result.headers
        doc.fetcher = result.fetcher
        doc.final_url = final_url

        # Cache successful responses
        if self.cache and result.body is not None:
            await self.cache.set(
                url,
                result.status,
                result.headers,
                result.body,
                namespace=cache_ns,
                fetcher=result.fetcher,
                final_url=final_url if final_url != url else None,
            )

        return doc

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff for ``attempt`` (0-based), with equal jitter.

        Base delay is ``2**attempt * backoff_factor``. With jitter enabled the
        actual wait is uniformly drawn from [base/2, base], so concurrent
        retries against one host spread out instead of landing together.
        """
        base = float(2**attempt * self.backoff_factor)
        if not self.backoff_jitter:
            return base
        return base / 2 + random.uniform(0, base / 2)

    async def _backoff(self, url: str, attempt: int, reason: str) -> None:
        """Log and sleep before retrying ``url`` after ``attempt`` (0-based)."""
        wait_time = self._backoff_delay(attempt)
        self._logger.warning(
            f"{reason} fetching {url} "
            f"(attempt {attempt + 1}/{self.max_retries}). "
            f"Retrying in {wait_time:.1f}s..."
        )
        await asyncio.sleep(wait_time)

    async def discover_sitemap_urls(self, base_url: str) -> list[str]:
        """Discover page URLs from the site's sitemaps.

        Uses ``Sitemap:`` declarations from robots.txt when available, otherwise
        falls back to the conventional ``/sitemap.xml`` location.
        """
        if not self.session:
            raise RuntimeError(
                "Crawler.session not initialized. "
                "Use 'async with Crawler(...) as crawler:' context manager."
            )

        from linktrace.sitemap import SitemapParser

        robots_sitemaps: list[str] = []
        if self.respect_robots_txt and self.robots_manager:
            robots_sitemaps = await self.robots_manager.get_sitemaps(base_url)

        parser = SitemapParser(self.session, self.user_agent, self._logger)
        return await parser.discover(base_url, robots_sitemaps or None)

    def parse_document(
        self, url: str, source: str | None, base_url: str | None = None
    ) -> Document:
        """Parse ``source`` into a Document for ``url``.

        ``base_url`` is the URL the content was actually served from (after
        redirects). Relative links are resolved against it and internal vs
        external classification uses its host, so a ``www`` -> apex redirect
        does not turn every link on the site into an "external" one.
        """
        base = base_url or url
        self._protocol_ = urlparse(base).scheme or "http"
        self.base_uri = urlparse(base).netloc

        doc = Document(url, source)
        doc.final_url = base
        if source is None:
            return doc

        try:
            dom = lxml.html.fromstring(source)
            if url not in self.visited_urls:
                self.visited_urls.add(url)

            doc.dom = dom

            title_element = dom.xpath("//title/text()")
            if title_element:
                doc.title = title_element[0].strip()

            skip_words = ["#", "\r", "\n", " ", "&amp;"]
            links = [
                link
                for link in dom.xpath("//a/@href/..")
                if link.attrib["href"]
                and (
                    link.attrib["href"][:1] not in skip_words
                    or self._is_hash_route(link.attrib["href"])
                )
            ]

            # Use local list per document to avoid state leakage
            found_links: list[HtmlLink] = []
            for link in links:
                link_url = link.attrib["href"]
                link_url = self.normalize_url(
                    urljoin(base, link_url), keep_hash_routes=self.keep_hash_routes
                )
                if urlparse(link_url).scheme not in ["http", "https", "ftp"]:
                    continue

                if "javascript:" not in link_url:
                    title = "".join(link.xpath("./text()")).strip()
                    if (
                        link_url not in self.visited_urls
                        and link_url not in self._queue
                    ):
                        found_links.append(HtmlLink(link_url, title))

            doc.internal_links = [
                link
                for link in found_links
                if self.get_domain_parts(link.url) == self.get_domain_parts(base)
                or link.url[:1] == "/"
                or link.url[:1] == ""
            ]
            doc.internal_links = list(dict.fromkeys(doc.internal_links))

            doc.external_links = [
                link
                for link in found_links
                if self.get_domain_parts(link.url) != self.get_domain_parts(base)
                and urlparse(link.url).scheme != ""
            ]
            doc.external_links = list(dict.fromkeys(doc.external_links))

            doc.links = doc.internal_links + doc.external_links

            for link in doc.links:
                self.queue_link(link.url)
        except lxml.etree.ParserError:
            # Empty or whitespace-only body: a valid page with nothing to parse.
            self._logger.debug(f"Empty document at {url}")
        except lxml.etree.XMLSyntaxError:
            self._logger.error(
                f"XMLSyntaxError: Invalid source document or truncated source at {url}"
            )
            self._broken_links.append(BrokenLink(url, 0))

        return doc

    def relative_to_full(self, url: str) -> str:
        return urljoin(f"{self._protocol_}://{self.base_uri}", url)

    def queue_link(self, link: str) -> None:
        if link not in self.visited_urls and link not in self._queue:
            self._queue.append(link)

    def _is_hash_route(self, href: str) -> bool:
        """True if ``href`` is a hash-router path we have been told to keep."""
        return self.keep_hash_routes and href[:2] in ("#/", "#!")

    @staticmethod
    def normalize_url(url: str, keep_hash_routes: bool = False) -> str:
        """Strip fragments and normalize an empty path to '/'.

        With ``keep_hash_routes=True``, fragments that look like client-side
        routes (``#/about``, ``#!/about``) are preserved so hash-router SPAs
        keep one URL per route instead of collapsing to the bare page.
        """
        base, fragment = urldefrag(url)
        parsed = urlparse(base)
        if parsed.netloc and not parsed.path:
            parsed = parsed._replace(path="/")
        if keep_hash_routes and fragment[:1] in ("/", "!"):
            parsed = parsed._replace(fragment=fragment)
        return parsed.geturl()

    @staticmethod
    def get_domain_parts(url: str) -> str:
        return urlparse(url).netloc
