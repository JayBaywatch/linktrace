# Troubleshooting

## SSL/Certificate Issues

### "SSL: CERTIFICATE_VERIFY_FAILED"

**Problem:** Certificate verification failed.

**Solutions:**

1. **Self-signed certificates (testing only):**
   ```python
   spider = Spider(
       start_url="https://self-signed.example.com",
       ssl_verify=False  # ⚠️ Insecure
   )
   ```

2. **Corporate proxy with CA bundle:**
   ```python
   spider = Spider(
       start_url="https://internal.company.com",
       ssl_verify="/etc/ssl/certs/company-ca.pem"
   )
   ```

3. **Skip hostname verification only:**
   ```python
   spider = Spider(
       start_url="https://example.com",
       ssl_verify=True,
       verify_hostname=False
   )
   ```

### "Can't connect to HTTPS URL because the SSL module is not available"

**Problem:** Python built without SSL support.

**Solution:** Rebuild Python with OpenSSL or use a prebuilt Python distribution.

---

## Connection & Timeout Issues

### "Connection refused" or "No route to host"

**Problem:** Cannot reach the target server.

**Debugging:**
- Check URL spelling
- Verify server is running
- Test connectivity: `ping example.com`
- Try in browser first

```python
# Verify URL is correct
spider = Spider(start_url="https://example.com")
```

### "Request timeout" / "Timeout waiting for response"

**Problem:** Server too slow or network latency.

**Solutions:**

1. **Increase timeout:**
   ```python
   spider = Spider(
       start_url="https://slow-server.example.com",
       request_timeout=60  # 60 seconds instead of default 30
   )
   ```

2. **Increase retries:**
   ```python
   spider = Spider(
       start_url="https://example.com",
       max_retries=5  # Retry 5 times
   )
   ```

3. **Use DFS for deep sites:**
   ```python
   spider = Spider(
       start_url="https://example.com",
       traversal_strategy="dfs"  # Fewer concurrent requests
   )
   ```

### "Too many connections" / "Connection pool is full"

**Problem:** Too many concurrent requests, or you're overwhelming a single host.

**Solution:** Lower the concurrency knobs and/or add a per-domain delay:

```python
spider = Spider(
    start_url="https://example.com",
    max_concurrency=5,             # fewer URLs per batch (default: 10)
    max_connections_per_host=4,    # fewer simultaneous conns to one host (default: 10)
    request_delay=0.5,             # space out requests to the same domain
)
documents = await spider.run_async()
```

---

## Parsing & Document Issues

### "No links found" / "Empty internal_links"

**Problem:** Spider isn't finding links on the page.

**Debugging:**

```python
spider = Spider(start_url="https://example.com", max_depth=1)
documents = await spider.run_async()

doc = documents[0]
print(f"URL: {doc.url}")
print(f"Status: {doc.status_code}")
print(f"Title: {doc.title}")
print(f"HTML length: {len(doc.source)}")
print(f"Internal links: {len(doc.internal_links)}")
print(f"External links: {len(doc.external_links)}")

# Print first few links
for link in doc.internal_links[:3]:
    print(f"  - {link.url}")
```

