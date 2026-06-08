# WebCrawler

Lightweight async web crawler for link analysis and HTML document processing.

**Perfect for:** Site structure analysis, link tracking, concurrent page fetching, HTML document transformation.

**Not:** A replacement for Scrapy. Use this when you need simple, focused crawling with automatic link classification and clean document models.

## Key Features

- ⚡ **Async/await native** — Built on asyncio + aiohttp for concurrent requests
- 🔗 **Automatic link classification** — Distinguishes internal vs external links by domain
- 📄 **Rich document model** — Full HTML source, parsed links, metadata, headers
- 🔄 **Persistent sessions** — Connection pooling for 10-100x faster same-domain crawls
- 🔁 **Retries + backoff** — Exponential backoff for transient errors (timeouts, 5xx)
- ⏱️ **Rate limiting** — Per-domain rate limiting with asyncio.Lock, no thundering herd
- 🤖 **robots.txt support** — Automatically respect Crawl-delay directives per domain
- 🔍 **Broken link tracking** — Audit 404s and 5xx errors for site structure validation
- 💾 **Optional caching** — Disk-based cache (1-day TTL) for repeat crawls
- 🔐 **SSL verification** — Secure by default, with corporate proxy support
- 🍪 **Automatic cookies** — Set-Cookie extraction and sending built-in
- 🔀 **Traversal strategies** — BFS (broad) or DFS (deep) crawling
- 📊 **Multi-format export** — JSON, Pandas, Polars, PyArrow for data analysis
- 📍 **Callbacks & streaming** — Process results as crawled without memory buildup

## Quick Start

```python
import asyncio
from WebCrawler import Spider

async def main():
    spider = Spider(start_url="https://example.com", max_depth=2)
    documents = await spider.run_async()
    
    for doc in documents:
        print(f"{doc.url}")
        print(f"  Internal links: {len(doc.internal_links)}")
        print(f"  External links: {len(doc.external_links)}")

asyncio.run(main())
```

## Installation

```bash
pip install webcrawler
```

**Optional export formats:**
```bash
pip install webcrawler[serializers]  # pandas + polars + pyarrow
pip install webcrawler[pandas]       # Just pandas
```

## Core Concepts

### Spider
High-level orchestrator that crawls multiple pages using BFS (breadth-first) or DFS (depth-first) traversal.

### Crawler
Low-level engine that fetches and parses individual documents. Handles retries, caching, SSL, cookies, sessions.

### Document
Rich object containing:
- `url` — page URL
- `title` — HTML title tag
- `source` — raw HTML
- `internal_links` — links to same domain
- `external_links` — links to other domains
- `status_code`, `response_headers`, `domain` — metadata

See [Core Concepts](docs/core-concepts.md) for more.

## Configuration

### Basic Crawl

```python
spider = Spider(
    start_url="https://example.com",
    max_depth=3,              # How deep to follow links
    traversal_strategy="bfs"  # "bfs" (default) or "dfs"
)
documents = await spider.run_async()
```

### Retries & Timeouts

```python
spider = Spider(
    start_url="https://example.com",
    request_timeout=15,       # Seconds per request (default: 30)
    max_retries=5,            # Retry transient errors (default: 3)
)
```

### Caching

```python
spider = Spider(
    start_url="https://example.com",
    cache_dir=".webcrawler_cache"  # Enable disk caching (default: None/disabled)
)
# 2nd run will be 10-50x faster for same URLs
```

### SSL & Corporate Proxies

```python
# Default: verify SSL with system CA
spider = Spider(start_url="https://example.com")

# Corporate proxy with custom CA bundle
spider = Spider(
    start_url="https://example.com",
    ssl_verify="/path/to/corporate-ca.pem"
)

# Self-signed certs (testing only)
spider = Spider(
    start_url="https://example.com",
    ssl_verify=False  # ⚠️ Insecure
)
```

Cookies are handled automatically — no configuration needed.

### Callbacks: Process Results in Real-Time

For large crawls, avoid memory buildup by processing documents as they're crawled:

```python
# Stream results to disk
async def save_result(doc):
    with open("results.jsonl", "a") as f:
        f.write(json.dumps({"url": doc.url, "title": doc.title}) + "\n")

spider = Spider(
    start_url="https://example.com",
    on_page_crawled=save_result,
    accumulate_results=False,  # Don't keep in memory
)
await spider.run_async()  # Returns [], file has results
```

**Callback Hooks:**
- `on_page_crawled(doc)` — Called after each successful crawl. Return value accumulated if `accumulate_results=True`
- `on_error(url, exc)` — Called on crawl failures
- `on_crawl_complete()` — Called when crawl finishes (cleanup hook)

**Async Callbacks Supported:**
```python
async def save_to_db(doc):
    await db.insert(doc.url, doc.title)
    return doc.url

spider = Spider(
    start_url="https://example.com",
    on_page_crawled=save_to_db,       # Async callback
    accumulate_results=True,
)
results = await spider.run_async()  # Returns list of URLs
```

**Return Logic:**
- No callback → returns all documents (default)
- Callback + `accumulate_results=False` → returns [] (streaming mode)
- Callback + `accumulate_results=True` → returns callback results

### Traversal Strategies

**BFS (Breadth-First) — Default**
```python
# Explores level by level: all depth-1 links, then depth-2, etc.
spider = Spider(start_url="https://example.com", max_depth=3, traversal_strategy="bfs")
```

