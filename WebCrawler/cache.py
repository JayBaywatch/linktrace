"""Disk-based response caching for WebCrawler."""

import hashlib
import json
from pathlib import Path


class CachedResponse:
    """Cached HTTP response data."""

    def __init__(self, status_code: int, response_headers: dict, content: str):
        self.status_code = status_code
        self.response_headers = response_headers
        self.content = content


class ResponseCache:
    """Disk-based response cache with TTL support."""

    def __init__(self, cache_dir: str, ttl_seconds: int = 86400):
        """Initialize cache.

        Args:
            cache_dir: Directory to store cache files
            ttl_seconds: Time-to-live for cached responses (default 1 day)
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl_seconds

    def _url_hash(self, url: str) -> str:
        """Generate cache file name from URL."""
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def _cache_path(self, url: str) -> Path:
        """Get cache file path for URL."""
        return self.cache_dir / f"{self._url_hash(url)}.json"

    async def get(self, url: str) -> CachedResponse | None:
        """Retrieve cached response if not expired.

        Args:
            url: URL to retrieve from cache

        Returns:
            CachedResponse if found and not expired, None otherwise
        """
        cache_file = self._cache_path(url)
        if not cache_file.exists():
            return None

        try:
            with open(cache_file) as f:
                data = json.load(f)

            # Check TTL
            import time

            age = time.time() - data["timestamp"]
            if age > self.ttl:
                cache_file.unlink()  # Delete expired cache
                return None

            return CachedResponse(
                status_code=data["status_code"],
                response_headers=data["response_headers"],
                content=data["content"],
            )
        except (json.JSONDecodeError, KeyError):
            # Cache file corrupted, remove it
            cache_file.unlink()
            return None

    async def set(
        self, url: str, status_code: int, headers: dict, content: str
    ) -> None:
        """Store response in cache.

        Args:
            url: URL being cached
            status_code: HTTP status code
            headers: Response headers dict
            content: Response body text
        """
        cache_file = self._cache_path(url)

        import time

        data = {
            "url": url,
            "timestamp": time.time(),
            "status_code": status_code,
            "response_headers": headers,
            "content": content,
        }

        try:
            with open(cache_file, "w") as f:
                json.dump(data, f)
        except OSError:
            # Silently skip cache write if filesystem issues
            pass

    async def clear(self) -> None:
        """Clear all cached responses."""
        import shutil

        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
