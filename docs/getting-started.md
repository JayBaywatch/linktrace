# Getting Started

## Installation

### From PyPI

```bash
pip install linktrace
```

### With Optional Export Formats

```bash
# All three: pandas, polars, pyarrow
pip install linktrace[serializers]

# Individual formats
pip install linktrace[pandas]
pip install linktrace[polars]
pip install linktrace[pyarrow]
```

### With JavaScript Rendering

For single-page apps that build their links in the browser:

```bash
pip install linktrace[browser]
playwright install chromium     # one-time download of the browser build
```

### Development Installation

```bash
git clone https://github.com/JayBaywatch/linktrace
cd webcrawler
pip install -e .
pip install -e ".[serializers]"  # Optional formats
```

## Your First Crawl

### 1. Basic Example

```python
import asyncio
from linktrace import Spider

async def main():
    spider = Spider(start_url="https://example.com", max_depth=1)
    documents = await spider.run_async()
    print(f"Crawled {len(documents)} pages")

asyncio.run(main())
```

### 2. Inspect Documents

```python
for doc in documents:
    print(f"URL: {doc.url}")
    print(f"Title: {doc.title}")
    print(f"Status: {doc.status_code}")
    print(f"Internal links: {len(doc.internal_links)}")
    print(f"External links: {len(doc.external_links)}")
    print()
```

### 3. Analyze Links

```python
# Find all external domains
external_domains = set()
for doc in documents:
    for link in doc.external_links:
        domain = link.url.split("/")[2]
        external_domains.add(domain)

print(f"Found {len(external_domains)} external domains")
```

### 4. Export Data

```python
from linktrace import Serializers

serializer = Serializers(documents)

# JSON
serializer.to_json("output.json")

# Pandas DataFrame
df = serializer.to_pandas()
print(df[["url", "title", "link_type"]].head())

# Polars
df_polars = serializer.to_polars()

# PyArrow
table = serializer.to_arrow()
```

## Common Patterns

### Crawl with Caching

```python
spider = Spider(
    start_url="https://example.com",
    max_depth=2,
    cache_dir=".webcrawler_cache"  # Enable disk caching
)

# First run: fetches from network
documents = await spider.run_async()

# Second run: uses cache (10-50x faster)
documents = await spider.run_async()
```

### Deep Crawling (DFS)

```python
spider = Spider(
    start_url="https://docs.example.com",
    max_depth=5,
    traversal_strategy="dfs"  # Depth-first
)
documents = await spider.run_async()
```

### Custom Timeouts & Retries

```python
spider = Spider(
    start_url="https://slow-api.example.com",
    request_timeout=60,   # 60 second timeout
    max_retries=5         # Retry 5 times
)
documents = await spider.run_async()
```

### Corporate Proxy with CA Certificate

```python
spider = Spider(
    start_url="https://internal.company.com",
    ssl_verify="/etc/ssl/certs/company-ca.pem"  # Custom CA
)
documents = await spider.run_async()
```

### Focus the Crawl with Filtering Rules

Follow only the URLs you care about and skip crawl traps (login pages,
sort/calendar links, binaries, off-site domains):

```python
from linktrace import Spider, CrawlRules

rules = CrawlRules(
    allowed_domains=["example.com"],            # stay on-site (subdomain-aware)
    include_path_prefixes=["/docs/"],           # only this section...
    exclude_path_prefixes=["/docs/legacy/"],    # ...but not this part of it
    blocked_extensions=["pdf", "zip"],          # documents, not downloads
    exclude_query_params=["sort", "page"],       # avoid faceted-search traps
)
spider = Spider("https://example.com/", max_depth=3, rules=rules)
documents = await spider.run_async()
```

Exclusions always win, and an empty `CrawlRules()` allows everything. See
[Core Concepts](core-concepts.md#url-filtering-rules) for the full evaluation order.

### Tune Concurrency

```python
spider = Spider(
    start_url="https://example.com",
    max_concurrency=50,            # URLs fetched per batch (default: 10)
    max_connections=200,           # total aiohttp pool size (default: 100)
    max_connections_per_host=8,    # connections to one host (default: 10)
)
documents = await spider.run_async()
```

Raise these to go faster across many hosts; keep `max_connections_per_host`
modest (and pair with `request_delay`) to stay polite to a single server.

### Seed from Sitemaps

Discover URLs from the site's own sitemap before link-following begins:

```python
spider = Spider(
    start_url="https://example.com/",
    max_depth=2,
    use_sitemaps=True,   # read sitemap.xml / robots.txt Sitemap: declarations
)
documents = await spider.run_async()
```

### Crawl a JavaScript-Rendered Site

Plain HTTP only sees the empty shell of a React/Vue/Angular app. Swap the
fetcher and the same crawl renders each page in headless Chromium first:

```python
from linktrace import Spider, RoutingFetcher

spider = Spider(
    start_url="https://app.example.com/",
    max_depth=2,
    fetcher=RoutingFetcher(),   # HTTP first; browser only for SPA-looking pages
)
documents = await spider.run_async()
for doc in documents:
    print(doc.fetcher, doc.url, len(doc.internal_links))   # "http" or "browser"
```

Use `fetcher=BrowserFetcher()` to render every page, and
`keep_hash_routes=True` for hash-router apps (`/#/listings/42`). See
[Core Concepts](core-concepts.md#fetchers) for how the pieces fit.

### Stream a Large Crawl to Disk

When a crawl won't fit in memory, write each page to a JSONL file as it is
crawled instead of collecting `Document` objects:

```python
spider = Spider(
    start_url="https://example.com/",
    max_depth=5,
    flush_to="crawl.jsonl",   # one JSON object per line
)
await spider.run_async()      # returns []; results are in crawl.jsonl
```

## Jupyter Notebooks

See the `notebooks/` directory for interactive examples:

```bash
jupyter notebook notebooks/crawl_cnn.ipynb
```

- **`crawl_cnn.ipynb`** — basic crawling, link-structure analysis, and exporting
  to JSON / Pandas / Polars / PyArrow
- **`config_rules_sitemaps.ipynb`** — URL filtering rules, configurable
  concurrency, and sitemap discovery

## Next Steps

- Read [Core Concepts](core-concepts.md) to understand Spider, Crawler, and Document
- See [Examples](examples.md) for more patterns
- Check [API Reference](api-reference.md) for complete method docs
- Browse [Troubleshooting](troubleshooting.md) if issues arise
