# webcrawler

Async web crawler / spider.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and [just](https://github.com/casey/just).

```sh
just sync     # create .venv, install deps + the WebCrawler package (editable)
just run      # run the spider against the demo URL
just build    # build wheel + sdist into dist/
just lint     # ruff check --fix
just fmt      # ruff format
just check    # CI: lint + format check (no writes)
```

## Layout

The importable package lives in `WebCrawler/`; everything else (tooling,
config, `.venv`) stays at the repo root and is not packaged.

- `WebCrawler/Spider.py` — async crawl driver (`Spider.run_async`)
- `WebCrawler/Crawler.py` — `Crawler`: fetch + parse one document (aiohttp + lxml)
- `WebCrawler/NetLib.py` — TLD/domain parsing, backed by `WebCrawler/data/effective_tld_names.hdf5`
- `WebDocument.py` — legacy synchronous document model at the repo root, superseded by the async path and excluded from the package and from linting

The distribution name is `webcrawler`; the import namespace is `WebCrawler`
(e.g. `from WebCrawler import Crawler, Spider`).

## Configuration

### Retries and Timeouts

All transient errors (timeouts, connection errors, 5xx responses) are retried with exponential backoff:

```python
spider = Spider(
    start_url="https://example.com",
    max_retries=3,              # Retry transient errors 3 times (default)
    request_timeout=30,         # 30 second timeout per request (default)
)
```

Exponential backoff uses: `wait_time = 2^attempt * backoff_factor`. Default backoff_factor is 2.

### Caching

Enable disk-based caching to avoid re-fetching URLs:

```python
spider = Spider(
    start_url="https://example.com",
    cache_dir=".webcrawler_cache"  # Enable caching, opt-in
)
```

- Cached responses are stored in `cache_dir` with a 1-day TTL by default
- Expired cache entries are automatically cleaned up on next access
- Cache is NOT enabled by default (specify `cache_dir=None` to disable)

### SSL and Certificates

By default, SSL certificate verification is enabled (secure):

```python
spider = Spider(
    start_url="https://example.com",
    ssl_verify=True   # Verify SSL certificates (default, recommended)
)
```

**For corporate proxies** (intercept HTTPS traffic):

```python
# Option 1: Custom CA certificate bundle (recommended for corporate proxies)
spider = Spider(
    start_url="https://example.com",
    ssl_verify="/path/to/corporate-ca.pem"  # Use corporate CA
)

# Option 2: Disable verification (less safe, only if CA bundle unavailable)
spider = Spider(
    start_url="https://example.com",
    ssl_verify=False  # ONLY for testing/corporate development
)

# Option 3: Disable hostname checking separately (independent of cert verification)
spider = Spider(
    start_url="https://example.com",
    ssl_verify=True,          # Still verify cert chain
    verify_hostname=False,    # But don't check hostname
)
```

**`ssl_verify` accepts:**
- `True` (default) — verify with system CA bundle
- `False` — disable verification entirely (insecure, testing only)
- `"/path/to/ca.pem"` — verify with custom CA bundle (corporate proxy scenario)

**`verify_hostname`:**
- `True` (default) — verify certificate hostname matches
- `False` — skip hostname verification (for self-signed certs, testing)

### Cookies

Cookies are handled automatically:
- Set-Cookie responses are automatically extracted
- Cookies are automatically sent on subsequent matching requests
- No additional configuration needed

Cookies work within a single `Spider.run_async()` call but do NOT persist across separate runs.

## Examples

### Basic crawl

```python
import asyncio
from WebCrawler import Spider

async def main():
    spider = Spider(start_url="https://example.com", max_depth=2)
    documents = await spider.run_async()
    
    for doc in documents:
        print(f"{doc.url}: {len(doc.links)} links")

asyncio.run(main())
```

### With caching (faster on subsequent runs)

```python
spider = Spider(
    start_url="https://example.com",
    cache_dir=".cache"  # ~2-50x faster on repeat crawls
)
documents = await spider.run_async()
```

### Crawl with timeout and retries

```python
spider = Spider(
    start_url="https://example.com",
    request_timeout=15,     # 15 sec timeout instead of default 30
    max_retries=5,          # Retry 5 times instead of default 3
)
```

### Traversal Strategies: BFS vs DFS

By default, Spider uses **breadth-first search (BFS)** — explores each depth level completely before going deeper.

For **depth-first search (DFS)** — follows single paths all the way down:

```python
spider = Spider(
    start_url="https://example.com",
    max_depth=5,
    traversal_strategy="dfs"  # Explore deep before broad
)
```

**When to use each:**
- **BFS (default)**: General site exploration, balanced memory use, finding many pages quickly, natural depth-limiting
- **DFS**: Deep hierarchies (docs, nested directories), memory-efficient for wide/shallow sites, exploring complete subtrees, path-based traversal

### Export to JSON, Pandas, Polars, or PyArrow

```python
from WebCrawler import Spider, Serializers

async def main():
    spider = Spider(start_url="https://example.com", max_depth=2)
    documents = await spider.run_async()
    
    # Export to JSON with nested link structure
    serializer = Serializers(documents)
    serializer.to_json("output.json", include_html=False)
    
    # Export to pandas DataFrame with flattened links (one row per link)
    df = serializer.to_pandas()
    print(df[["url", "title", "link_url", "link_type"]])
    
    # Export to polars or PyArrow
    df_polars = serializer.to_polars()
    table_arrow = serializer.to_arrow()

asyncio.run(main())
```

**Serializers features:**
- **JSON**: Nested structure preserving internal/external links
- **Pandas/Polars/PyArrow**: Flattened format with one row per link, suitable for data analysis
- **Metadata**: Each export includes: url, title, status_code, domain, response_headers, link_url, link_text, link_type
- **Optional HTML**: Pass `include_html=True` to export raw HTML source

**Installation:** Optional serialization dependencies can be installed with:
```sh
pip install webcrawler[serializers]  # All three: pandas, polars, pyarrow
pip install webcrawler[pandas]       # Just pandas
pip install webcrawler[polars]       # Just polars
pip install webcrawler[pyarrow]      # Just pyarrow
```

## Notebooks

Interactive examples and demos in `notebooks/`:
- `crawl_cnn.ipynb` — crawls CNN.com and analyzes link structure, page titles, and external link domains
