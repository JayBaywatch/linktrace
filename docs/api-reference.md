# API Reference

## Spider

Main orchestrator for multi-page crawling.

### Constructor

```python
Spider(
    start_url: str,
    max_depth: int = 3,
    debug: bool = False,
    log_name: str = None,
    ssl_verify: bool | str = True,
    verify_hostname: bool = True,
    request_timeout: int = 30,
    cache_dir: str = None,
    max_retries: int = 3,
    traversal_strategy: str = "bfs",
    show_progress: bool = False,
    on_page_crawled: Callable[[Document], Any] = None,
    on_error: Callable[[str, Exception], None] = None,
    on_crawl_complete: Callable[[], None] = None,
    accumulate_results: bool = False,
    request_delay: float = 0.0,
    user_agent: str = "linktrace/<version>",
    respect_robots_txt: bool = True,
    max_concurrency: int = 10,
    max_connections: int = 100,
    max_connections_per_host: int = 10,
    rules: CrawlRules = None,
    use_sitemaps: bool = False,
    fetcher: Fetcher = None,
    keep_hash_routes: bool = False,
    flush_to: str = None,
    flush_html: bool = False,
    retain_documents: bool = None,
    max_response_bytes: int = 10_485_760,
    cache_ttl: int = 86400,
    cache_max_bytes: int = None
)
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `start_url` | str | — | URL to start crawling from (required) |
| `max_depth` | int | 3 | Maximum depth to follow links (0 = start_url only) |
| `debug` | bool | False | Enable debug logging (deprecated, use log_name) |
| `log_name` | str | None | Logger name for filtering logs |
| `ssl_verify` | bool\|str | True | SSL verification: True (system CA), False (skip), or path to CA cert |
| `verify_hostname` | bool | True | Verify certificate hostname matches domain |
| `request_timeout` | int | 30 | Timeout per request in seconds |
| `cache_dir` | str | None | Directory for disk cache (None = disabled) |
| `max_retries` | int | 3 | Retry transient errors up to N times |
| `traversal_strategy` | str | "bfs" | "bfs" (breadth-first) or "dfs" (depth-first) |
| `show_progress` | bool | False | Show tqdm progress bar with visited/pending counts |
| `on_page_crawled` | Callable | None | Callback after each page crawl. Supports sync and async. Return value accumulated if `accumulate_results=True` |
| `on_error` | Callable | None | Callback on crawl failure. Receives (url, exception) |
| `on_crawl_complete` | Callable | None | Callback when crawl finishes. Supports async for cleanup |
| `accumulate_results` | bool | False | If True, accumulate callback return values in results list |
| `request_delay` | float | 0.0 | Minimum seconds between requests to same domain (0 = no forced delay) |
| `user_agent` | str | "linktrace/<version>" | User-Agent header for requests (affects robots.txt rules). Default tracks the installed package version |
| `respect_robots_txt` | bool | True | Parse and respect robots.txt Crawl-delay directives |
| `max_concurrency` | int | 10 | Max URLs fetched concurrently per batch (must be ≥ 1) |
| `max_connections` | int | 100 | Total size of the aiohttp connection pool |
| `max_connections_per_host` | int | 10 | Max simultaneous connections to a single host |
| `rules` | CrawlRules | None | URL include/exclude policy for discovered links (None = allow all) |
| `use_sitemaps` | bool | False | Seed the queue from the site's sitemaps before link-following |
| `fetcher` | Fetcher | None | Transport used to fetch pages (None = `HttpFetcher()`). See [Fetchers](#fetchers) |
| `keep_hash_routes` | bool | False | Keep `#/...` and `#!...` fragments as distinct URLs (hash-router SPAs) |
| `flush_to` | str | None | Append each crawled page as one JSON line to this file as soon as it is crawled. A failed write raises `FlushError` and aborts the crawl |
| `flush_html` | bool | False | Include page source in flushed lines |
| `retain_documents` | bool | None | Keep `Document` objects in memory. Defaults to False when `flush_to` is set or a callback is used without `accumulate_results`, else True |
| `max_response_bytes` | int | 10 MiB | Largest page body a fetcher may buffer; bigger responses are dropped (not retried). `None` disables |
| `cache_ttl` | int | 86400 | Seconds a cache entry stays valid |
| `cache_max_bytes` | int | None | Cap on total cache size on disk; oldest entries are evicted when the Crawler starts |

