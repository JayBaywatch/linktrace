# Examples

## 1. Basic Crawl

Crawl a site and print all pages.

```python
import asyncio
from linktrace import Spider

async def main():
    spider = Spider(
        start_url="https://example.com",
        max_depth=2
    )
    documents = await spider.run_async()
    
    for doc in documents:
        print(f"{doc.url}")
        print(f"  Title: {doc.title}")
        print(f"  Status: {doc.status_code}")
        print(f"  Internal: {len(doc.internal_links)}")
        print(f"  External: {len(doc.external_links)}")
        print()

asyncio.run(main())
```

## 2. Analyze External Domains

Find the most common external domains linked from a site.

```python
from collections import Counter
from linktrace import Spider

async def main():
    spider = Spider(
        start_url="https://example.com",
        max_depth=1
    )
    documents = await spider.run_async()
    
    domains = Counter()
    for doc in documents:
        for link in doc.external_links:
            domain = link.url.split("/")[2]
            domains[domain] += 1
    
    print("Top external domains:")
    for domain, count in domains.most_common(10):
        print(f"  {domain}: {count} links")

asyncio.run(main())
```

## 3. Export to Pandas for Analysis

Crawl and export to DataFrame.

```python
from linktrace import Spider, Serializers

async def main():
    spider = Spider(start_url="https://example.com", max_depth=2)
    documents = await spider.run_async()
    
    serializer = Serializers(documents)
    df = serializer.to_pandas()
    
    # Analyze link types
    print(df['link_type'].value_counts())
    
    # Find pages with most external links
    print(df[df['link_type'] == 'external'].groupby('url').size().nlargest(5))
    
    # Export to CSV
    df.to_csv("crawl.csv", index=False)

asyncio.run(main())
```

## 4. Deep Crawling with DFS

Use depth-first search for hierarchical sites.

```python
from linktrace import Spider

async def main():
    spider = Spider(
        start_url="https://docs.example.com",
        max_depth=4,
        traversal_strategy="dfs"  # Depth-first
    )
    documents = await spider.run_async()
    
    # DFS explores deep before broad
    for doc in documents:
        depth = doc.url.count("/")
        print(f"{'  ' * depth}{doc.title}")

asyncio.run(main())
```

## 5. Caching for Repeated Crawls

First crawl fetches from network; second uses cache.

```python
from linktrace import Spider
import time

async def crawl():
    spider = Spider(
        start_url="https://example.com",
        max_depth=2,
        cache_dir=".webcrawler_cache"  # Enable caching
    )
    
    start = time.time()
    documents = await spider.run_async()
    elapsed = time.time() - start
    
    print(f"Crawled {len(documents)} pages in {elapsed:.2f}s")
    return documents

# First run: fetches from network (~5-30 seconds)
# documents = asyncio.run(crawl())

# Second run: uses cache (~0.5 seconds)
# documents = asyncio.run(crawl())
```

## 6. Handle SSL/Corporate Proxy

Different SSL configuration scenarios.

```python
from linktrace import Spider

# Scenario 1: Public HTTPS (default, most secure)
spider = Spider(start_url="https://example.com")

# Scenario 2: Self-signed certificate (testing only)
spider = Spider(
    start_url="https://self-signed.example.com",
    ssl_verify=False  # ⚠️ Insecure
)

# Scenario 3: Corporate proxy with custom CA
spider = Spider(
    start_url="https://internal.company.com",
    ssl_verify="/etc/ssl/certs/company-ca.pem"
)

# Scenario 4: Skip hostname verification only
spider = Spider(
    start_url="https://example.com",
    ssl_verify=True,          # Still verify cert chain
    verify_hostname=False     # But don't check hostname
)

documents = await spider.run_async()
```

## 7. Slow/Timeout-Prone Sites

Configure longer timeouts and more retries.

```python
from linktrace import Spider

async def main():
    spider = Spider(
        start_url="https://slow-api.example.com",
        request_timeout=60,    # 60 second timeout
        max_retries=5,         # Retry 5 times
    )
    documents = await spider.run_async()

asyncio.run(main())
```

## 8. Track Link Hierarchy

Find which pages link to which other pages.

```python
from linktrace import Spider

async def main():
    spider = Spider(
        start_url="https://example.com",
        max_depth=2
    )
    documents = await spider.run_async()
    
    # Build link graph
    graph = {}
    for doc in documents:
        graph[doc.url] = []
        for link in doc.internal_links:
            graph[doc.url].append(link.url)
    
    # Find most linked-to pages
    from collections import Counter
    inbound = Counter()
    for source, targets in graph.items():
        for target in targets:
            inbound[target] += 1
    
    print("Most linked pages:")
    for url, count in inbound.most_common(5):
        print(f"  {url}: {count} inbound links")

asyncio.run(main())
```

