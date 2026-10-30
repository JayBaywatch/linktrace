# linktrace

[![PyPI - Version](https://img.shields.io/pypi/v/linktrace?color=blue)](https://pypi.org/project/linktrace/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/linktrace)](https://pypi.org/project/linktrace/)
[![Tests](https://github.com/JayBaywatch/linktrace/actions/workflows/tests.yml/badge.svg)](https://github.com/JayBaywatch/linktrace/actions/workflows/tests.yml)
[![Documentation](https://readthedocs.org/projects/linktrace/badge/?version=latest)](https://linktrace.readthedocs.io/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![GitHub](https://img.shields.io/badge/GitHub-JayBaywatch/linktrace-blue?logo=github)](https://github.com/JayBaywatch/linktrace)

LinkTrace is a document-oriented crawler. Every crawled page becomes a rich Document object containing metadata, content, and discovered relationships.

**Perfect for:** Site structure analysis, link tracking, concurrent page fetching, HTML document transformation.

**Not:** A Scrapy replacement. Scrapy is a powerful full-featured framework — linktrace is deliberately lightweight with no pipelines, middleware, or project scaffolding to configure. If you want crawling results in minutes rather than hours of setup, and a gentler learning curve, linktrace is for you.

## Key Features

- ⚡ **Async/await native** — Built on asyncio + aiohttp for concurrent requests
- 🔗 **Automatic link classification** — Distinguishes internal vs external links by domain
- 🎯 **URL filtering rules** — Include/exclude by regex, path prefix, extension, query param, or domain
- 🎚️ **Configurable concurrency** — Tune `max_concurrency` and connection-pool limits for throughput
- 🗺️ **Sitemap discovery** — Seed from `sitemap.xml` / robots.txt `Sitemap:`, including nested indexes
- 🧭 **Pluggable fetchers** — Plain HTTP by default; optional headless-browser rendering (Playwright) for JavaScript SPAs, or route per URL with automatic escalation
- 📄 **Rich document model** — Full HTML source, parsed links, metadata, headers
- 🔄 **Persistent sessions** — Connection pooling for 10-100x faster same-domain crawls
- 🔁 **Retries + backoff** — Jittered exponential backoff for timeouts, connection errors and 5xx responses
- 🛡️ **Guard rails** — Response size limit, redirect tracking (links resolve against the served URL), O(1) frontier, pruned cache with a size cap
- ⏱️ **Rate limiting** — Per-domain rate limiting with asyncio.Lock, no thundering herd
- 🤖 **robots.txt support** — Automatically respect Crawl-delay directives and Disallow rules per domain
- 🔍 **Broken link tracking** — Audit 404s and 5xx errors for site structure validation
- 💾 **Optional caching** — Disk-based cache (configurable TTL and size cap, pruned on start) for repeat crawls
- 🔐 **SSL verification** — Secure by default, with corporate proxy support
- 🍪 **Automatic cookies** — Set-Cookie extraction and sending built-in
- 🔀 **Traversal strategies** — BFS (broad) or DFS (deep) crawling
- 📊 **Multi-format export** — JSON, Pandas, Polars, PyArrow for data analysis
- 📍 **Callbacks & streaming** — Process results as crawled without memory buildup
- 🗂️ **Flush to disk** — `flush_to="crawl.jsonl"` streams every page to a JSONL file for crawls too big for RAM

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

In a plain script you can skip the event loop boilerplate with
`documents = Spider("https://example.com").run()`. For a JavaScript-rendered
site add `fetcher=RoutingFetcher()`; for a crawl too big for memory add
`flush_to="crawl.jsonl"`. Both are covered below.

## Installation

```bash
pip install linktrace
```

**Optional export formats:**
```bash
pip install linktrace[serializers]  # pandas + polars + pyarrow
pip install linktrace[pandas]       # Just pandas
```

**Optional JavaScript rendering (SPAs):**
```bash
pip install linktrace[browser]      # Playwright
playwright install chromium         # one-time browser download
```

## Core Concepts

### Spider
High-level orchestrator that crawls multiple pages using BFS (breadth-first) or DFS (depth-first) traversal.

### Crawler
Low-level engine that fetches and parses individual documents. Handles retries, caching, SSL, cookies, sessions.

### Document
Rich object containing:
- `url` — page URL as requested; `final_url` — where it was actually served after redirects
- `title` — HTML title tag
- `source` — raw HTML, or the rendered DOM when a browser fetcher produced it
- `fetcher` — `"http"`, `"browser"`, or your own fetcher's name
- `internal_links` / `external_links` — `HtmlLink` objects (`url`, `text`), classified by domain
- `broken_internal_links` — `BrokenLink` objects for internal links whose target returned 4xx/5xx (filled after the crawl)
- `status_code`, `response_headers`, `domain` — metadata

### CrawlRules
Declarative include/exclude policy for which discovered URLs the Spider follows (regex, path prefix, extension, query param, domain). Passed as `Spider(rules=...)`.

### SitemapParser
Fetches and parses XML sitemaps (urlsets and nested indexes). Used when `Spider(use_sitemaps=True)`, or directly for sitemap inspection.

### Fetchers
The pluggable "get me the page" step. `HttpFetcher` (default) uses aiohttp; `BrowserFetcher` renders pages in headless Chromium; `RoutingFetcher` tries HTTP first and escalates to the browser only for pages that look like un-rendered SPA shells (the `looks_like_spa_shell` heuristic). Passed as `Spider(fetcher=...)`. Subclass `Fetcher` and return a `FetchResult` to plug in any other transport; raise `TransientFetchError` for failures the crawler should retry.

See [Core Concepts](https://github.com/JayBaywatch/linktrace/blob/main/docs/core-concepts.md) for more.

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

### URL Filtering Rules

By default the spider follows every internal link until `max_depth` is reached.
Pass a `CrawlRules` object to keep the crawl focused and skip crawl traps (login
pages, sort/calendar links, binaries, off-site domains):

```python
from linktrace import Spider, CrawlRules

rules = CrawlRules(
    allowed_domains=["realty.example.com"],      # stay on-site (subdomain-aware)
    include_path_prefixes=["/homes-for-sale/"],  # only follow listing pages...
    exclude_path_prefixes=["/login", "/privacy"],# ...never these
    blocked_extensions=["pdf", "jpg", "png"],    # documents, not downloads
    exclude_query_params=["sort", "page"],        # avoid faceted-search explosion
    exclude_patterns=[r"/print/?$"],              # regex escape hatch
)

spider = Spider("https://realty.example.com/", max_depth=4, rules=rules)
```

A populated *allow* list (`allowed_domains`, `include_path_prefixes`,
`allowed_extensions`, `include_patterns`) is a whitelist; a *block*/*exclude*
list rejects matches. **Exclusions always win**, and an empty `CrawlRules()`
(the default) allows everything. `rules.allows(url)` is pure and unit-testable.

### Concurrency

```python
spider = Spider(
    start_url="https://example.com",
    max_concurrency=50,            # URLs fetched per batch (default: 10)
    max_connections=200,           # total aiohttp pool size (default: 100)
    max_connections_per_host=8,    # connections to one host (default: 10)
)
```

Raise `max_concurrency` / `max_connections` to go faster across **many** hosts;
keep `max_connections_per_host` modest (and pair with `request_delay` or
`respect_robots_txt=True`) to stay polite to any single server.

### Sitemap Discovery

Seed the queue from a site's published document inventory before link-following
begins. linktrace reads `Sitemap:` declarations from robots.txt (falling back to
`/sitemap.xml`), follows sitemap indexes and nested sitemaps, and filters every
discovered URL through your `CrawlRules`:

```python
spider = Spider(
    start_url="https://realty.example.com/",
    max_depth=2,
    use_sitemaps=True,   # discover URLs from sitemap.xml / robots.txt Sitemap:
    rules=rules,
)
documents = await spider.run_async()
```

Sitemap discovery is best-effort — if none exists, ordinary link-following still
runs. You can also inspect sitemaps directly via `SitemapParser` or
`Crawler.discover_sitemap_urls(base_url)`.

### JavaScript-Rendered Sites (SPAs)

Plain HTTP only sees the empty shell of a React/Vue/Angular app. Swap the
fetcher to render pages in a headless browser (requires `linktrace[browser]`):

```python
from linktrace import Spider, BrowserFetcher, RoutingFetcher

# Render everything in headless Chromium
spider = Spider(
    start_url="https://app.example.com/",
    fetcher=BrowserFetcher(wait_until="networkidle", max_pages=4),
)

# Cheaper: plain HTTP first, browser only for pages that look like SPA shells
spider = Spider(
    start_url="https://app.example.com/",
    fetcher=RoutingFetcher(),
)
documents = await spider.run_async()
print({doc.url: doc.fetcher for doc in documents})   # "http" or "browser"
```

`RoutingFetcher` also takes `render_patterns=[r"/search"]` to send matching
URLs straight to the browser. Robots.txt, rate limiting, retries and caching
apply identically whichever fetcher is used. For hash-router apps
(`/#/listings/42`) add `keep_hash_routes=True` so each route is its own URL.

Not sure whether a site needs rendering? Probe it:

```python
from linktrace import Crawler, looks_like_spa_shell

async with Crawler() as crawler:
    result = await crawler.fetcher.fetch("https://app.example.com/", {})
    print(looks_like_spa_shell(result))   # True → plain HTTP only sees the shell
```

### Bring Your Own Transport

Any client can plug in. Subclass `Fetcher`, return a `FetchResult`, and raise
`TransientFetchError` for failures the crawler should retry. Robots.txt,
rate limiting, retries, caching and parsing all keep working:

```python
from linktrace import Spider, Fetcher, FetchResult, TransientFetchError

class MyFetcher(Fetcher):
    name = "mine"

    async def open(self, ctx):          # optional: ctx has the shared aiohttp
        self.client = make_client(ctx)  # session, timeout, user agent, SSL setting

    async def fetch(self, url, headers):
        status, body = await self.client.get(url, headers)
        if status == 429:
            raise TransientFetchError("rate limited")
        return FetchResult(url, status, body=body if status == 200 else None,
                           fetcher=self.name)

spider = Spider("https://example.com", fetcher=MyFetcher())
```

### Guard Rails for Long Crawls

Defaults are tuned to run unattended against large or badly behaved sites.
Every knob is adjustable:

```python
spider = Spider(
    start_url="https://example.com",
    max_response_bytes=10 * 1024 * 1024,  # drop bodies over 10 MiB (default); None = no limit
    max_retries=3,                        # jittered exponential backoff on timeouts and 5xx
    cache_dir=".linktrace_cache",
    cache_ttl=86400,                      # seconds an entry stays valid (default 1 day)
    cache_max_bytes=2 * 1024**3,          # evict oldest entries past 2 GiB, on start
    show_progress=True,                   # tqdm bar with visited/pending counts
)
```

Redirects are followed and recorded: `doc.final_url` is where the page was
served, relative links resolve against it, and the redirect target is marked
visited so it is never fetched twice.

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
- Callback + `accumulate_results=False` → returns [] (streaming mode; documents are not retained)
- Callback + `accumulate_results=True` → returns callback results

### Large Crawls: Flush to Disk

For crawls that won't fit in memory, stream each page to a JSONL file as soon
as it's crawled. Nothing is retained in RAM beyond the URL bookkeeping:

```python
spider = Spider(
    start_url="https://example.com",
    max_depth=5,
    flush_to="crawl.jsonl",   # one JSON object per line, same schema as to_json()
    flush_html=False,         # True to include page source
)
await spider.run_async()      # returns []
```

Streaming and flushing default to `retain_documents=False`; pass
`retain_documents=True` to keep the `Document` list as well. If a line cannot
be written (disk full, file removed) the crawl stops with a `FlushError`
instead of finishing with rows silently missing.

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

# Which pages link to broken internal pages (populated after the crawl)
for doc in documents:
    for broken in doc.broken_internal_links:
        print(f"{doc.url} -> {broken.url} (HTTP {broken.status_code})")
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
- `crawl_cnn_callbacks.ipynb` — Memory-efficient streaming with callbacks, and the one-argument `flush_to` alternative
- `crawl_tax_assessor.ipynb` — Crawls a municipal property/GIS site, with callbacks and aggregation
- `config_rules_sitemaps.ipynb` — URL filtering rules, configurable concurrency, sitemap discovery, crawling a JavaScript-rendered SPA with `RoutingFetcher`, and flushing a crawl to JSONL

## API Reference

See [API Reference](https://github.com/JayBaywatch/linktrace/blob/main/docs/api-reference.md) for complete method documentation.

## Troubleshooting

### "SSL: CERTIFICATE_VERIFY_FAILED"
Use `ssl_verify=False` for self-signed certs (testing only), or `ssl_verify="/path/to/ca.pem"` for corporate proxies.

### "Too many connections"
Lower `max_concurrency` and/or `max_connections_per_host` to reduce parallel
requests, and consider adding a `request_delay`. Defaults are conservative.

### "Crawler hits timeout on deep sites"
Try DFS traversal instead of BFS, or increase `request_timeout`.

### "No links found on a JavaScript app"
Use `fetcher=RoutingFetcher()` or `fetcher=BrowserFetcher()` (requires `pip install linktrace[browser]` and `playwright install chromium`).

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
  └─ Crawler (robots.txt, rate limiting, retries, cache, parsing)
      ├─ Fetcher (pluggable transport)
      │   ├─ HttpFetcher     — aiohttp (default)
      │   ├─ BrowserFetcher  — Playwright / headless Chromium
      │   └─ RoutingFetcher  — HTTP first, browser on escalation
      ├─ aiohttp session (connection pooling, cookies, SSL; also robots + sitemaps)
      ├─ lxml (HTML parsing)
      └─ ResponseCache (optional disk caching)
```

Spider manages the crawl queue and traversal. Crawler handles individual document fetching/parsing and delegates the transport to a Fetcher. All HTTP requests share one persistent aiohttp session per Spider instance, so connection pooling, cookies, SSL configuration, and DNS caching are reused across the crawl.

## Why linktrace?

Scrapy is an excellent full crawling and extraction framework, built around a
job that was common ten years ago: pull specific fields out of pages and push
them through item pipelines. Most crawling in AI and data projects today is a
different job. You want the **pages themselves** as documents (for a RAG corpus,
an underwriting model's property data, an LLM agent's research step), you want
them in a notebook or a dataframe or a JSONL file in minutes, and the sources
are increasingly JavaScript apps.

`linktrace` is built for that job:

| | linktrace | Scrapy |
|---|---|---|
| **First crawl** | One constructor call, `await spider.run_async()` | Project scaffold, a Spider class, `settings.py`, a CLI run |
| **Output** | `Document` objects, JSONL, pandas / polars / arrow | `Item`s through pipelines you write |
| **JavaScript sites** | `fetcher=RoutingFetcher()`; renders only pages that need it | `scrapy-playwright` plugin, reactor swap, per-request `meta` |
| **Runs inside your app** | Native asyncio; `await` it from a FastAPI handler, an agent loop, or Jupyter | Twisted reactor; embedding in an existing event loop takes care |
| **Memory on big crawls** | `flush_to="crawl.jsonl"` streams to disk, nothing retained | Items stream through pipelines |
| **Politeness** | robots.txt (incl. `Crawl-delay`), per-domain rate limit, pool limits | `ROBOTSTXT_OBEY`, `DOWNLOAD_DELAY`, AutoThrottle |
| **Guard rails** | Size limit, jittered retries, redirect-aware dedupe, pruned cache | Mature equivalents via settings and middleware |
| **Learning surface** | Two classes and a handful of keyword arguments | Spiders, requests, responses, items, loaders, pipelines, middleware, settings |

Each crawled URL becomes a `Document` with the page source (raw or rendered),
title, status, headers, domain, classified links, which fetcher produced it,
and where redirects actually landed. Everything you need to decide whether a
page belongs in a corpus is on the object, and every export carries it along.

One persistent `aiohttp` session per crawl carries connection pooling,
cookies, SSL configuration, timeouts, per-host limits and DNS caching across
requests, so same-domain crawls stay fast without tuning.

**Use Scrapy when:** you need a mature extraction framework with item
pipelines, middleware, a scheduler, distributed back ends and a large plugin
ecosystem, or when your deliverable is structured fields rather than pages.

**Use linktrace when:** your deliverable is a set of documents and their
links, you want results in a notebook or a data pipeline today, the sources
may be JavaScript apps, and you would rather await a crawl from your own code
than run a framework around it.

**vs requests + BeautifulSoup:** Built-in async concurrency, automatic session reuse, retries, caching, rate limiting, and structured document objects. Better for crawling multiple pages.

**vs Selenium / bare Playwright:** HTTP by default (fast, light), with an optional headless-browser fetcher for JavaScript-rendered sites. You get rendering *plus* the crawl machinery (queue, robots.txt, rate limiting, retries, caching, exports) instead of scripting a browser by hand.

## Testing

```bash
just test          # Run all tests
just test-cov      # Run with coverage report
```

All 196 tests pass. 100% of core crawling paths tested (rate limiting, broken link tracking, robots.txt, callbacks, URL filtering rules, sitemap discovery, fetchers, flushing, size limits, redirects, cache pruning). Browser tests run against a local page in headless Chromium and skip automatically when Playwright is not installed.

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