**Raises:** `ValueError` if `max_concurrency < 1`.

### Methods

#### `async run_async() -> List[Document]`

Crawl asynchronously. **Preferred method.**

```python
spider = Spider(start_url="https://example.com")
documents = await spider.run_async()
```

**Returns:** List of Document objects

**Raises:**
- `ValueError` — If traversal_strategy is invalid

#### `run() -> List[Document]`

Crawl synchronously (blocking). A convenience wrapper around `run_async()` for
scripts.

```python
spider = Spider(start_url="https://example.com")
documents = spider.run()  # Blocks until complete
```

**Returns:** List of Document objects

**Raises:** `RuntimeError` if called from inside a running event loop (Jupyter,
an async application). Use `await spider.run_async()` there.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `start_url` | str | Starting URL |
| `max_depth` | int | Max crawl depth |
| `visited` | set | Set of visited URLs (includes redirect targets) |
| `to_visit` | deque | Frontier of (url, depth) tuples; BFS pops the left end, DFS the right |
| `documents` | list | Results (accumulated Documents) |
| `visited_count` | int | Number of pages successfully fetched |
| `traversal_strategy` | str | "bfs" or "dfs" |
| `on_page_crawled` | Callable \| None | Callback for each crawled page |
| `on_error` | Callable \| None | Callback for crawl errors |
| `on_crawl_complete` | Callable \| None | Callback on crawl completion |
| `accumulate_results` | bool | Whether to accumulate callback results |
| `accumulated_results` | list | Accumulated callback return values |
| `request_delay` | float | Minimum delay between requests to same domain |
| `user_agent` | str | User-Agent header value |
| `respect_robots_txt` | bool | Whether to respect robots.txt rules |
| `max_concurrency` | int | Max URLs fetched concurrently per batch |
| `max_connections` | int | Total aiohttp connection pool size |
| `max_connections_per_host` | int | Max connections to a single host |
| `rules` | CrawlRules | URL filtering policy (always a CrawlRules; empty allows all) |
| `use_sitemaps` | bool | Whether the queue is seeded from sitemaps |
| `fetcher` | Fetcher \| None | Fetcher passed to the Crawler (None = default HTTP) |
| `keep_hash_routes` | bool | Whether hash-router fragments are preserved |
| `flush_to` | str \| None | JSONL path pages are streamed to |
| `retain_documents` | bool | Whether Documents are kept in memory (resolved from the constructor args) |
| `max_response_bytes` | int \| None | Body size limit passed to the Crawler |
| `cache_ttl` | int | Cache TTL passed to the Crawler |
| `cache_max_bytes` | int \| None | Cache size cap passed to the Crawler |

### Callback Signature

```python
# Sync callback (simple file I/O, aggregation)
def on_page_crawled(doc: Document) -> Any:
    # Process document, return data to accumulate or None
    pass

# Async callback (database, HTTP, etc.)
async def on_page_crawled(doc: Document) -> Any:
    await db.insert(doc.url)
    return doc.url

# Error callback
def on_error(url: str, exception: Exception) -> None:
    logger.error(f"Failed: {url}: {exception}")

# Completion callback (async supported)
async def on_crawl_complete() -> None:
    await db.close()
```

### Return Behavior

| Callback | `accumulate_results` | Return Value | Documents retained? |
|----------|----------------------|--------------|---------------------|
| None | Any | List of all Documents | Yes |
| Provided | False | Empty list [] | No (streaming) |
| Provided | True | List of accumulated callback returns | Yes |

`flush_to` returns `[]` and retains nothing unless `retain_documents=True`.
When documents are not retained, `source` and `dom` are cleared after the
callback runs and `broken_internal_links` is not computed.

---

## Crawler

Low-level HTTP engine for fetching and parsing individual documents.

### Constructor

```python
Crawler(
    log_level: int = logging.DEBUG,
    log_name: str = None,
    ssl_verify: bool | str = True,
    verify_hostname: bool = True,
    request_timeout: int = 30,
    cache_dir: str = None,
    max_retries: int = 3,
    backoff_factor: int = 2,
    request_delay: float = 0.0,
    user_agent: str = "linktrace/<version>",
    respect_robots_txt: bool = True,
    max_connections: int = 100,
    max_connections_per_host: int = 10,
    fetcher: Fetcher = None,
    keep_hash_routes: bool = False,
    max_response_bytes: int = 10_485_760,
    backoff_jitter: bool = True,
    cache_ttl: int = 86400,
    cache_max_bytes: int = None
)
```