**Common causes:**
- Relative links not resolved correctly
- JavaScript-generated links (the default HTTP fetcher doesn't execute JS)
- Links hidden behind `onclick` or `data-href`
- Hash-router URLs (`/#/page`) collapsing to one URL
- Page returned error status (check `doc.status_code`)

**Solution for JS-heavy sites:** render in a headless browser.

```python
from linktrace import Spider, RoutingFetcher

spider = Spider(
    start_url="https://app.example.com/",
    fetcher=RoutingFetcher(),      # HTTP first, browser when the page looks like an SPA
    keep_hash_routes=True,         # only if routes look like /#/...
)
```

Requires `pip install linktrace[browser]` and `playwright install chromium`.
Quick check that rendering is the problem: `looks_like_spa_shell` on the
raw response.

```python
from linktrace import Crawler, looks_like_spa_shell

async with Crawler() as crawler:
    result = await crawler.fetcher.fetch("https://app.example.com/", {})
    print(looks_like_spa_shell(result))   # True → you need BrowserFetcher
```

Links driven purely by `onclick` handlers have no `href` and stay out of
reach even when rendered.

### "Wrong internal/external classification"

**Problem:** Link marked as external when it should be internal (or vice versa).

**Cause:** Domain extraction issue.

```python
doc.url = "https://example.com"
doc.domain  # "example"

# Subdomain issue?
doc.url = "https://api.example.com"
doc.domain  # "example" (correctly recognizes base domain)

# Link mismatch?
link.url = "https://www.example.com"  # "www" prefix
# Link is still internal because tldextract handles this
```

**If still misclassified:** Check link URL format:

```python
for link in doc.links:
    print(f"{link.url} → {link.url.split('/')[2]}")
```

---

## Browser Fetcher Issues

### "BrowserFetcher requires Playwright"

**Problem:** The `browser` extra is not installed.

```bash
pip install "linktrace[browser]"
playwright install chromium
```

### "Could not launch chromium" / "Executable doesn't exist"

**Problem:** Playwright is installed but its browser build is not.

```bash
playwright install chromium
```

In Docker use the `mcr.microsoft.com/playwright/python` base image, or run
`playwright install --with-deps chromium` to pull system libraries too.

### "Browser timeout" on every page

**Problem:** `wait_until="networkidle"` never fires because the site keeps a
long-polling or websocket connection open.

**Solution:** Wait for the DOM and a selector instead:

```python
BrowserFetcher(wait_until="domcontentloaded", wait_for_selector="a[href]")
```

Timeouts are retried like any transient error; lower `max_retries` if a site
is consistently slow rather than flaky.

### Rendered pages still have no links

- Confirm the crawl actually used the browser: `doc.fetcher == "browser"`.
  With `RoutingFetcher`, a page that doesn't trip the SPA heuristic stays on
  HTTP; add it to `render_patterns`.
- The app may render links only after an XHR completes; add
  `wait_for_selector` for an element that appears with the data, or
  `settle_ms=500`.
- A stale cache entry from an HTTP crawl is never served to a browser crawl
  (entries are namespaced by fetcher), but clearing `cache_dir` rules it out.

### Browser crawl is slow

- Keep `max_pages` small (default 4); more tabs rarely helps on one host.
- Prefer `RoutingFetcher` so only SPA pages are rendered.
- Leave `block_resources` at its default (images, media, fonts are skipped).
- Enable `cache_dir` so repeat crawls skip rendering entirely.

---

## Memory Issues

### "Crawl runs out of memory"

**Problem:** Every `Document` holds its HTML (and rendered DOMs are larger),
and by default all of them are kept until the crawl finishes.

**Solutions:**

1. **Flush to disk** and keep nothing in memory:
   ```python
   spider = Spider(start_url="...", flush_to="crawl.jsonl")
   await spider.run_async()   # returns []; read crawl.jsonl afterwards
   ```

2. **Stream through a callback** (documents are released after it runs):
   ```python
   spider = Spider(start_url="...", on_page_crawled=handle, accumulate_results=False)
   ```

3. Lower `max_depth`, tighten `CrawlRules`, or use DFS for a smaller queue.

Both streaming modes set `retain_documents=False`; `broken_internal_links` is
only computed for retained documents.

---

## Caching Issues

### "Cache file corrupted" warning

**Problem:** Cache file is invalid JSON or incomplete.

**Solution:** Clear cache:

```python
import shutil
shutil.rmtree(".webcrawler_cache")
```

Cache is automatically cleaned up on corruption; the crawl continues.

### "Cache not being used" / "Slow second run"

**Problem:** Cache directory doesn't exist or wrong path.

**Debugging:**

```python
import os
from linktrace import Spider

cache_dir = ".webcrawler_cache"
print(f"Cache enabled: {os.path.exists(cache_dir)}")
print(f"Cache files: {os.listdir(cache_dir) if os.path.exists(cache_dir) else 'N/A'}")

spider = Spider(
    start_url="https://example.com",
    cache_dir=cache_dir
)
```

**Solutions:**

1. **Ensure cache_dir is set:**
   ```python
   spider = Spider(
       start_url="https://example.com",
       cache_dir=".webcrawler_cache"  # Don't forget this!
   )
   ```

2. **Use absolute path:**
   ```python
   import os
   cache_dir = os.path.join(os.getcwd(), ".webcrawler_cache")
   spider = Spider(start_url="...", cache_dir=cache_dir)
   ```

---

## Performance Issues

### "Crawl is slow"

**Problem:** Waiting for network or parsing.

**Debugging:**

```python
import time
from linktrace import Spider

start = time.time()
spider = Spider(start_url="https://example.com", max_depth=1)
documents = await spider.run_async()
elapsed = time.time() - start

print(f"Pages: {len(documents)}")
print(f"Time: {elapsed:.2f}s")
print(f"Per page: {elapsed / len(documents):.2f}s")
```

**Solutions:**

1. **Increase max_depth cautiously** (exponential time):
   ```python
   # Depth 1 = fast
   # Depth 2 = slower
   # Depth 3+ = can be very slow
   spider = Spider(start_url="https://example.com", max_depth=2)
   ```

2. **Use caching:**
   ```python
   spider = Spider(
       start_url="https://example.com",
       cache_dir=".webcrawler_cache"  # 2-50x faster on 2nd run
   )
   ```

3. **Raise concurrency:**
   ```python
   spider = Spider(
       start_url="https://example.com",
       max_concurrency=50,     # more URLs fetched per batch (default: 10)
       max_connections=200,    # larger connection pool (default: 100)
   )
   ```

4. **Try BFS instead of DFS (or vice versa):**
   ```python
   # DFS might find slow branch first
   spider = Spider(
       start_url="https://example.com",
       traversal_strategy="bfs"  # Try this instead
   )
   ```

---

## Crawl Scope Issues

### "Crawl pulls in too many irrelevant pages"

**Problem:** The spider follows every internal link — login pages, faceted-search
variants (`?sort=`, `?page=`), calendars, binaries — exhausting `max_depth` on
pages you don't want.

**Solution:** Pass `CrawlRules` to scope the crawl:

```python
from linktrace import Spider, CrawlRules

rules = CrawlRules(
    include_path_prefixes=["/products/"],   # only this section
    exclude_query_params=["sort", "page"],   # drop faceted-search traps
    blocked_extensions=["pdf", "jpg", "zip"],
    allowed_domains=["example.com"],         # never wander off-site
)
spider = Spider("https://example.com/", rules=rules)
```

Rules are pure and testable — verify your policy without crawling:

```python
rules.allows("https://example.com/products/1")            # True
rules.allows("https://example.com/products/1?sort=price") # False
```

### "Sitemap seeding found no URLs"

**Problem:** `use_sitemaps=True` didn't add anything to the queue.

**Cause:** The site may not publish a sitemap, or it isn't declared in robots.txt
and isn't at `/sitemap.xml`. Discovery is best-effort — the crawl still proceeds
via ordinary link-following.

**Debugging:** Inspect what discovery returns directly:

```python
from linktrace import Crawler

async with Crawler() as crawler:
    urls = await crawler.discover_sitemap_urls("https://example.com/")
    print(f"Sitemap listed {len(urls)} URLs")
```

---

## Export/Serialization Issues

### "pandas not found" error

**Problem:** pandas not installed.

**Solution:**
```bash
pip install pandas
# or
pip install linktrace[pandas]
```

### "DataFrame is huge / running out of memory"

**Problem:** Too many rows from large crawl.

**Solutions:**

1. **Export only specific fields:**
   ```python
   df = serializer.to_pandas()
   df_small = df[["url", "title", "link_url", "link_type"]]
   df_small.to_csv("output.csv")
   ```

2. **Process in batches:**
   ```python
   df = serializer.to_pandas()
   for chunk in [df[i:i+1000] for i in range(0, len(df), 1000)]:
       process(chunk)
   ```

3. **Don't include HTML:**
   ```python
   serializer = Serializers(documents)
   df = serializer.to_pandas(include_html=False)  # Much smaller
   ```

---

## Logging & Debugging

### "No debug output" / "Silent failure"

**Problem:** Can't see what's happening.

**Solution:** Enable logging:

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

spider = Spider(start_url="https://example.com")
documents = await spider.run_async()

# Now you'll see:
# DEBUG: Spider initialized: strategy=BFS, max_depth=3
# DEBUG: Fetching https://example.com (attempt 1)
# INFO: Visited: https://example.com
# etc.
```

### Specific logger filtering:

```python
# Just Spider logs
logging.getLogger("linktrace.Spider").setLevel(logging.DEBUG)

# Just Crawler logs
logging.getLogger("linktrace.Crawler").setLevel(logging.DEBUG)

# Silence everything else
logging.getLogger().setLevel(logging.WARNING)
```

---

## Common Mistakes

### ❌ Not using async context manager

```python
# Wrong
crawler = Crawler()
doc = await crawler.crawl_document_async(url)  # Session is None!

# Correct
async with Crawler() as crawler:
    doc = await crawler.crawl_document_async(url)
```

### ❌ Forgetting `await`

```python
# Wrong
spider = Spider(start_url="https://example.com")
documents = spider.run_async()  # Returns coroutine, not documents!

# Correct
spider = Spider(start_url="https://example.com")
documents = await spider.run_async()
```

### ❌ Invalid traversal_strategy

```python
# Wrong
spider = Spider(start_url="...", traversal_strategy="dfs-fast")

# Correct
spider = Spider(start_url="...", traversal_strategy="dfs")  # or "bfs"
```

### ❌ Expecting JavaScript execution from the default fetcher

```python
# Finds nothing - the default HTTP fetcher doesn't execute JavaScript
spider = Spider(start_url="https://react-app.example.com")

# Correct: render in a headless browser (pip install linktrace[browser])
from linktrace import RoutingFetcher
spider = Spider(start_url="https://react-app.example.com", fetcher=RoutingFetcher())
```

### ❌ Calling `run()` inside Jupyter

```python
# Wrong - Jupyter already runs an event loop
documents = spider.run()   # RuntimeError

# Correct
documents = await spider.run_async()
```

---

## Getting Help

1. **Check the logs** — Enable DEBUG logging
2. **Verify network** — Test URL in browser
3. **Check docs** — See [API Reference](api-reference.md) and [Examples](examples.md)
4. **File an issue** — Include logs, error message, minimal reproduction
