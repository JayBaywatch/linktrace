# LinkTrace

LinkTrace is a document-oriented crawler. Every crawled page becomes a rich Document object containing metadata, content, and discovered relationships.

**Perfect for:** Site structure analysis, link tracking, concurrent page fetching, HTML document transformation.

**Not:** A Scrapy replacement. Scrapy is a powerful full-featured framework — linktrace is deliberately lightweight with no pipelines, middleware, or project scaffolding to configure. If you want crawling results in minutes rather than hours of setup, and a gentler learning curve, linktrace is for you.

## Quick Start

```bash
pip install linktrace
```

```python
import asyncio
from linktrace import Spider

async def main():
    spider = Spider(start_url="https://example.com", max_depth=2)
    documents = await spider.run_async()
    for doc in documents:
        print(doc.title, len(doc.internal_links))

asyncio.run(main())
```

## Documentation

- [Getting Started](getting-started.md) — installation and your first crawl
- [Core Concepts](core-concepts.md) — Spider, Crawler, and the Document model
- [API Reference](api-reference.md) — classes, parameters, and return types
- [Examples](examples.md) — common crawling recipes
- [Troubleshooting](troubleshooting.md) — fixes for common issues

## Links

- [PyPI](https://pypi.org/project/linktrace/)
- [GitHub](https://github.com/JayBaywatch/linktrace)
- [Issues](https://github.com/JayBaywatch/linktrace/issues)
- [Changelog](https://github.com/JayBaywatch/linktrace/releases)