#### Parameters

Same as Spider, plus:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `log_level` | int | logging.DEBUG | Logging level |
| `backoff_factor` | int | 2 | Exponential backoff multiplier (base wait = 2^attempt * factor) |
| `backoff_jitter` | bool | True | Draw each wait uniformly from [base/2, base] so concurrent retries spread out |
| `max_response_bytes` | int | 10 MiB | Largest body a fetcher may buffer; `ResponseTooLarge` drops bigger pages. `None` disables |
| `cache_ttl` | int | 86400 | Seconds a cache entry stays valid |
| `cache_max_bytes` | int | None | Cap on total cache size; `prune()` runs on enter |
| `max_connections` | int | 100 | Total size of the aiohttp connection pool |
| `max_connections_per_host` | int | 10 | Max simultaneous connections to a single host |
| `fetcher` | Fetcher | None | Transport used to fetch pages (None = `HttpFetcher()`) |
| `keep_hash_routes` | bool | False | Keep `#/...` and `#!...` fragments as distinct URLs |

### Methods

#### `async __aenter__() -> Crawler`

Enter async context manager. Prunes the cache (if enabled), creates the
persistent aiohttp session, then calls `fetcher.open(FetchContext)`.

```python
async with Crawler(...) as crawler:
    doc = await crawler.crawl_document_async("https://example.com")
```

#### `async __aexit__(exc_type, exc_val, exc_tb)`

Exit async context manager. Calls `fetcher.close()`, then closes the session.

#### `async crawl_document_async(url: str) -> Document`

Fetch and parse a single document.

```python
async with Crawler() as crawler:
    doc = await crawler.crawl_document_async("https://example.com/page")
    print(doc.title)
    print(doc.internal_links)
```

**Parameters:**
- `url` (str) — URL to fetch

**Returns:** Document object

**Notes:**
- Checks cache first if `cache_dir` configured
- Retries `TransientFetchError` and 5xx responses up to `max_retries` times with jittered exponential backoff
- Returns Document even on 4xx/5xx (check `status_code`); returns `None` when every attempt failed with an error or the body exceeded `max_response_bytes`
- Follows redirects; `Document.final_url` holds the served URL and relative links are resolved against it
- Automatic cookie handling
- `Document.fetcher` names the fetcher that produced the page

#### `parse_document(url: str, source: str | None, base_url: str = None) -> Document`

Parse HTML into a Document without fetching. `base_url` (default `url`) is the
URL the content was served from: relative links resolve against it and the
internal/external split uses its host.

#### `static normalize_url(url: str, keep_hash_routes: bool = False) -> str`

Canonical form used for de-duplication: strips the fragment and normalizes an
empty path to `/`. With `keep_hash_routes=True`, fragments beginning with `#/`
or `#!` are kept so hash-router SPA routes stay distinct.

```python
Crawler.normalize_url("https://example.com#top")                        # "https://example.com/"
Crawler.normalize_url("https://example.com/#/about", keep_hash_routes=True)  # "https://example.com/#/about"
```

#### `async discover_sitemap_urls(base_url: str) -> List[str]`

Discover page URLs from the site's sitemaps. Reads `Sitemap:` declarations from
robots.txt when available (and `respect_robots_txt=True`), otherwise falls back
to `/sitemap.xml`. Follows sitemap indexes and nested sitemaps.

```python
async with Crawler() as crawler:
    urls = await crawler.discover_sitemap_urls("https://example.com/")
```

**Returns:** De-duplicated list of page URLs (discovery order preserved).

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `session` | aiohttp.ClientSession | HTTP session (None until context entered) |
| `fetcher` | Fetcher | The fetcher in use (an `HttpFetcher` by default) |
| `keep_hash_routes` | bool | Whether hash-router fragments are preserved |
| `cache` | ResponseCache | Cache object (None if cache_dir not set) |
| `ssl_verify` | bool\|str | SSL verification setting |
| `verify_hostname` | bool | Hostname verification setting |
| `request_timeout` | int | Request timeout in seconds |
| `max_retries` | int | Max retry attempts |
| `backoff_factor` | int | Exponential backoff multiplier |
| `backoff_jitter` | bool | Whether retry waits are jittered |
| `max_response_bytes` | int \| None | Body size limit handed to the fetcher |
| `max_connections` | int | Total aiohttp connection pool size |
| `max_connections_per_host` | int | Max connections to a single host |