## 9. Export to Multiple Formats

Export same crawl to JSON, Pandas, Polars, PyArrow.

```python
from linktrace import Spider, Serializers

async def main():
    spider = Spider(start_url="https://example.com", max_depth=2)
    documents = await spider.run_async()
    
    serializer = Serializers(documents)
    
    # JSON (nested structure)
    serializer.to_json("crawl.json", include_html=False)
    
    # Pandas (flattened for analysis)
    df_pandas = serializer.to_pandas()
    df_pandas.to_csv("crawl.csv")
    
    # Polars (faster for large datasets)
    df_polars = serializer.to_polars()
    
    # PyArrow (for data pipelines)
    table = serializer.to_arrow()
    # Parquet export: table.to_pandas().to_parquet("crawl.parquet")

asyncio.run(main())
```

## 10. Find Broken Internal Links

Identify 404s and other errors on internal links. After the crawl, every
retained Document carries `broken_internal_links`: the internal links whose
target page came back with a 4xx/5xx status.

```python
from linktrace import Spider

async def main():
    spider = Spider(start_url="https://example.com", max_depth=2)
    documents = await spider.run_async()

    total = 0
    for doc in documents:
        for broken in doc.broken_internal_links:
            total += 1
            print(f"  {doc.url} → {broken.url} (HTTP {broken.status_code})")

    print(f"Found {total} broken internal links")

asyncio.run(main())
```

## 11. Batch Processing

Process large crawls in memory-efficient batches.

```python
from linktrace import Crawler

async def process_batch(urls):
    """Process a batch of URLs."""
    async with Crawler() as crawler:
        documents = []
        for url in urls:
            doc = await crawler.crawl_document_async(url)
            documents.append(doc)
        return documents

async def main():
    urls = [
        "https://example.com/page1",
        "https://example.com/page2",
        "https://example.com/page3",
    ]
    
    # Process in batches of 5
    batch_size = 5
    for i in range(0, len(urls), batch_size):
        batch = urls[i:i+batch_size]
        documents = await process_batch(batch)
        
        # Process batch results
        for doc in documents:
            print(f"Processed: {doc.url}")
            # Do something with doc...

import asyncio
asyncio.run(main())
```

## 12. Custom Logging

See detailed crawl progress.

```python
import logging
from linktrace import Spider

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

async def main():
    spider = Spider(
        start_url="https://example.com",
        max_depth=2,
        log_name="my-crawler"
    )
    documents = await spider.run_async()
    
    # Output includes:
    # DEBUG: "Traversal strategy: BFS"
    # DEBUG: "Fetching https://example.com (attempt 1)"
    # INFO: "Visited: https://example.com"
    # DEBUG: "Cache hit for https://example.com/page"
    # etc.

import asyncio
asyncio.run(main())
```

## 13. Stream Results to Disk (Memory Efficient)

For large crawls, process documents as they're crawled without accumulating in memory.

```python
import json
from linktrace import Spider

async def save_result(doc):
    """Save each document to JSONL file as it's crawled."""
    with open("results.jsonl", "a") as f:
        json.dump({
            "url": doc.url,
            "title": doc.title,
            "status": doc.status_code,
            "internal_links": len(doc.internal_links),
        }, f)
        f.write("\n")

async def main():
    spider = Spider(
        start_url="https://example.com",
        max_depth=2,
        on_page_crawled=save_result,
        accumulate_results=False,  # Don't keep in memory
    )
    
    result = await spider.run_async()
    # result is empty list, but file "results.jsonl" contains all pages
    print(f"Crawl complete. Results saved to results.jsonl")

asyncio.run(main())
```

## 14. Aggregate Results with Callbacks

Use callbacks to transform and aggregate data from each page.

```python
from linktrace import Spider

def extract_links(doc):
    """Extract and return link summary for each page."""
    return {
        "url": doc.url,
        "title": doc.title,
        "internal_count": len(doc.internal_links),
        "external_count": len(doc.external_links),
    }

async def main():
    spider = Spider(
        start_url="https://example.com",
        max_depth=1,
        on_page_crawled=extract_links,
        accumulate_results=True,  # Collect results
    )
    
    results = await spider.run_async()
    
    # results is list of dicts with structured data
    print(f"Crawled {len(results)} pages")
    for page in results:
        total = page['internal_count'] + page['external_count']
        print(f"  {page['title']} ({total} total links)")

asyncio.run(main())
```

