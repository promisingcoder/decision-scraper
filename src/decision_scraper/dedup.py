"""URL normalization and deduplication."""

from urllib.parse import urlparse, urlunparse


def normalize_url(url: str) -> str:
    """Normalize a URL for deduplication.

    - Lowercases the scheme and host.
    - Strips fragments (#...).
    - Strips trailing slashes from path (keeps "/" for root).
    - Strips all query parameters (corporate pages are path-based;
      query params are almost always analytics trackers).
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", "", ""))


class URLDeduplicator:
    """Set-based URL deduplication."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def is_new(self, url: str) -> bool:
        """Return True if the URL has not been seen before, and mark it seen."""
        norm = normalize_url(url)
        if norm in self._seen:
            return False
        self._seen.add(norm)
        return True

    @property
    def count(self) -> int:
        return len(self._seen)