---

## Fetchers

The pluggable transport used by the Crawler. All fetchers live in
`linktrace.fetchers` and are re-exported from `linktrace`.

### Fetcher (base class)

```python
class Fetcher(ABC):
    name: str = "custom"
    async def open(self, ctx: FetchContext) -> None: ...   # optional
    async def close(self) -> None: ...                     # optional
    async def fetch(self, url: str, headers: dict[str, str]) -> FetchResult: ...
```

Subclass it and implement `fetch`. `open`/`close` are called once per crawl
by the Crawler's context manager. Raise `TransientFetchError` for failures the
Crawler should retry and `FetchError` for those it should not. `name` is
recorded on `Document.fetcher` and namespaces cache entries.

### FetchResult

```python
FetchResult(url: str, status: int, headers: dict = {}, body: str | None = None, fetcher: str = "http", final_url: str | None = None)
```

`body` should be `None` for non-200 responses. `final_url` is the URL actually
served after redirects; the `redirected` property is true when it differs from
`url`. Fetchers that cannot tell leave it `None`.

### FetchContext

Passed to `Fetcher.open`:

| Attribute | Type | Description |
|-----------|------|-------------|
| `session` | aiohttp.ClientSession | The Crawler's shared session (pooling, cookies, SSL) |
| `request_timeout` | float | Per-request timeout in seconds |
| `user_agent` | str | User-Agent for the crawl |
| `ssl_verify` | bool \| str | The Crawler's SSL setting |
| `max_response_bytes` | int \| None | Body limit a fetcher must enforce by raising `ResponseTooLarge` |

### HttpFetcher

```python
HttpFetcher(session: aiohttp.ClientSession = None, *, max_response_bytes=<inherit>)
```

The default. One `GET` per URL through the Crawler's session (or the one
supplied). Rejects bodies over the size limit before buffering them: a
`Content-Length` above the limit is refused outright, otherwise the body is
streamed until EOF and abandoned as soon as it passes the limit. Reports the
served URL as `final_url` and logs redirect chains at DEBUG.
`max_response_bytes` overrides the Crawler's limit for this fetcher (`None`
disables). `name = "http"`.

An instance can be reused across crawls: it rebinds to each Crawler's session
on `open()` unless you passed your own `session`, which is then kept as is.

### BrowserFetcher

```python
BrowserFetcher(
    browser: "chromium" | "firefox" | "webkit" = "chromium",
    headless: bool = True,
    wait_until: "commit" | "domcontentloaded" | "load" | "networkidle" = "networkidle",
    wait_for_selector: str = None,
    settle_ms: int = 0,
    max_pages: int = 4,
    timeout: float = None,
    block_resources: Iterable[str] = ("image", "media", "font"),
    viewport: dict[str, int] = None,
    launch_args: list[str] = None,
    ignore_https_errors: bool = None,
)
```

Renders pages with Playwright. Requires `pip install linktrace[browser]` and
`playwright install chromium`. `name = "browser"`.

