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
    traversal_strategy: str = "bfs"
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

Crawl synchronously (blocking). Use `asyncio.run()` wrapper for async context.

```python
spider = Spider(start_url="https://example.com")
documents = spider.run()  # Blocks until complete
```

**Returns:** List of Document objects

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `start_url` | str | Starting URL |
| `max_depth` | int | Max crawl depth |
| `visited` | set | Set of visited URLs |
| `to_visit` | list | Queue of (url, depth) tuples |
| `documents` | list | Results (accumulated Documents) |
| `visited_count` | int | Number of pages successfully fetched |
| `traversal_strategy` | str | "bfs" or "dfs" |

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
    backoff_factor: int = 2
)
```

#### Parameters

Same as Spider, plus:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `log_level` | int | logging.DEBUG | Logging level |
| `backoff_factor` | int | 2 | Exponential backoff multiplier (wait_time = 2^attempt * factor) |

### Methods

#### `async __aenter__() -> Crawler`

Enter async context manager. Creates persistent aiohttp session.

```python
async with Crawler(...) as crawler:
    doc = await crawler.crawl_document_async("https://example.com")
```

#### `async __aexit__(exc_type, exc_val, exc_tb)`

Exit async context manager. Closes session.

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
- Retries transient errors up to `max_retries` times
- Returns Document even on 4xx/5xx (check `status_code`)
- Automatic cookie handling

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `session` | aiohttp.ClientSession | HTTP session (None until context entered) |
| `cache` | ResponseCache | Cache object (None if cache_dir not set) |
| `ssl_verify` | bool\|str | SSL verification setting |
| `verify_hostname` | bool | Hostname verification setting |
| `request_timeout` | int | Request timeout in seconds |
| `max_retries` | int | Max retry attempts |
| `backoff_factor` | int | Exponential backoff multiplier |

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
| `domain` | str | Domain extracted from URL (read-only property) |
| `internal_links` | List[HtmlLink] | Links to same domain |
| `external_links` | List[HtmlLink] | Links to other domains |
| `links` | List[HtmlLink] | All links (internal + external) |

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
- `url`, `title`, `status_code`, `domain`
- `link_url`, `link_text`, `link_type` (internal/external/None)
- `html` (if include_html=True)

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
ResponseCache(cache_dir: str, ttl_seconds: int = 86400)
```

**Parameters:**
- `cache_dir` (str) — Directory to store cache files
- `ttl_seconds` (int) — Time-to-live for entries (default: 1 day)

### Methods

#### `async get(url: str) -> CachedResponse | None`

Retrieve cached response if not expired.

#### `async set(url: str, status_code: int, headers: dict, content: str) -> None`

Store response in cache.

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

---

## Logging

WebCrawler uses Python's standard logging module.

### Configure Logging

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Or specific logger
logger = logging.getLogger("WebCrawler.Spider")
logger.setLevel(logging.DEBUG)
```

### Log Levels

- **DEBUG:** Detailed traversal, cache hits/misses, retries
- **INFO:** Pages visited, crawl progress
- **WARNING:** SSL verification disabled, expired cache entries
- **ERROR:** Failed requests after retries, parse errors
