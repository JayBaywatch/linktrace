# Getting Started

## Installation

### From PyPI

```bash
pip install webcrawler
```

### With Optional Export Formats

```bash
# All three: pandas, polars, pyarrow
pip install webcrawler[serializers]

# Individual formats
pip install webcrawler[pandas]
pip install webcrawler[polars]
pip install webcrawler[pyarrow]
```

### Development Installation

```bash
git clone https://github.com/yourusername/webcrawler
cd webcrawler
pip install -e .
pip install -e ".[serializers]"  # Optional formats
```

## Your First Crawl

### 1. Basic Example

```python
import asyncio
from WebCrawler import Spider

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
from WebCrawler import Serializers

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

## Jupyter Notebook

See `notebooks/crawl_cnn.ipynb` for interactive examples with Jupyter:

```bash
jupyter notebook notebooks/crawl_cnn.ipynb
```

The notebook demonstrates:
- Basic crawling
- Analyzing link structure
- Exporting to JSON
- Pandas/Polars/PyArrow analysis

## Next Steps

- Read [Core Concepts](core-concepts.md) to understand Spider, Crawler, and Document
- See [Examples](examples.md) for more patterns
- Check [API Reference](api-reference.md) for complete method docs
- Browse [Troubleshooting](troubleshooting.md) if issues arise