| Parameter | Description |
|-----------|-------------|
| `wait_until` | When navigation counts as done. `"networkidle"` suits SPAs; use `"domcontentloaded"` + `wait_for_selector` for long-polling sites |
| `wait_for_selector` | CSS selector to wait for after navigation (e.g. `"a[href]"`). Skipped on error responses (status >= 400) so a 404 does not wait out the timeout |
| `settle_ms` | Extra fixed wait after the above |
| `max_pages` | Max concurrent tabs, independent of the Spider's `max_concurrency` |
| `timeout` | Navigation timeout in seconds (defaults to the Crawler's `request_timeout`) |
| `block_resources` | Playwright resource types to abort; `()` loads everything |
| `ignore_https_errors` | Defaults to `True` only when the Crawler has `ssl_verify=False` |

**Raises:** `ImportError` from `open()` if Playwright is missing;
`RuntimeError` if the browser binary is not installed. Navigation timeouts are
raised as `TransientFetchError` (retried); other Playwright errors as
`FetchError`.

### RoutingFetcher

```python
RoutingFetcher(
    default: Fetcher = None,          # HttpFetcher()
    fallback: Fetcher = None,         # BrowserFetcher()
    render_patterns: Iterable[str] = (),
    route: Callable[[str], bool] = None,
    escalate: Callable[[FetchResult], bool] = looks_like_spa_shell,
)
```

Fetches with `default`, then re-fetches with `fallback` if `escalate(result)`
is true. URLs matching `render_patterns` or for which `route(url)` is true skip
`default`. `escalate=None` disables escalation. The `escalations` attribute
counts re-fetches. `name = "routing"`.

#### `needs_render(url: str) -> bool`

True if `url` is routed straight to `fallback`.

### `looks_like_spa_shell(result: FetchResult) -> bool`

Cheap regex heuristic for un-rendered SPA shells: a 200 body with a
`<noscript>` mentioning JavaScript, an empty mount element
(`<div id="root"></div>`, `#app`, `#__next`, ...), or no `<a href>` but an
external `<script src>`.

### Exceptions

- `FetchError` — non-retryable fetch failure.
- `TransientFetchError(FetchError)` — retried by the Crawler with backoff.
- `ResponseTooLarge(FetchError)` — body exceeded `max_response_bytes`; carries `url`, `limit` and (when known) `size`.

---

## CrawlRules

Declarative include/exclude policy for which discovered URLs the Spider follows.
Pass an instance as `Spider(rules=...)`. All fields are optional; an empty
`CrawlRules()` allows everything.

### Constructor

```python
CrawlRules(
    include_patterns: list[str] = [],
    exclude_patterns: list[str] = [],
    include_path_prefixes: list[str] = [],
    exclude_path_prefixes: list[str] = [],
    allowed_extensions: list[str] = [],
    blocked_extensions: list[str] = [],
    exclude_query_params: list[str] = [],
    allowed_domains: list[str] = [],
    blocked_domains: list[str] = []
)
```

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `include_patterns` | list[str] | Regexes; if non-empty, the URL must match at least one |
| `exclude_patterns` | list[str] | Regexes; any match rejects the URL |
| `include_path_prefixes` | list[str] | If non-empty, the path must start with one of these |
| `exclude_path_prefixes` | list[str] | Any path starting with one of these is rejected |
| `allowed_extensions` | list[str] | If non-empty, only these file extensions are kept (use `""` for extensionless paths) |
| `blocked_extensions` | list[str] | These file extensions are always rejected |
| `exclude_query_params` | list[str] | URLs carrying any of these query keys are rejected (sort/page/calendar traps) |
| `allowed_domains` | list[str] | If non-empty, the host must equal or be a subdomain of one of these |
| `blocked_domains` | list[str] | Host equalling or being a subdomain of one of these is rejected |

**Evaluation:** Deterministic, and **exclusions always win over inclusions**.
Domain matching is subdomain-aware and ignores the port. Extension comparison is
case-insensitive and a leading dot is optional (`"pdf"` and `".pdf"` are
equivalent).

### Methods

#### `allows(url: str) -> bool`

Return `True` if `url` passes every configured rule.

```python
rules = CrawlRules(exclude_path_prefixes=["/blog/"], blocked_extensions=["pdf"])
rules.allows("https://example.com/homes/1")     # True
rules.allows("https://example.com/blog/post")   # False
rules.allows("https://example.com/flyer.pdf")   # False
```

---

## SitemapParser

Fetches and parses XML sitemaps, returning the page URLs they list. Used
internally when `Spider(use_sitemaps=True)`, and usable directly for sitemap
inspection.

### Constructor

```python
SitemapParser(
    session: aiohttp.ClientSession,
    user_agent: str = "linktrace/<version>",
    logger: logging.Logger = None,
    max_sitemaps: int = 50,
    max_depth: int = 5
)
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | aiohttp.ClientSession | — | Session used to fetch sitemap documents |
| `user_agent` | str | "linktrace/<version>" | User-Agent sent with sitemap requests |
| `logger` | logging.Logger | None | Logger to use (defaults to module logger) |
| `max_sitemaps` | int | 50 | Hard cap on sitemap documents fetched (guards against huge indexes) |
| `max_depth` | int | 5 | Max nesting depth for sitemap-index recursion |

### Methods

#### `async discover(base_url: str, robots_sitemaps: list[str] = None) -> List[str]`

Discover page URLs for `base_url`. Uses `robots_sitemaps` when provided,
otherwise `{base_url}/sitemap.xml`. Follows sitemap indexes and nested sitemaps.

**Returns:** De-duplicated list of page URLs (discovery order preserved).

#### `static parse(content: bytes) -> tuple[str | None, list[str]]`

Parse sitemap XML bytes into `(kind, locs)` where `kind` is `"index"`,
`"urlset"`, or `None` (unparseable). Namespace-agnostic.

```python
kind, locs = SitemapParser.parse(b"<urlset><url><loc>https://x/a</loc></url></urlset>")
# ("urlset", ["https://x/a"])
```

---

## Document

Represents a crawled webpage.

### Constructor

```python
Document(url: str, source: str = None)
```

**Parameters:**
- `url` (str) — Page URL
- `source` (str) — Raw HTML (optional)

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `url` | str | Page URL (absolute) |
| `source` | str | Raw HTML response |
| `title` | str | HTML `<title>` tag content |
| `status_code` | int | HTTP status code |
| `response_headers` | dict | HTTP response headers |
| `fetcher` | str | Name of the fetcher that produced the page (`"http"`, `"browser"`, ...) |
| `final_url` | str | URL actually served after redirects (equals `url` when none) |
| `redirected` | bool | Read-only: `final_url != url` |
| `domain` | str | Domain extracted from URL (read-only property) |
| `internal_links` | List[HtmlLink] | Links to same domain (successful crawl) |
| `external_links` | List[HtmlLink] | Links to other domains (successful crawl) |
| `links` | List[HtmlLink] | All links (internal + external) |
| `broken_internal_links` | List[BrokenLink] | Internal links whose target page returned 4xx/5xx. Filled in by the Spider after the crawl, for retained documents. Links to a redirect target resolve too; a directly fetched status wins over one learned through a redirect |
| `broken_external_links` | List[BrokenLink] | Always empty: external links are not fetched |

### Properties

#### `domain: str` (read-only)

Domain extracted from URL using tldextract.

```python
doc.url = "https://www.example.com/page"
doc.domain  # "example"
```

---

## HtmlLink

Represents a link found in HTML.

### Constructor

```python
HtmlLink(url: str, text: str)
```

**Parameters:**
- `url` (str) — Link URL (absolute)
- `text` (str) — Anchor text

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `url` | str | Link destination URL |
| `text` | str | Anchor text (visible text in `<a>` tag) |

### Properties

#### `schema: str` (read-only)

URL scheme (http, https, ftp, etc).

#### `description: str` (read-only)

Alias for `text`.

### Methods

Supports standard Python comparisons:
- `==`, `!=` — Compare by URL
- `<`, `>` — Sort by URL
- `hash()` — Use in sets/dicts

---

## BrokenLink

Represents a link that returned an HTTP error status (4xx, 5xx).

### Constructor

```python
BrokenLink(url: str, status: int)
```

**Parameters:**
- `url` (str) — Link URL
- `status` (int) — HTTP status code (e.g., 404, 500)

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `url` | str | Link destination URL |
| `status_code` | int | HTTP error status code |
| `text` | str | String representation of status code |

**Note:** BrokenLink inherits from HtmlLink, so it supports the same comparison operations.

### Usage

```python
spider = Spider(start_url="https://example.com")
documents = await spider.run_async()

for doc in documents:
    if doc.broken_internal_links:
        print(f"Found {len(doc.broken_internal_links)} broken internal links:")
        for broken in doc.broken_internal_links:
            print(f"  {broken.url} - HTTP {broken.status_code}")
```

---

## Serializers

Export documents to multiple formats.

### Constructor

```python
Serializers(documents: List[Document])
```

**Parameters:**
- `documents` — List of Document objects

### Methods

#### `to_json(output_path: str, include_html: bool = False) -> None`

Export to JSON file with nested structure.

```python
serializer = Serializers(documents)
serializer.to_json("output.json", include_html=False)
```

**Parameters:**
- `output_path` (str) — Path to write JSON file
- `include_html` (bool) — Include raw HTML in output

**Example output:**
```json
[
  {
    "url": "https://example.com",
    "title": "Example",
    "status_code": 200,
    "domain": "example",
    "final_url": "https://example.com/",
    "fetcher": "http",
    "response_headers": {...},
    "internal_links": [{"url": "...", "text": "..."}],
    "external_links": [...]
  }
]
```

#### `to_pandas(include_html: bool = False) -> pd.DataFrame`

Export to pandas DataFrame with flattened links (one row per link).

```python
df = serializer.to_pandas()
print(df[["url", "title", "link_url", "link_type"]].head())
```

**Returns:** pandas DataFrame

**Columns:**
- `url`, `title`, `status_code`, `domain`, `final_url`, `fetcher`
- `link_url`, `link_text`, `link_type` (internal/external/None)
- `html` (if include_html=True)

#### `static document_to_dict(doc: Document, include_html: bool = False) -> dict`

The per-document structure used by `to_json` and by `Spider(flush_to=...)`,
one object per JSONL line.

**Notes:**
- One row per link
- Documents without links have one row with NULL link fields
- Requires `pip install pandas`

#### `to_polars(include_html: bool = False) -> pl.DataFrame`

Export to polars DataFrame (same schema as pandas, often faster).

**Returns:** polars DataFrame

**Requires:** `pip install polars`

#### `to_arrow(include_html: bool = False) -> pa.Table`

Export to PyArrow Table for data pipelines.

**Returns:** pyarrow Table

**Requires:** `pip install pyarrow`

---

## ResponseCache

Disk-based response caching (used internally by Crawler).

### Constructor

```python
ResponseCache(cache_dir: str, ttl_seconds: int = 86400, max_bytes: int = None)
```

**Parameters:**
- `cache_dir` (str) — Directory to store cache files
- `ttl_seconds` (int) — Time-to-live for entries (default: 1 day)
- `max_bytes` (int) — Optional cap on total size on disk, enforced by `prune()`

### Methods

#### `async get(url: str, *, namespace: str = None) -> CachedResponse | None`

Retrieve cached response if not expired. `namespace` selects a separate entry
for the same URL; the Crawler passes the fetcher name for non-default fetchers
and `None` for plain HTTP, so existing cache directories keep working.

#### `async set(url: str, status_code: int, headers: dict, content: str, *, namespace: str = None, fetcher: str = "http") -> None`

Store response in cache. `fetcher` and `final_url` are recorded and restored
onto the Document on a cache hit.

#### `async prune() -> int`

Delete entries older than `ttl_seconds` and, if `max_bytes` is set, the oldest
entries until the directory fits. Uses file modification times, so no entry is
parsed. The Crawler calls this once on enter. Returns the number of files
removed.

#### `async clear() -> None`

Clear all cache files.

---

## Exceptions

#### `ValueError`

Raised when:
- Invalid `traversal_strategy` (not "bfs" or "dfs")
- Missing required parameters
- SSL certificate not found

#### `CrawlException`

Raised for crawl-specific errors.

```python
class CrawlException(Exception):
    url: str        # URL that caused error
    message: str    # Error message
```

#### `FlushError`

Raised by `Spider.run_async()` when `flush_to` is set and a page cannot be
written (disk full, file removed, permissions). The crawl stops rather than
finishing with silently missing lines; the original `OSError` is available as
`__cause__`. Pages already written stay in the file, so the crawl can be
resumed by appending to it.

```python
from linktrace import FlushError

try:
    await spider.run_async()
except FlushError as e:
    print(f"Output incomplete: {e}")   # e.__cause__ is the OSError
```

Fetcher-level exceptions (`FetchError`, `TransientFetchError`,
`ResponseTooLarge`) are listed under [Fetchers](#exceptions).

---

## Logging

linktrace uses Python's standard logging module.

### Configure Logging

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Or specific logger
logger = logging.getLogger("linktrace.Spider")
logger.setLevel(logging.DEBUG)
```

### Log Levels

- **DEBUG:** Detailed traversal, cache hits/misses, retries
- **INFO:** Pages visited, crawl progress
- **WARNING:** SSL verification disabled, expired cache entries
- **ERROR:** Failed requests after retries, parse errors