## 15. Handle Errors with Callbacks

Track failures and perform cleanup operations.

```python
import logging
from linktrace import Spider

logger = logging.getLogger(__name__)
failed_urls = []

def on_error(url, exception):
    """Track failed URLs."""
    logger.error(f"Failed to crawl {url}: {exception}")
    failed_urls.append(url)

async def on_complete():
    """Cleanup and report."""
    if failed_urls:
        print(f"\nFailed URLs ({len(failed_urls)}):")
        for url in failed_urls:
            print(f"  - {url}")
    else:
        print("\nAll URLs crawled successfully!")

async def main():
    spider = Spider(
        start_url="https://example.com",
        max_depth=2,
        on_error=on_error,
        on_crawl_complete=on_complete,
    )
    
    documents = await spider.run_async()
    print(f"Crawled {len(documents)} pages")

asyncio.run(main())
```

## 16. Async Callbacks: Save to Database

Use async callbacks for I/O operations like database writes.

```python
from linktrace import Spider

class Database:
    async def connect(self):
        print("Connected to database")
    
    async def insert(self, url, title):
        # Simulate async DB insert
        print(f"Inserting: {title}")
    
    async def close(self):
        print("Database closed")

db = Database()

async def save_to_db(doc):
    """Async callback to save page to database."""
    await db.insert(doc.url, doc.title)
    return doc.url  # Return for tracking

async def cleanup():
    """Close database connection."""
    await db.close()

async def main():
    await db.connect()
    
    spider = Spider(
        start_url="https://example.com",
        max_depth=2,
        on_page_crawled=save_to_db,      # Async callback
        on_crawl_complete=cleanup,       # Cleanup hook
        accumulate_results=True,         # Get URLs back
    )
    
    urls = await spider.run_async()
    print(f"Saved {len(urls)} pages to database")

asyncio.run(main())
```

## 17. Respect robots.txt (Ethical Crawling)

Automatically respect robots.txt Crawl-delay directives for each domain.

```python
import asyncio
from linktrace import Spider

async def main():
    # By default, respect_robots_txt=True
    spider = Spider(
        start_url="https://example.com",
        max_depth=2,
        respect_robots_txt=True,  # Parse robots.txt for Crawl-delay
        user_agent="MyBot/1.0"     # Identify your bot
    )
    
    # Crawler will:
    # 1. Fetch https://example.com/robots.txt
    # 2. Extract Crawl-delay for MyBot/1.0
    # 3. Enforce delay between requests to same domain
    # 4. Allow concurrent requests to different domains
    
    documents = await spider.run_async()
    print(f"Crawled {len(documents)} pages (respecting robots.txt)")

asyncio.run(main())
```

## 18. Custom Rate Limiting

Enforce minimum delay between requests if robots.txt unavailable or for testing.

```python
import asyncio
from linktrace import Spider

async def main():
    # Disable robots.txt, use explicit delay
    spider = Spider(
        start_url="https://example.com",
        max_depth=2,
        respect_robots_txt=False,  # Don't fetch robots.txt
        request_delay=1.0          # 1 second between requests to same domain
    )
    
    # Requests to same domain: 1+ second apart
    # Requests to different domains: concurrent (respects 10 per-host limit)
    
    documents = await spider.run_async()
    print(f"Crawled {len(documents)} pages with 1s delay")

asyncio.run(main())
```

## 19. Track Pages with Error Status

Find pages that returned 4xx/5xx errors during crawling.

```python
import asyncio
from linktrace import Spider

async def main():
    spider = Spider(
        start_url="https://example.com",
        max_depth=2
    )
    documents = await spider.run_async()
    
    # Find pages with errors
    print("=== PAGES WITH ERRORS ===")
    error_pages = [doc for doc in documents if doc.status_code >= 400]
    for doc in error_pages:
        print(f"  {doc.url} (HTTP {doc.status_code})")
    
    # Check for disallowed pages (robots.txt)
    print("\n=== DISALLOWED BY ROBOTS.TXT ===")
    disallowed = [doc for doc in documents if doc.status_code == 403]
    for doc in disallowed:
        print(f"  {doc.url}")
    
    # Summary
    print(f"\nTotal: {len(documents)} pages")
    print(f"Errors: {len(error_pages)}")
    print(f"Disallowed: {len(disallowed)}")

asyncio.run(main())
```

## 20. Stream Error Pages to Report

Monitor pages with error responses as crawl progresses using callbacks.

