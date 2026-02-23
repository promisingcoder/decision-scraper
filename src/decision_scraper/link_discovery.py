"""Link filtering, scoring, and frontier management."""

from urllib.parse import urljoin, urlparse

# Keywords that strongly suggest decision-maker content (high priority)
HIGH_PRIORITY_KEYWORDS = [
    # Corporate team/leadership pages
    "about", "team", "leadership", "executive", "management",
    "staff", "people", "founders", "directors", "board",
    "our-team", "our-people", "who-we-are", "meet-the-team",
    "meet-us", "bios", "principals", "partners",
    # Professional practices (dental, medical, legal)
    "doctor", "dentist", "provider", "attorney", "our-doctor",
    "our-staff", "our-providers", "meet-our",
    # Small business / local service pages
    "about-us", "our-story", "our-company", "who-we-are",
    "why-us", "why-choose", "credentials", "license",
    "owner", "our-owner", "meet-the-owner",
]

# Keywords for contact pages (medium priority — may have names + emails)
MEDIUM_PRIORITY_KEYWORDS = [
    "contact", "contact-us", "get-in-touch", "reach-us",
    # Small business pages that often mention the owner
    "reviews", "testimonial", "warranty", "guarantee",
]

# Keywords for pages to skip entirely
SKIP_KEYWORDS = [
    "blog", "news", "press", "article", "post", "category",
    "tag", "cart", "shop", "product", "pricing", "faq",
    "privacy", "terms", "cookie", "sitemap", "feed", "rss",
    "login", "signup", "register", "account", "checkout",
    "wp-content", "wp-admin", "wp-json",
    "cdn-cgi", ".pdf", ".jpg", ".png", ".gif", ".svg",
    ".css", ".js", ".zip", ".xml", ".ico", ".woff", ".ttf",
]


def score_url(url: str) -> int:
    """Score a URL for relevance to decision-maker discovery.

    Returns:
        2 = high priority (team/about pages)
        1 = medium priority (contact pages)
        0 = neutral (homepage or unknown)
       -1 = skip (blog, shop, etc.)
    """
    path = urlparse(url).path.lower()

    for kw in SKIP_KEYWORDS:
        if kw in path:
            return -1

    for kw in HIGH_PRIORITY_KEYWORDS:
        if kw in path:
            return 2

    for kw in MEDIUM_PRIORITY_KEYWORDS:
        if kw in path:
            return 1

    return 0


def get_base_domain(url: str) -> str:
    """Extract the base domain from a URL."""
    return urlparse(url).netloc.lower()


def filter_internal_links(
    links: list[dict],
    base_domain: str,
    base_url: str,
) -> list[str]:
    """Filter and sort internal links by relevance.

    Args:
        links: list of link dicts with "href" key.
        base_domain: the domain we are scraping (e.g. "uniprecision.com").
        base_url: the root URL for resolving relative links.

    Returns:
        List of absolute URLs, sorted by priority (highest first),
        excluding URLs scored as -1 (skip).
    """
    candidates: list[tuple[int, str]] = []
    for link in links:
        href = link.get("href", "")
        if not href:
            continue

        # Resolve relative URLs
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)

        # Ensure same domain
        if base_domain not in parsed.netloc.lower():
            continue

        score = score_url(absolute)
        if score >= 0:
            candidates.append((score, absolute))

    # Sort descending by score, then alphabetical for determinism
    candidates.sort(key=lambda x: (-x[0], x[1]))
    return [url for _, url in candidates]
