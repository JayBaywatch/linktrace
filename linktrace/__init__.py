"""WebCrawler — async web crawler / spider."""

from linktrace._version import __version__
from linktrace.cache import ResponseCache
from linktrace.Crawler import BrokenLink, Crawler, CrawlException, Document, HtmlLink
from linktrace.fetchers import (
    BrowserFetcher,
    FetchContext,
    Fetcher,
    FetchError,
    FetchResult,
    HttpFetcher,
    ResponseTooLarge,
    RoutingFetcher,
    TransientFetchError,
    looks_like_spa_shell,
)
from linktrace.rules import CrawlRules
from linktrace.Serializers import Serializers
from linktrace.sitemap import SitemapParser
from linktrace.Spider import FlushError, Spider

__all__ = [
    "__version__",
    "BrokenLink",
    "BrowserFetcher",
    "Crawler",
    "CrawlException",
    "CrawlRules",
    "Document",
    "FetchContext",
    "Fetcher",
    "FetchError",
    "FetchResult",
    "FlushError",
    "HtmlLink",
    "HttpFetcher",
    "ResponseCache",
    "ResponseTooLarge",
    "RoutingFetcher",
    "Serializers",
    "SitemapParser",
    "Spider",
    "TransientFetchError",
    "looks_like_spa_shell",
]
