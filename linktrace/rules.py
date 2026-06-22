"""URL filtering rules for controlling which links a Spider follows.

A :class:`CrawlRules` instance describes include/exclude policy across several
independent dimensions (regex, path prefixes, file extensions, query params and
domains). It is consulted by the :class:`~linktrace.Spider.Spider` before a
discovered link is queued. Empty rules allow everything, so an unconfigured
Spider behaves exactly as before.
"""

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse


def _host(netloc: str) -> str:
    """Return the lowercase hostname portion of a netloc (drops any port)."""
    return netloc.split(":", 1)[0].lower()


def _extension(path: str) -> str:
    """Return the lowercase file extension of a URL path without the dot.

    Returns "" when the final path segment has no extension (e.g. ``/homes/``),
    which is the common case for HTML pages.
    """
    last = path.rsplit("/", 1)[-1]
    if "." in last:
        return last.rsplit(".", 1)[-1].lower()
    return ""


@dataclass
class CrawlRules:
    """Declarative include/exclude policy for crawl URLs.

    All fields are optional. Evaluation is deterministic and exclusions always
    win over inclusions. For each dimension, a populated *allow* list acts as a
    whitelist (the URL must match at least one entry), while a *block* list acts
    as a blacklist (any match rejects the URL).

    Args:
        include_patterns: Regexes; if non-empty the URL must match at least one.
        exclude_patterns: Regexes; any match rejects the URL.
        include_path_prefixes: If non-empty, the path must start with one of these.
        exclude_path_prefixes: Any path starting with one of these is rejected.
        allowed_extensions: If non-empty, only these file extensions are kept.
            Use "" to permit extensionless paths (typical HTML pages).
        blocked_extensions: These file extensions are always rejected.
        exclude_query_params: URLs carrying any of these query keys are rejected
            (e.g. ``sort``, ``page``, calendar params that create crawl traps).
        allowed_domains: If non-empty, the host must equal or be a subdomain of
            one of these.
        blocked_domains: The host equalling or being a subdomain of one of these
            is rejected.
    """

    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    include_path_prefixes: list[str] = field(default_factory=list)
    exclude_path_prefixes: list[str] = field(default_factory=list)
    allowed_extensions: list[str] = field(default_factory=list)
    blocked_extensions: list[str] = field(default_factory=list)
    exclude_query_params: list[str] = field(default_factory=list)
    allowed_domains: list[str] = field(default_factory=list)
    blocked_domains: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Pre-compile regexes once; normalize extensions/domains for cheap compares.
        self._include_re: list[re.Pattern[str]] = [
            re.compile(p) for p in self.include_patterns
        ]
        self._exclude_re: list[re.Pattern[str]] = [
            re.compile(p) for p in self.exclude_patterns
        ]
        self._allowed_ext = {e.lstrip(".").lower() for e in self.allowed_extensions}
        self._blocked_ext = {e.lstrip(".").lower() for e in self.blocked_extensions}
        self._allowed_domains = [d.lower() for d in self.allowed_domains]
        self._blocked_domains = [d.lower() for d in self.blocked_domains]
        self._exclude_query = set(self.exclude_query_params)

    @staticmethod
    def _domain_matches(host: str, domain: str) -> bool:
        """True if host equals domain or is a subdomain of it."""
        return host == domain or host.endswith("." + domain)

    def allows(self, url: str) -> bool:
        """Return True if ``url`` passes every configured rule."""
        parsed = urlparse(url)
        host = _host(parsed.netloc)
        path = parsed.path or "/"

        # --- Domain rules ---
        if any(self._domain_matches(host, d) for d in self._blocked_domains):
            return False
        if self._allowed_domains and not any(
            self._domain_matches(host, d) for d in self._allowed_domains
        ):
            return False

        # --- Extension rules ---
        ext = _extension(path)
        if ext in self._blocked_ext:
            return False
        if self._allowed_ext and ext not in self._allowed_ext:
            return False

        # --- Path prefix rules ---
        if any(path.startswith(p) for p in self.exclude_path_prefixes):
            return False
        if self.include_path_prefixes and not any(
            path.startswith(p) for p in self.include_path_prefixes
        ):
            return False

        # --- Query param rules ---
        if self._exclude_query:
            params = parse_qs(parsed.query)
            if self._exclude_query & params.keys():
                return False

        # --- Regex rules (evaluated against the full URL) ---
        if any(r.search(url) for r in self._exclude_re):
            return False
        if self._include_re and not any(r.search(url) for r in self._include_re):
            return False

        return True
