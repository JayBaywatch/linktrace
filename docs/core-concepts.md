# Core Concepts

## Architecture Overview

linktrace has three main components:

```
┌─────────────────────────────────────────────────┐
│ Spider (Orchestrator)                           │
│ - Manages crawl queue (to_visit)                │
│ - Tracks visited pages                          │
│ - Implements BFS or DFS traversal               │
│ - Returns collection of Documents               │
└──────────────────┬──────────────────────────────┘
                   │
                   │ creates one persistent
                   │
┌──────────────────▼──────────────────────────────┐
│ Crawler (HTTP Engine)                           │
│ - Persistent aiohttp session                    │
│ - Connection pooling                            │
│ - Retries with exponential backoff              │
│ - Caching (optional)                            │
│ - SSL verification                              │
│ - Cookie jar                                    │
└──────────────────┬──────────────────────────────┘
                   │
        ┌──────────┼──────────┐
        │          │          │
    ┌───▼──┐  ┌───▼──┐  ┌───▼──┐
    │aiohttp  │  lxml   │  Cache  │
    │ (HTTP)  │ (parse) │ (disk)  │
    └────────┘  └────────┘  └────────┘
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

Transient errors (timeouts, connection errors, 5xx responses) are retried with exponential backoff:

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

## Document

The **Document** object represents a crawled page.

```python
class Document:
    url: str                    # Page URL
    title: str                  # HTML <title> tag
    source: str                 # Raw HTML
    status_code: int            # HTTP status (200, 404, etc)
    response_headers: dict      # HTTP response headers
    domain: str                 # Domain extracted via tldextract
    internal_links: List[Link]  # Links to same domain
    external_links: List[Link]  # Links to other domains
    links: List[Link]           # All links (internal + external)
```

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
- Number of pages (each Document ~100KB with HTML)
- Queue size (larger for BFS on wide sites)
- Cache size (if enabled)

Typical: ~1MB per 100 pages.

To reduce memory:
- Disable HTML in Document: don't store `doc.source`
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
