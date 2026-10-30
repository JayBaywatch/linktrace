# Core Concepts

## Architecture Overview

linktrace has three main components plus a pluggable transport:

```
┌─────────────────────────────────────────────────┐
│ Spider (Orchestrator)                           │
│ - Manages crawl queue (to_visit)                │
│ - Tracks visited pages                          │
│ - Implements BFS or DFS traversal               │
│ - Returns Documents, or flushes them to disk    │
└──────────────────┬──────────────────────────────┘
                   │
                   │ creates one persistent
                   │
┌──────────────────▼──────────────────────────────┐
│ Crawler (Crawl Engine)                          │
│ - robots.txt + per-domain rate limiting         │
│ - Retries with exponential backoff              │
│ - Caching (optional)                            │
│ - Link parsing / classification                 │
│ - Persistent aiohttp session (SSL, cookies)     │
└──────────────────┬──────────────────────────────┘
                   │ delegates "get the page" to
                   │
┌──────────────────▼──────────────────────────────┐
│ Fetcher (Transport)                             │
│ - HttpFetcher    → aiohttp (default)            │
│ - BrowserFetcher → Playwright headless Chromium │
│ - RoutingFetcher → HTTP, escalate to browser    │
└─────────────────────────────────────────────────┘
```

## Spider

The **Spider** is the main entry point. It orchestrates crawling a website.

```python
spider = Spider(
    start_url="https://example.com",
    max_depth=3,
    traversal_strategy="bfs"  # or "dfs"
)
documents = await spider.run_async()
```

### Attributes
- `start_url` — Starting URL for crawl
- `max_depth` — How many levels deep to follow links
- `traversal_strategy` — "bfs" (breadth-first) or "dfs" (depth-first)
- `visited` — Set of visited URLs
- `to_visit` — Queue of (url, depth) tuples waiting to be crawled
- `documents` — List of Document objects (results)

### Methods
- `run_async()` — Async crawl, returns list of Documents
- `run()` — Sync crawl (blocking), returns list of Documents

### Internal Logic

1. Pop URL from `to_visit` queue (FIFO for BFS, LIFO for DFS)
2. Skip if visited or exceeds max_depth
3. Tell Crawler to fetch + parse the URL
4. Add returned Document to results
5. Extract internal links, add to queue
6. Repeat until queue empty

## Crawler

The **Crawler** handles individual document fetching and parsing. Manages:
- HTTP requests via aiohttp
- Connection pooling (`max_connections=100` total, `max_connections_per_host=10`, both configurable)
- Retries with exponential backoff
- Caching (optional)
- SSL verification
- Automatic cookie handling

### Usage

```python
from linktrace import Crawler

async with Crawler(ssl_verify=True, cache_dir=".cache") as crawler:
    doc = await crawler.crawl_document_async("https://example.com")
```

### Retry Logic

Transient errors (timeouts, connection errors, 5xx responses) are retried with exponential backoff. If every attempt returns 5xx, the last response is returned as a Document with that `status_code`:

```
wait_time = 2^attempt * backoff_factor

Attempt 1: wait 2s
Attempt 2: wait 4s  
Attempt 3: wait 8s
Attempt 4: fail
```

Default: 3 retries, backoff_factor=2.

### SSL Verification

- **Default (ssl_verify=True):** Verify cert with system CA bundle (secure)
- **Corporate proxy (ssl_verify="/path/to/ca.pem"):** Verify cert with custom CA
- **Self-signed (ssl_verify=False):** Skip verification (⚠️ insecure, testing only)

### Cookies

Cookies are handled automatically:
- Set-Cookie response headers extracted
- Cookies sent on subsequent requests to same domain
- Persists across all requests in a single crawl
- Does NOT persist across separate Spider runs (in-memory only)

### Caching

Optional disk-based cache:

```python
crawler = Crawler(cache_dir=".webcrawler_cache")
```

- Responses stored as `{cache_dir}/{url_hash}.json`
- Default TTL: 1 day
- Expired entries auto-deleted on retrieval
- Highly effective for repeat crawls (2-50x speedup)
- Non-default fetchers get their own namespace, so a cached raw HTTP shell is
  never served to a crawl that asked for a rendered page

