# linktrace

[![PyPI - Version](https://img.shields.io/pypi/v/linktrace)](https://pypi.org/project/linktrace/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/linktrace)](https://pypi.org/project/linktrace/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![GitHub](https://img.shields.io/badge/GitHub-JayBaywatch/linktrace-blue?logo=github)](https://github.com/JayBaywatch/linktrace)

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
- 🤖 **robots.txt support** — Automatically respect Crawl-delay directives and Disallow rules per domain
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
from linktrace import Spider

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
pip install linktrace
```

**Optional export formats:**
```bash
pip install linktrace[serializers]  # pandas + polars + pyarrow
pip install linktrace[pandas]       # Just pandas
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
    cache_dir=".linktrace_cache"  # Enable disk caching (default: None/disabled)
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

By default, linktrace automatically respects robots.txt `Crawl-delay` directives and `Disallow` rules, enforcing per-domain rate limiting:

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

### Track Crawl Status

Monitor which pages returned error status codes:

```python
spider = Spider(start_url="https://example.com", max_depth=2)
documents = await spider.run_async()

# Find pages with error responses
error_pages = [doc for doc in documents if doc.status_code >= 400]
for doc in error_pages:
    print(f"Error: {doc.url} (HTTP {doc.status_code})")

# Monitor disallowed pages (403 from robots.txt)
disallowed = [doc for doc in documents if doc.status_code == 403]
print(f"Disallowed by robots.txt: {len(disallowed)} pages")
```

Stream crawl status in real-time:

```python
async def track_errors(doc):
    if doc.status_code >= 400:
        print(f"❌ {doc.url} (HTTP {doc.status_code})")

spider = Spider(
    start_url="https://example.com",
    on_page_crawled=track_errors,
    accumulate_results=False,
)
await spider.run_async()
```

### Export Data

```python
from linktrace import Spider, Serializers

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

See [Examples](https://github.com/JayBaywatch/linktrace/blob/main/docs/examples.md) for more patterns.

## Notebooks

Interactive examples in `notebooks/`:
- `crawl_cnn.ipynb` — Crawls CNN.com, analyzes link structure, demonstrates all export formats

## API Reference

See [API Reference](https://github.com/JayBaywatch/linktrace/blob/main/docs/api-reference.md) for complete method documentation.

## Troubleshooting

### "SSL: CERTIFICATE_VERIFY_FAILED"
Use `ssl_verify=False` for self-signed certs (testing only), or `ssl_verify="/path/to/ca.pem"` for corporate proxies.

### "Too many connections"
Reduce concurrency by lowering `max_retries` or increase timeouts. Default settings are conservative.

### "Crawler hits timeout on deep sites"
Try DFS traversal instead of BFS, or increase `request_timeout`.

See [Troubleshooting](https://github.com/JayBaywatch/linktrace/blob/main/docs/troubleshooting.md) for more.

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

Spider manages the crawl queue and traversal. Crawler handles individual document fetching/parsing. All requests share one persistent aiohttp session per Spider instance, so connection pooling, cookies, SSL configuration, and DNS caching are reused across the crawl.

## Why linktrace?

Scrapy is an excellent full crawling and extraction framework. `linktrace` is designed for a narrower job: fast async link analysis with minimal setup.

Instead of building a Scrapy project around spiders, requests, responses, callbacks, items, pipelines, middleware, and settings, `linktrace` gives you a direct document-centric API. Each crawled URL becomes a `Document` object containing the page source, title, status code, response headers, domain, internal links, external links, and crawl status metadata.

That makes `linktrace` useful when your goal is to inspect site structure, trace links, audit crawl status, or export crawl results to dataframe-oriented tools without creating a larger scraping project.

`linktrace` also reuses a persistent `aiohttp` session during a crawl. Connection pooling, cookie reuse, SSL configuration, request timeouts, per-host limits, and DNS caching are carried across requests, which can make repeated same-domain crawls much faster than creating a fresh client/session per URL.

**Use Scrapy when:** you need a mature scraping framework with item pipelines, middleware, schedulers, broad ecosystem support, and complex extraction workflows.

**Use linktrace when:** you want a focused async crawler that turns URLs into analyzable `Document` objects with automatic link classification and simple exports.

**vs requests + BeautifulSoup:** Built-in async concurrency, automatic session reuse, retries, caching, rate limiting, and structured document objects. Better for crawling multiple pages.

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
- [Getting Started](https://github.com/JayBaywatch/linktrace/blob/main/docs/getting-started.md)
- [Core Concepts](https://github.com/JayBaywatch/linktrace/blob/main/docs/core-concepts.md)
- [API Reference](https://github.com/JayBaywatch/linktrace/blob/main/docs/api-reference.md)
- [Examples](https://github.com/JayBaywatch/linktrace/blob/main/docs/examples.md)
- [Troubleshooting](https://github.com/JayBaywatch/linktrace/blob/main/docs/troubleshooting.md)
