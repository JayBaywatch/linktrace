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

**Problem:** Too many concurrent requests.

**Solution:** Wait between crawls or reduce depth:

```python
import asyncio

spider = Spider(start_url="https://example.com", max_depth=1)
documents = await spider.run_async()

# Wait before next crawl
await asyncio.sleep(5)

spider2 = Spider(start_url="https://example.com/section2", max_depth=1)
documents2 = await spider2.run_async()
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
- JavaScript-generated links (linktrace doesn't execute JS)
- Links hidden behind `onclick` or `data-href`
- Page returned error status (check `doc.status_code`)

**Solution for JS-heavy sites:** Use Selenium or Playwright instead.

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

3. **Try BFS instead of DFS (or vice versa):**
   ```python
   # DFS might find slow branch first
   spider = Spider(
       start_url="https://example.com",
       traversal_strategy="bfs"  # Try this instead
   )
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

### ❌ Expecting JavaScript execution

```python
# Won't work - linktrace doesn't execute JavaScript
spider = Spider(start_url="https://react-app.example.com")
documents = await spider.run_async()

# Solution: Use Playwright or Selenium for JS-heavy sites
```

---

## Getting Help

1. **Check the logs** — Enable DEBUG logging
2. **Verify network** — Test URL in browser
3. **Check docs** — See [API Reference](api-reference.md) and [Examples](examples.md)
4. **File an issue** — Include logs, error message, minimal reproduction