## Fetchers

The **Fetcher** is the one step of a crawl that talks to the outside world:
given a URL, return a status, headers and body. Everything the Crawler does
around it (robots.txt, rate limiting, retries, caching, parsing) is transport
agnostic, so swapping the fetcher is the only change needed to crawl sites
plain HTTP cannot handle.

```python
from linktrace import Spider, HttpFetcher, BrowserFetcher, RoutingFetcher

Spider(url)                               # HttpFetcher() — the default
Spider(url, fetcher=BrowserFetcher())     # render every page in headless Chromium
Spider(url, fetcher=RoutingFetcher())     # HTTP first, browser when it looks like an SPA
```

### HttpFetcher (default)

One `GET` per URL through the Crawler's shared aiohttp session. Timeouts and
connection errors are raised as `TransientFetchError` so the Crawler retries
them; other client errors are `FetchError` and are not retried.

### BrowserFetcher

Renders each page in a headless browser via [Playwright](https://playwright.dev)
and returns the resulting DOM. Requires `pip install linktrace[browser]` and a
one-time `playwright install chromium`. Playwright is imported only when the
fetcher is opened, so the core package never depends on it.

- One browser and one browser context are shared for the whole crawl; each
  fetch opens a tab, navigates, waits, serialises the DOM and closes the tab.
- `max_pages` (default 4) caps concurrent tabs **independently** of the
  Spider's `max_concurrency`, because a rendered page costs far more than an
  HTTP request.
- `wait_until="networkidle"` (default) is the most reliable choice for SPAs.
  Sites with long-polling connections never go idle; use
  `wait_until="domcontentloaded"` plus `wait_for_selector="a[href]"` there.
- Images, media and fonts are blocked by default (`block_resources`) so pages
  render faster. Pass `block_resources=()` to load everything.
- `ignore_https_errors` follows the Crawler's `ssl_verify=False`.

Rendered pages have real anchors when the app uses a router (React Router,
Vue Router, Angular Router, Next.js). Apps that navigate only through click
handlers expose nothing to extract and remain out of reach.

### RoutingFetcher

Sends every URL to `default` (plain HTTP) first, then re-fetches with
`fallback` (the browser) when the response looks like an un-rendered SPA
shell. The built-in `looks_like_spa_shell` heuristic checks for a `<noscript>`
mentioning JavaScript, an empty mount element such as `<div id="root"></div>`,
or a page with no anchors but a script bundle.

```python
RoutingFetcher(
    render_patterns=[r"/search", r"/map"],   # always render these
    route=lambda url: "?q=" in url,          # or decide in code
    escalate=looks_like_spa_shell,           # None disables escalation
)
```

`routing.escalations` counts how many pages were re-fetched. The browser is
only launched when the fetcher is opened, but Playwright must still be
installed if any URL may reach it.

### Which fetcher produced a Document

`Document.fetcher` records the name (`"http"`, `"browser"`, or a custom
fetcher's name) and the serializers export it as a `fetcher` column, so a
DataFrame can tell rendered rows from raw ones. With `BrowserFetcher`,
`Document.source` is the rendered DOM rather than the raw response.

### Hash-router apps

URL normalization strips fragments, so `/#/about` and `/#/contact` would
collapse into one page. Pass `keep_hash_routes=True` to keep fragments that
start with `#/` or `#!` as distinct URLs (plain in-page anchors like `#top`
are still dropped).

### Writing your own fetcher

Subclass `Fetcher` and implement `fetch`. `open`/`close` are optional hooks
called once per crawl with a `FetchContext` (the shared aiohttp session,
timeout, user agent and SSL setting).

```python
from linktrace import Fetcher, FetchResult, TransientFetchError

class CurlImpersonateFetcher(Fetcher):
    name = "curl"

    async def fetch(self, url, headers):
        status, body = await my_client.get(url, headers)   # your transport
        if status == 429:
            raise TransientFetchError("rate limited")      # Crawler retries
        return FetchResult(url, status, body=body if status == 200 else None,
                           fetcher=self.name)
```

Robots.txt and sitemap fetches always use plain HTTP regardless of fetcher.

## Document

The **Document** object represents a crawled page.

```python
class Document:
    url: str                    # Page URL
    title: str                  # HTML <title> tag
    source: str                 # Raw HTML
    status_code: int            # HTTP status (200, 404, etc)
    response_headers: dict      # HTTP response headers
    fetcher: str                # "http", "browser", or a custom fetcher name
    domain: str                 # Domain extracted via tldextract
    internal_links: List[Link]  # Links to same domain
    external_links: List[Link]  # Links to other domains
    links: List[Link]           # All links (internal + external)
    broken_internal_links: List[BrokenLink]  # Internal links whose target returned 4xx/5xx
```

`broken_internal_links` is filled in once the crawl finishes, from the status
codes of the pages actually visited. External links are never fetched, so
`broken_external_links` stays empty.

### HtmlLink

```python
class HtmlLink:
    url: str                    # Link URL (absolute)
    text: str                   # Link text (anchor text)
    schema: str                 # Protocol (http, https, etc)
```

### Example

```python
for doc in documents:
    print(f"Title: {doc.title}")
    print(f"Status: {doc.status_code}")
    print(f"Domain: {doc.domain}")
    
    for link in doc.internal_links:
        print(f"  Internal: {link.url} → '{link.text}'")
    
    for link in doc.external_links:
        print(f"  External: {link.url} → '{link.text}'")
```

## Traversal Strategies

### BFS (Breadth-First Search) — Default

```
Level 0: start_url
         ↓
Level 1: [all links from start_url]
         ↓
Level 2: [all links from level 1 pages]
         ↓
Level 3: [all links from level 2 pages]
```

**Pros:**
- Natural depth-limiting (discovers shallow links first)
- Balanced memory use
- Good for broad site exploration

**Cons:**
- Queue can grow large for wide sites
- Slower for deep hierarchies

**Use when:** Exploring general site structure, shallow links matter more

### DFS (Depth-First Search)

```
Start at url1 → follows links deep
            → when blocked, backtracks
            → explores url2 → deep again
```

**Pros:**
- Memory-efficient for wide/shallow sites
- Explores complete subtrees
- Good for hierarchical sites

**Cons:**
- Can hit slow/hanging pages on deep branches
- May take longer to find diverse links

**Use when:** Crawling documentation, nested directories, exploring single paths

## URL Filtering Rules

By default the Spider follows every internal link it discovers until `max_depth`
is reached. On real-world sites this pulls in login pages, faceted-search
variants, calendars, binaries, and other crawl traps. `CrawlRules` lets you
declare exactly which URLs to follow:

```python
from linktrace import Spider, CrawlRules

rules = CrawlRules(
    allowed_domains=["realty.example.com"],     # stay on-site (subdomain-aware)
    include_path_prefixes=["/homes-for-sale/"], # only listing pages
    exclude_path_prefixes=["/login", "/cart"],  # skip these sections
    blocked_extensions=["pdf", "jpg", "zip"],   # documents, not downloads
    exclude_query_params=["sort", "page"],       # avoid faceted-search explosion
    exclude_patterns=[r"/print/?$"],             # regex escape hatch
)
spider = Spider("https://realty.example.com/", rules=rules)
```

### How rules are evaluated

Rules are checked against each **discovered** link before it is queued (the
`start_url` itself is always fetched). For each dimension:

- A populated *allow* list (`allowed_domains`, `include_path_prefixes`,
  `allowed_extensions`, `include_patterns`) acts as a **whitelist** — the URL
  must match at least one entry.
- A *block*/*exclude* list rejects any URL that matches.
- **Exclusions always win**: if a URL matches both an include and an exclude, it
  is excluded.

An empty `CrawlRules()` (the default) allows everything, so existing crawls are
unaffected. Regexes are pre-compiled once and matched against the full URL;
extension checks are case-insensitive with an optional leading dot; domain
checks match subdomains and ignore the port.

## Sitemap Discovery

Link-following only finds pages reachable from the `start_url`. Many sites
publish their full document inventory as an XML sitemap — ideal for a crawler
positioned around document discovery. Set `use_sitemaps=True` to seed the queue
from it before link-following begins:

```python
spider = Spider("https://realty.example.com/", use_sitemaps=True, rules=rules)
```

The Spider:

1. Reads `Sitemap:` declarations from `robots.txt` (falling back to
   `/sitemap.xml` if none are declared).
2. Fetches each sitemap, following **sitemap indexes** and **nested sitemaps**
   (with loop, depth, and count guards).
3. Normalizes every discovered URL, filters it through your `CrawlRules`, and
   seeds it at **depth 0** — so the sitemap URLs *and* their own links are
   crawled within `max_depth`.

Sitemap discovery is best-effort: if no sitemap exists or fetching fails, the
crawl proceeds with ordinary link-following. You can also call
`Crawler.discover_sitemap_urls(base_url)` or use `SitemapParser` directly to
inspect a site's sitemaps without crawling.

## Connection Pooling

Both BFS and DFS benefit from persistent sessions:

```python
# GOOD: One session, connection reuse (10-100x faster)
spider = Spider(start_url="https://example.com")
await spider.run_async()

# vs

# BAD: New session per request (default in many libraries)
# Slow handshake/TLS negotiation for each request
```

linktrace reuses one persistent session across all requests in a single crawl. Same-domain requests are dramatically faster.

## Error Handling

### Transient Errors (retried)
- Timeout
- Connection reset
- 5xx responses

### Non-transient Errors (not retried)
- 4xx responses (invalid URL, etc)
- DNS failures
- SSL errors

Failed requests log errors but don't crash the crawl. Document is returned with status_code and empty links.

## Memory Model

Memory usage scales with:
- Number of pages (each Document ~100KB with HTML; rendered DOMs from
  `BrowserFetcher` are typically several times larger)
- Queue size (larger for BFS on wide sites)
- Cache size (if enabled)

Typical: ~1MB per 100 pages.

By default every `Document` (including its HTML) is kept until the crawl
finishes. Two options change that:

- **Streaming callbacks.** With `on_page_crawled` set and
  `accumulate_results=False`, documents are handed to your callback and then
  released: `source` and `dom` are cleared and nothing is appended to
  `spider.documents`.
- **Flush to disk.** `flush_to="crawl.jsonl"` appends each page as one JSON
  object per line (the same schema as `Serializers.to_json`; add
  `flush_html=True` to include the source) as soon as it is crawled, and
  likewise retains nothing.

Both set `retain_documents=False` implicitly; pass `retain_documents=True` to
keep the in-memory list as well. `broken_internal_links` is only computed for
retained documents.

To reduce memory further:
- Use DFS instead of BFS (smaller queue)
- Disable caching
- Lower max_depth

## Concurrency Model

Spider creates tasks concurrently but processes results sequentially:

```python
# Pseudocode
while to_visit:
    # Create tasks for up to max_concurrency queue items (concurrent HTTP)
    tasks = [crawler.fetch(url) for url, depth in to_visit[:max_concurrency]]
    
    # Wait for all tasks (concurrent)
    results = await gather(*tasks)
    
    # Process results (sequential - add new links to queue)
    for doc in results:
        add_internal_links_to_queue(doc)
```

This means: **up to `max_concurrency` HTTP requests happen concurrently, but
link discovery is sequential per batch.**

### Tuning concurrency

Three parameters control throughput:

- `max_concurrency` (default 10) — how many URLs are fetched per batch.
- `max_connections` (default 100) — total size of the aiohttp connection pool.
- `max_connections_per_host` (default 10) — simultaneous connections to a single host.

```python
spider = Spider(
    start_url="https://example.com",
    max_concurrency=50,            # larger fan-out
    max_connections=200,           # bigger pool
    max_connections_per_host=8,    # but polite to any one host
)
```

Raise `max_concurrency` and `max_connections` to go faster across **many**
hosts; keep `max_connections_per_host` modest (and pair with `request_delay` or
`respect_robots_txt=True`) to avoid overwhelming a single server.

With `BrowserFetcher`, rendered fetches are additionally capped by its own
`max_pages` (default 4), so a batch of 50 URLs still opens at most 4 tabs at a
time.