**DFS (Depth-First)**
```python
# Follows single paths all the way down before exploring siblings
spider = Spider(start_url="https://example.com", max_depth=5, traversal_strategy="dfs")
```

Use DFS for deep hierarchies (documentation sites, nested directories). Use BFS for broad exploration.

### Rate Limiting & robots.txt

By default, WebCrawler automatically respects robots.txt `Crawl-delay` directives and enforces per-domain rate limiting:

```python
# Automatic robots.txt respect (default)
spider = Spider(
    start_url="https://example.com",
    user_agent="MyBot/1.0",  # Identifies your bot to robots.txt rules
)
await spider.run_async()
```

Customize rate limiting:

```python
# Enforce explicit delay (ignores robots.txt)
spider = Spider(
    start_url="https://example.com",
    request_delay=1.0,           # 1 second between requests to same domain
    respect_robots_txt=False,    # Don't fetch robots.txt
)

# Concurrent requests to different domains, serialized to same domain
await spider.run_async()
```

### Broken Link Audit

Track 404s and 5xx errors for site maintenance:

```python
spider = Spider(start_url="https://example.com", max_depth=2)
documents = await spider.run_async()

for doc in documents:
    # Broken internal links (fix these first!)
    for broken in doc.broken_internal_links:
        print(f"{doc.url} → {broken.url} (HTTP {broken.status_code})")
    
    # Broken external links (check if still valid)
    for broken in doc.broken_external_links:
        print(f"External: {broken.url} (HTTP {broken.status_code})")
```

Stream broken links in real-time:

```python
async def audit_broken(doc):
    broken_count = len(doc.broken_internal_links) + len(doc.broken_external_links)
    if broken_count > 0:
        print(f"{doc.url}: {broken_count} broken links")

spider = Spider(
    start_url="https://example.com",
    on_page_crawled=audit_broken,
    accumulate_results=False,
)
await spider.run_async()
```

### Export Data

```python
from WebCrawler import Spider, Serializers

spider = Spider(start_url="https://example.com", max_depth=2)
documents = await spider.run_async()

# Export to JSON
serializer = Serializers(documents)
serializer.to_json("crawl.json", include_html=False)

# Export to Pandas (one row per link)
df = serializer.to_pandas()
print(df[["url", "title", "link_url", "link_type"]])

# Export to Polars (faster for large datasets)
df_polars = serializer.to_polars()

# Export to PyArrow (for data pipelines)
table = serializer.to_arrow()
```

### Link Analysis

```python
from collections import Counter

spider = Spider(start_url="https://example.com", max_depth=2)
documents = await spider.run_async()

# Count external domains
external_domains = Counter()
for doc in documents:
    for link in doc.external_links:
        domain = link.url.split("/")[2]
        external_domains[domain] += 1

print(external_domains.most_common(10))
```

See [Examples](docs/examples.md) for more patterns.

## Notebooks

Interactive examples in `notebooks/`:
- `crawl_cnn.ipynb` — Crawls CNN.com, analyzes link structure, demonstrates all export formats

## API Reference

See [API Reference](docs/api-reference.md) for complete method documentation.

## Troubleshooting

### "SSL: CERTIFICATE_VERIFY_FAILED"
Use `ssl_verify=False` for self-signed certs (testing only), or `ssl_verify="/path/to/ca.pem"` for corporate proxies.

### "Too many connections"
Reduce concurrency by lowering `max_retries` or increase timeouts. Default settings are conservative.

### "Crawler hits timeout on deep sites"
Try DFS traversal instead of BFS, or increase `request_timeout`.

See [Troubleshooting](docs/troubleshooting.md) for more.

## Performance

Typical performance (single-domain crawl):
- **First run:** ~50-500ms per page (network-bound)
- **Cached run:** ~1-10ms per page (2-50x faster)
- **Memory:** ~1MB per 100 pages

With persistent sessions + connection pooling, same-domain requests are 10-100x faster than per-request session setup.

## Architecture

```
Spider (orchestrator)
  └─ Crawler (persistent session)
      ├─ aiohttp (HTTP requests + connection pooling)
      ├─ lxml (HTML parsing)
      ├─ ResponseCache (optional disk caching)
      └─ CookieJar (automatic cookie handling)
```

Spider manages the crawl queue and traversal. Crawler handles individual document fetching/parsing. All requests share one persistent aiohttp session per Spider instance.

## Why WebCrawler?

**vs Scrapy:** Lightweight, focused, simpler API for link analysis. Scrapy is better for complex extraction pipelines.

**vs requests + BeautifulSoup:** Built-in async concurrency, automatic session reuse, retries, caching. Better for crawling multiple pages.

**vs Selenium:** Pure HTTP crawler (no JS execution). Faster, lighter, but can't handle dynamic sites.

## Testing

```bash
just test          # Run all tests
just test-cov      # Run with coverage report
```

All 91 tests pass. 100% of core crawling paths tested (rate limiting, broken link tracking, robots.txt, callbacks).

## Contributing

Bug reports and pull requests welcome on GitHub.

## License

MIT

---

**Documentation:**
- [Getting Started](docs/getting-started.md)
- [Core Concepts](docs/core-concepts.md)
- [API Reference](docs/api-reference.md)
- [Examples](docs/examples.md)
- [Troubleshooting](docs/troubleshooting.md)
