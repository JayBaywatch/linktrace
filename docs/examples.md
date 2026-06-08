# Examples

## 1. Basic Crawl

Crawl a site and print all pages.

```python
import asyncio
from WebCrawler import Spider

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
from WebCrawler import Spider

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
from WebCrawler import Spider, Serializers

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
from WebCrawler import Spider

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
from WebCrawler import Spider
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
from WebCrawler import Spider

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
from WebCrawler import Spider

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
from WebCrawler import Spider

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
from WebCrawler import Spider, Serializers

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

Identify 404s and other errors on internal links.

```python
from WebCrawler import Spider

async def main():
    spider = Spider(start_url="https://example.com", max_depth=2)
    documents = await spider.run_async()
    
    broken = []
    for doc in documents:
        for link in doc.internal_links:
            # Find if this link was also crawled
            linked_doc = next(
                (d for d in documents if d.url == link.url),
                None
            )
            
            if linked_doc and linked_doc.status_code != 200:
                broken.append({
                    'from': doc.url,
                    'to': link.url,
                    'status': linked_doc.status_code,
                    'text': link.text
                })
    
    print(f"Found {len(broken)} broken internal links:")
    for item in broken:
        print(f"  {item['from']} → {item['to']} ({item['status']})")

asyncio.run(main())
```

## 11. Batch Processing

Process large crawls in memory-efficient batches.

```python
from WebCrawler import Crawler

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
from WebCrawler import Spider

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
from WebCrawler import Spider

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
from WebCrawler import Spider

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
from WebCrawler import Spider

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
from WebCrawler import Spider

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