```python
import asyncio
import json
from linktrace import Spider

async def track_errors(doc):
    """Log error pages as they're discovered."""
    if doc.status_code >= 400:
        report = {
            "url": doc.url,
            "status": doc.status_code,
            "status_text": "Disallowed" if doc.status_code == 403 else "Error"
        }
        with open("error_pages.jsonl", "a") as f:
            json.dump(report, f)
            f.write("\n")

async def main():
    spider = Spider(
        start_url="https://example.com",
        max_depth=2,
        on_page_crawled=track_errors,
        accumulate_results=False,  # Memory efficient
        request_delay=0.5          # Be polite
    )
    
    await spider.run_async()
    print("Error pages report saved to error_pages.jsonl")

asyncio.run(main())
```

## 21. Focus a Crawl with URL Filtering Rules

Use `CrawlRules` to follow only the URLs you care about and skip crawl traps
(login pages, sort/calendar links, binary files, off-site domains). Rules apply
to every discovered link; the `start_url` itself is always fetched.

```python
import asyncio
from linktrace import Spider, CrawlRules

async def main():
    rules = CrawlRules(
        # Stay on this site (matches subdomains too)
        allowed_domains=["realty.example.com"],
        # Only follow listing and agent pages...
        include_path_prefixes=["/homes-for-sale/", "/agents/"],
        # ...but never these
        exclude_path_prefixes=["/login", "/privacy", "/cart"],
        # Skip binaries — we want documents, not downloads
        blocked_extensions=["pdf", "jpg", "png", "zip"],
        # Drop faceted-search variants that explode the queue
        exclude_query_params=["sort", "view", "page", "calendar"],
        # Regex escape hatch for anything the above can't express
        exclude_patterns=[r"/print/?$"],
    )

    spider = Spider(
        start_url="https://realty.example.com/",
        max_depth=4,
        rules=rules,
    )
    documents = await spider.run_async()
    print(f"Crawled {len(documents)} on-topic pages")

asyncio.run(main())
```

