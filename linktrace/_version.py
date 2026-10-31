"""Package version and the default User-Agent derived from it.

Kept free of package imports so Crawler, Spider and SitemapParser can use it
for their defaults without import cycles.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("linktrace")
except PackageNotFoundError:  # pragma: no cover - running from an unbuilt checkout
    __version__ = "0.0.0+unknown"

DEFAULT_USER_AGENT = f"linktrace/{__version__}"
