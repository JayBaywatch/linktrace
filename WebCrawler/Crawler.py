import asyncio
import logging
import ssl
from urllib.parse import urljoin, urlparse

import aiohttp
import lxml.html
import tldextract

from WebCrawler.cache import ResponseCache


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
        self.status_code: int = 0
        self.response_headers: dict[str, str] = {}
        self.dom: object = None

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
    ) -> None:
        self._logger = logging.getLogger(log_name if log_name else __name__)
        self._logger.setLevel(log_level)
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

        # Caching (opt-in)
        self.cache: ResponseCache | None = (
            ResponseCache(cache_dir) if cache_dir else None
        )

        # Cookies handled automatically via CookieJar in session (created lazily)
        self._cookie_jar: aiohttp.CookieJar | None = None

    async def __aenter__(self) -> "Crawler":
        """Enter async context manager: create and setup session."""
        self.session = await self._create_session()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit async context manager: cleanup session."""
        if self.session:
            await self.session.close()

    async def _create_session(self) -> aiohttp.ClientSession:
        """Create persistent aiohttp session with SSL context, connector, timeouts."""
        # Create cookie jar now (requires event loop)
        if self._cookie_jar is None:
            self._cookie_jar = aiohttp.CookieJar()

        ssl_context = self._build_ssl_context()

        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=10,
            ttl_dns_cache=300,
            ssl=ssl_context,
        )

        session = aiohttp.ClientSession(
            connector=connector,
            cookie_jar=self._cookie_jar,
            timeout=aiohttp.ClientTimeout(total=self.request_timeout),
        )

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

    async def crawl_document_async(self, url: str) -> Document | None:
        """Fetch and parse a document with retries, with optional caching."""
        if not self.session:
            raise RuntimeError(
                "Crawler.session not initialized. "
                "Use 'async with Crawler(...) as crawler:' context manager."
            )

        # Check cache first
        if self.cache:
            cached = await self.cache.get(url)
            if cached:
                self._logger.debug(f"Cache hit for {url}")
                doc = self.parse_document(url, cached.content)
                doc.status_code = cached.status_code
                doc.response_headers = cached.response_headers
                return doc

        # Implement retry logic manually (tenacity works better with functions)
        for attempt in range(self.max_retries):
            try:
                async with self.session.get(url) as response:
                    self._logger.debug(f"Fetching {url} (attempt {attempt + 1})")
                    status = response.status
                    headers = dict(response.headers)

                    if status != 200:
                        self._logger.error(f"Failed to fetch {url}: HTTP {status}")
                        doc = Document(url, None)
                        doc.status_code = status
                        doc.response_headers = headers
                        return doc

                    html = await response.text()

                doc = self.parse_document(url, html)
                doc.status_code = status
                doc.response_headers = headers

                # Cache successful responses
                if self.cache:
                    await self.cache.set(url, status, headers, html)

                return doc

            except (
                TimeoutError,
                aiohttp.ClientConnectorError,
                aiohttp.ServerTimeoutError,
            ) as e:
                if attempt < self.max_retries - 1:
                    wait_time = 2**attempt * self.backoff_factor
                    self._logger.warning(
                        f"Transient error fetching {url} "
                        f"(attempt {attempt + 1}/{self.max_retries}): {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    self._logger.error(
                        f"Failed to fetch {url} after {self.max_retries} attempts: {e}"
                    )
            except aiohttp.ClientError as e:
                self._logger.error(f"Client error while fetching {url}: {e}")
                break
            except Exception as e:
                self._logger.error(f"Unexpected error while fetching {url}: {e}")
                raise

        return None

    def parse_document(self, url: str, source: str | None) -> Document:
        self._protocol_ = urlparse(url).scheme if not urlparse(url).scheme else "http"
        self.base_uri = urlparse(url).netloc

        doc = Document(url, source)
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
                if link.attrib["href"] and link.attrib["href"][:1] not in skip_words
            ]

            for link in links:
                link_url = link.attrib["href"]
                link_url = urljoin(url, link_url)
                if urlparse(link_url).scheme not in ["http", "https", "ftp"]:
                    continue

                if "javascript:" not in link_url:
                    title = "".join(link.xpath("./text()")).strip()
                    if (
                        link_url not in self.visited_urls
                        and link_url not in self._queue
                    ):
                        self._links.append(HtmlLink(link_url, title))

            doc.internal_links = [
                link
                for link in self._links
                if self.get_domain_parts(link.url) == self.get_domain_parts(doc.url)
                or link.url[:1] == "/"
                or link.url[:1] == ""
            ]
            doc.internal_links = list(dict.fromkeys(doc.internal_links))

            doc.external_links = [
                link
                for link in self._links
                if self.get_domain_parts(link.url) != self.get_domain_parts(doc.url)
                and urlparse(link.url).scheme != ""
            ]
            doc.external_links = list(dict.fromkeys(doc.external_links))

            doc.links = doc.internal_links + doc.external_links

            for link in doc.links:
                self.queue_link(link.url)
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

    @staticmethod
    def get_domain_parts(url: str) -> str:
        return urlparse(url).netloc