!!! note "Exclusions always win"
    For each dimension, a populated *allow* list (`allowed_domains`,
    `include_path_prefixes`, `allowed_extensions`, `include_patterns`) acts as a
    whitelist, and any *block*/*exclude* list rejects matches. If a URL matches
    both an include and an exclude, it is **excluded**. An empty `CrawlRules()`
    allows everything, so leaving `rules` unset preserves the default behavior.

## 22. Tune Concurrency for Throughput

Raise (or lower) how many pages are fetched at once. `max_concurrency` controls
the Spider's per-batch fan-out; `max_connections` / `max_connections_per_host`
size the underlying aiohttp connection pool.

```python
import asyncio
from linktrace import Spider

async def main():
    # Faster: large fan-out, but cap per-host to stay polite to one server
    spider = Spider(
        start_url="https://example.com",
        max_depth=3,
        max_concurrency=50,            # up to 50 fetches per batch (default 10)
        max_connections=200,           # total pool size (default 100)
        max_connections_per_host=8,    # be gentle on a single host (default 10)
        request_delay=0.2,             # still rate-limit per domain
    )
    documents = await spider.run_async()
    print(f"Crawled {len(documents)} pages")

asyncio.run(main())
```

!!! tip "Be a good citizen"
    High concurrency is best when fanning out across **many** hosts. Against a
    single site, keep `max_connections_per_host` modest and pair it with
    `request_delay` or `respect_robots_txt=True` so you don't overwhelm the
    server.

## 23. Seed a Crawl from Sitemaps

Set `use_sitemaps=True` to discover URLs from the site's own document
inventory before link-following begins. linktrace reads `Sitemap:` declarations
from `robots.txt` (falling back to `/sitemap.xml`), follows sitemap *indexes*
and nested sitemaps, and seeds every discovered URL at depth 0.

```python
import asyncio
from linktrace import Spider, CrawlRules

async def main():
    rules = CrawlRules(include_path_prefixes=["/homes-for-sale/"])

    spider = Spider(
        start_url="https://realty.example.com/",
        max_depth=2,
        use_sitemaps=True,   # seed from sitemap.xml / robots.txt Sitemap:
        rules=rules,         # sitemap URLs are filtered through rules too
    )
    documents = await spider.run_async()
    print(f"Crawled {len(documents)} pages (sitemap-seeded)")

asyncio.run(main())
```

You can also use the parser directly to inspect a site's sitemaps:

```python
import asyncio
from linktrace import Crawler, SitemapParser

async def main():
    async with Crawler() as crawler:
        parser = SitemapParser(crawler.session)
        urls = await parser.discover("https://realty.example.com/")
        print(f"Sitemap lists {len(urls)} URLs")
        for url in urls[:10]:
            print(f"  {url}")

asyncio.run(main())
```

## 24. Crawl a JavaScript-Rendered Site (SPA)

React, Vue and Angular apps ship an empty HTML shell and build their links in
the browser, so plain HTTP finds nothing. `BrowserFetcher` renders every page
in headless Chromium before linktrace parses it. Requires
`pip install linktrace[browser]` and a one-time `playwright install chromium`.

```python
import asyncio
from linktrace import Spider, BrowserFetcher, CrawlRules

async def main():
    spider = Spider(
        start_url="https://listings.example.com/",
        max_depth=2,
        fetcher=BrowserFetcher(
            wait_until="networkidle",      # let the app finish its XHR calls
            wait_for_selector="a[href]",   # ...and actually render links
            max_pages=4,                   # concurrent tabs
        ),
        rules=CrawlRules(include_path_prefixes=["/listing/", "/"]),
        request_delay=0.5,                 # rate limiting still applies
    )
    documents = await spider.run_async()

    for doc in documents:
        print(f"[{doc.fetcher}] {doc.url}: {len(doc.internal_links)} links")

asyncio.run(main())
```

!!! tip "Hash-router apps"
    If the app's routes look like `/#/listing/42`, add
    `keep_hash_routes=True` to the Spider. Without it every route normalizes
    to the same bare URL and the crawl stops after one page.

## 25. HTTP First, Browser Only When Needed

Rendering is 10-50x slower than an HTTP request. `RoutingFetcher` fetches
each URL with plain HTTP first and only re-fetches in the browser when the
response looks like an un-rendered SPA shell (a `<noscript>` telling you to
enable JavaScript, an empty `<div id="root">`, or no links but a script
bundle). Mixed sites, where a server-rendered marketing site wraps a
client-rendered app, get the cheap path for most pages.

```python
import asyncio
from linktrace import Spider, RoutingFetcher, BrowserFetcher

async def main():
    routing = RoutingFetcher(
        fallback=BrowserFetcher(max_pages=2),
        render_patterns=[r"/search", r"/map"],   # always render these
    )
    spider = Spider(
        start_url="https://realty.example.com/",
        max_depth=3,
        fetcher=routing,
    )
    documents = await spider.run_async()

    rendered = [d for d in documents if d.fetcher == "browser"]
    print(f"{len(documents)} pages, {len(rendered)} rendered "
          f"({routing.escalations} escalated automatically)")

asyncio.run(main())
```

Pass `escalate=None` to route purely by pattern, or your own
`escalate=lambda result: ...` for site-specific signals.

## 26. Stream a Huge Crawl to Disk

Documents hold their full HTML, so a deep crawl can exhaust memory. `flush_to`
appends each page to a JSONL file the moment it is crawled and keeps nothing
in RAM beyond the URL bookkeeping. The line format matches
`Serializers.to_json`, so it loads straight into pandas or polars.

```python
import asyncio
import polars as pl
from linktrace import Spider

async def main():
    spider = Spider(
        start_url="https://example.com/",
        max_depth=6,
        flush_to="crawl.jsonl",
        flush_html=False,          # True to keep page source too
        show_progress=True,
    )
    await spider.run_async()       # returns []

    df = pl.read_ndjson("crawl.jsonl")
    print(df.select("url", "status_code", "fetcher").head())

asyncio.run(main())
```

`flush_to` combines with a callback or with `retain_documents=True` if you
also want the objects in memory.

## 27. Write Your Own Fetcher

Any transport can plug into the crawl: subclass `Fetcher`, return a
`FetchResult`, and raise `TransientFetchError` for failures the Crawler should
retry. Robots.txt, rate limiting, retries, caching and parsing all keep
working unchanged.

```python
import asyncio
import httpx
from linktrace import Spider, Fetcher, FetchResult, TransientFetchError

class HttpxFetcher(Fetcher):
    name = "httpx"

    async def open(self, ctx):
        self.client = httpx.AsyncClient(
            http2=True, timeout=ctx.request_timeout,
            headers={"User-Agent": ctx.user_agent},
        )

    async def close(self):
        await self.client.aclose()

    async def fetch(self, url, headers):
        try:
            r = await self.client.get(url, headers=headers, follow_redirects=True)
        except httpx.TimeoutException as e:
            raise TransientFetchError(str(e)) from e
        return FetchResult(
            url, r.status_code, dict(r.headers),
            body=r.text if r.status_code == 200 else None,
            fetcher=self.name,
        )

async def main():
    spider = Spider("https://example.com/", fetcher=HttpxFetcher())
    documents = await spider.run_async()
    print({d.fetcher for d in documents})   # {"httpx"}

asyncio.run(main())
```
