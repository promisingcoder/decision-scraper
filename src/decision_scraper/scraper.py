"""Main orchestrator — multi-level BFS crawl with concurrent LLM extraction."""

import asyncio
import logging
import re
from typing import Optional

from .crawler import CrawlManager
from .dedup import URLDeduplicator
from .link_discovery import filter_internal_links, get_base_domain, score_url
from .models import DecisionMaker, ScrapeResult
from .resources import ResourceMonitor

logger = logging.getLogger(__name__)

DEFAULT_MAX_PAGES = 50

# Prefixes/suffixes to strip for fuzzy name dedup
_NAME_PREFIXES = re.compile(
    r"^(dr\.?|mr\.?|mrs\.?|ms\.?|prof\.?|rev\.?)\s+", re.IGNORECASE
)


def _normalize_name(name: str) -> str:
    """Normalize a name for dedup: strip titles, lowercase, collapse whitespace."""
    n = name.strip().lower()
    n = _NAME_PREFIXES.sub("", n)
    # Strip credential suffixes like ", DDS" or ", DMD" or ", MD"
    n = re.sub(r",?\s*(dds|dmd|md|do|phd|esq|jr\.?|sr\.?|ii|iii|iv)\.?\s*$", "", n, flags=re.IGNORECASE)
    return " ".join(n.split())


def _is_duplicate(dm: DecisionMaker, existing: list[DecisionMaker]) -> bool:
    """Check if dm is a duplicate of any entry in existing (fuzzy name match).

    Matches if:
    - Normalized names are identical, OR
    - One normalized name is a substring of the other (handles "Madaan" vs "Gauri Madaan")
    """
    norm = _normalize_name(dm.name)
    if not norm:
        return True  # empty name → treat as duplicate
    for other in existing:
        other_norm = _normalize_name(other.name)
        if norm == other_norm:
            return True
        # One name is contained in the other (handles last-name-only matches)
        if len(norm) >= 3 and len(other_norm) >= 3:
            if norm in other_norm or other_norm in norm:
                return True
    return False


async def scrape_decision_makers(
    url: str,
    api_token: str,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_workers: Optional[int] = None,
) -> ScrapeResult:
    """Scrape a website for decision makers.

    This is the primary public API.

    Uses a multi-level BFS: every crawled page feeds newly discovered links
    back into the frontier (scored and filtered), so the scraper keeps
    expanding coverage until max_pages is reached or no new relevant pages
    remain.

    Args:
        url: Root website URL to scrape.
        api_token: OpenAI API key.
        max_pages: Maximum number of pages to crawl (default 50).
        max_workers: Override for max concurrent workers (None = auto-detect).

    Returns:
        ScrapeResult with all found decision makers.
    """
    resource_monitor = ResourceMonitor()
    if max_workers is None:
        max_workers = resource_monitor.calculate_optimal_workers()

    logger.info(f"Starting scrape of {url} with max_workers={max_workers}")
    logger.info(f"Resource snapshot: {resource_monitor.get_snapshot()}")

    crawl_manager = CrawlManager(api_token, resource_monitor)
    dedup = URLDeduplicator()

    all_decision_makers: list[DecisionMaker] = []
    errors: list[str] = []
    pages_crawled = 0
    pages_skipped = 0

    base_domain = get_base_domain(url)
    semaphore = asyncio.Semaphore(max_workers)

    # BFS frontier — queue of URLs to crawl, ordered by priority
    # Start with the root URL
    frontier: asyncio.Queue[str] = asyncio.Queue()
    frontier.put_nowait(url)
    dedup.is_new(url)  # Mark root as seen
    total_queued = 1

    def _expand_frontier(internal_links: list[dict]) -> int:
        """Score, filter, and add new links to the frontier. Returns count added."""
        nonlocal total_queued
        prioritized = filter_internal_links(internal_links, base_domain, url)
        added = 0
        for link_url in prioritized:
            if total_queued >= max_pages:
                break
            if dedup.is_new(link_url):
                frontier.put_nowait(link_url)
                total_queued += 1
                added += 1
        return added

    try:
        # Phase 1: Discover links from the homepage using crawl4ai
        logger.info(f"Phase 1: Discovering links from {url}")
        homepage_result = await crawl_manager.crawl_for_links(url)
        if homepage_result["success"]:
            internal_links = homepage_result["internal_links"]
            added = _expand_frontier(internal_links)
            logger.info(
                f"Homepage yielded {len(internal_links)} internal links, "
                f"{added} added to frontier (total: {total_queued})"
            )
        else:
            logger.warning(f"Failed to discover links from homepage: {url}")

        # Phase 2: Multi-level BFS — crawl pages, extract decision makers,
        # and feed newly discovered links back into the frontier.
        logger.info(f"Phase 2: BFS extraction (frontier: {total_queued} pages, cap: {max_pages})")

        async def _process_page(page_url: str) -> None:
            nonlocal pages_crawled, pages_skipped
            async with semaphore:
                logger.debug(f"Processing: {page_url}")
                try:
                    makers, new_links = await crawl_manager.crawl_and_extract(page_url)
                    all_decision_makers.extend(makers)
                    pages_crawled += 1

                    # Feed new links back into frontier (multi-level BFS)
                    if new_links and total_queued < max_pages:
                        added = _expand_frontier(new_links)
                        if added > 0:
                            logger.debug(
                                f"  {page_url} yielded {added} new frontier URLs "
                                f"(total: {total_queued})"
                            )
                except Exception as e:
                    errors.append(f"{page_url}: {e!s}")
                    pages_skipped += 1

        # Drain the frontier in waves. After each wave, check if new URLs
        # were added (by pages in that wave discovering new links).
        while not frontier.empty():
            # Collect current wave
            wave: list[str] = []
            while not frontier.empty():
                wave.append(frontier.get_nowait())

            logger.info(f"  Wave: processing {len(wave)} pages...")

            tasks = [_process_page(page_url) for page_url in wave]
            await asyncio.gather(*tasks, return_exceptions=True)

        # Deduplicate decision makers by name (fuzzy — handles
        # "Dr. Gauri Madaan" vs "Gauri Madaan" vs "Dr. Madaan")
        unique_makers: list[DecisionMaker] = []
        for dm in all_decision_makers:
            if not _is_duplicate(dm, unique_makers):
                unique_makers.append(dm)

        logger.info(
            f"Done: {len(unique_makers)} unique decision makers found "
            f"from {pages_crawled} pages ({total_queued} queued, "
            f"{pages_skipped} skipped)"
        )

    finally:
        await crawl_manager.close()

    return ScrapeResult(
        url=url,
        decision_makers=unique_makers,
        pages_crawled=pages_crawled,
        pages_skipped=pages_skipped,
        errors=errors,
    )


async def scrape_multiple(
    urls: list[str],
    api_token: str,
    max_pages_per_site: int = DEFAULT_MAX_PAGES,
) -> list[ScrapeResult]:
    """Scrape multiple websites sequentially.

    Each site gets its own CrawlManager/browser to avoid cross-contamination.
    Sites are processed sequentially; pages within a site are concurrent.
    """
    results: list[ScrapeResult] = []
    for site_url in urls:
        logger.info(f"\n{'='*60}\nScraping site: {site_url}\n{'='*60}")
        try:
            result = await scrape_decision_makers(
                url=site_url,
                api_token=api_token,
                max_pages=max_pages_per_site,
            )
            results.append(result)
        except Exception as e:
            logger.error(f"Failed to scrape {site_url}: {e}")
            results.append(ScrapeResult(url=site_url, errors=[str(e)]))
    return results
