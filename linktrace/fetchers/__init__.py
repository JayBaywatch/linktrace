"""Pluggable page fetchers: plain HTTP, headless browser, or routed per URL."""

from linktrace.fetchers.base import (
    FetchContext,
    Fetcher,
    FetchError,
    FetchResult,
    TransientFetchError,
)
from linktrace.fetchers.browser import BrowserFetcher
from linktrace.fetchers.http import HttpFetcher
from linktrace.fetchers.routing import RoutingFetcher, looks_like_spa_shell

__all__ = [
    "BrowserFetcher",
    "FetchContext",
    "FetchError",
    "FetchResult",
    "Fetcher",
    "HttpFetcher",
    "RoutingFetcher",
    "TransientFetchError",
    "looks_like_spa_shell",
]
