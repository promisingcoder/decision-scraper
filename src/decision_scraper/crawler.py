"""Crawl4ai-only crawler with link discovery and LLM extraction."""

import json
import logging
import os
import re
import sys
from typing import Optional

# Fix Windows charmap encoding issues before importing crawl4ai
if sys.platform == "win32":
    os.environ.setdefault("PYTHONUTF8", "1")

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

from .extraction import build_extraction_strategy
from .models import DecisionMaker
from .resources import ResourceMonitor

logger = logging.getLogger(__name__)

# Titles/roles that confirm someone is a decision maker.
# Used for soft validation — if the LLM returns a title containing any of
# these, we are confident. If the title is something else, we still accept
# it as long as the name passes basic sanity checks (the LLM prompt is
# engineered to only return owners/decision makers).
KNOWN_DECISION_ROLES = re.compile(
    r"owner|ceo|founder|co-founder|president|vp|vice.president|director|"
    r"partner|principal|chief|cto|cfo|coo|cmo|cio|cpo|"
    r"managing.director|general.manager|"
    r"plumb|electric|contrac|hvac|roofing|landscap|"
    r"master|licensed|journeyman|"
    r"dentist|dds|dmd|doctor|md|physician|surgeon|"
    r"attorney|lawyer|cpa|architect|engineer|"
    r"broker|realtor|agent",
    re.IGNORECASE,
)

# Names that are clearly NOT real person names — reject these.
_JUNK_NAME_PATTERNS = re.compile(
    r"^(http|www\.|/|@|#|\d{3,}|n/?a$|none$|null$|unknown$|"
    r"team$|staff$|our team$|contact us$|home$|services?$)",
    re.IGNORECASE,
)

# Names that look like business names rather than person names.
_BUSINESS_NAME_WORDS = re.compile(
    r"\b(service|plumbing|electric|hvac|roofing|dental|clinic|"
    r"company|inc|llc|corp|ltd|group|associates|solutions|"
    r"construction|repair|maintenance|installation)\b",
    re.IGNORECASE,
)

# Titles that indicate someone is NOT a decision maker — reject these.
# This is a blocklist approach: if the title matches, the person is almost
# certainly not an owner/executive.  We use a function instead of a single
# regex so we can handle the "General Manager" exception cleanly.
_NON_DECISION_TITLE_WORDS = re.compile(
    r"team.lead|coordinator|"
    r"technician|\btech\b|assistant|receptionist|dispatcher|"
    r"secretary|clerk|\bintern\b|trainee|"
    r"specialist|analyst|developer|designer|"
    r"accountant|bookkeeper|payroll|"
    r"customer.service|\bsupport\b|"
    r"estimator|supervisor|foreman",
    re.IGNORECASE,
)

# "Manager" is tricky — "General Manager" IS a decision maker, but
# "Project Manager", "Content Manager" etc. are not.
_MANAGER_PATTERN = re.compile(r"\bmanager\b", re.IGNORECASE)
_MANAGER_EXCEPTIONS = re.compile(r"general.manager|managing", re.IGNORECASE)


def _is_non_decision_title(title: str) -> bool:
    """Return True if the title indicates a non-decision-maker role."""
    if _NON_DECISION_TITLE_WORDS.search(title):
        return True
    # Check "manager" separately with exceptions
    if _MANAGER_PATTERN.search(title) and not _MANAGER_EXCEPTIONS.search(title):
        return True
    return False


class CrawlManager:
    """Manages crawling using crawl4ai for both link discovery and extraction."""

    def __init__(self, api_token: str, resource_monitor: ResourceMonitor) -> None:
        self.api_token = api_token
        self.resource_monitor = resource_monitor
        self._crawler: Optional[AsyncWebCrawler] = None
        self._extraction_strategy = build_extraction_strategy(api_token)

    async def _ensure_crawler(self) -> AsyncWebCrawler:
        """Lazy-init the crawl4ai crawler."""
        if self._crawler is None:
            browser_config = BrowserConfig(
                headless=True,
                text_mode=True,
                verbose=False,
            )
            self._crawler = AsyncWebCrawler(config=browser_config)
            await self._crawler.start()
        return self._crawler

    async def crawl_for_links(self, url: str) -> dict:
        """Crawl a URL with crawl4ai and return its internal links.

        No LLM extraction — just fetches the page and collects links.

        Returns:
            {
                "internal_links": [{"href": ..., "text": ...}, ...],
                "success": bool,
            }
        """
        crawler = await self._ensure_crawler()
        config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            wait_until="domcontentloaded",
            page_timeout=30000,
        )
        try:
            result = await crawler.arun(url=url, config=config)
            if result.success:
                internal = result.links.get("internal", [])
                return {
                    "internal_links": internal,
                    "success": True,
                }
        except Exception as e:
            logger.warning(f"Link discovery failed for {url}: {e}")

        return {
            "internal_links": [],
            "success": False,
        }

    async def crawl_and_extract(self, url: str) -> tuple[list[DecisionMaker], list[dict]]:
        """Crawl a URL, extract decision makers via LLM, AND return links.

        Returns both extracted decision makers and internal links discovered
        on this page (for multi-level BFS — every page feeds the frontier).
        """
        crawler = await self._ensure_crawler()
        config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            extraction_strategy=self._extraction_strategy,
            wait_until="domcontentloaded",
            page_timeout=30000,
        )

        try:
            result = await crawler.arun(url=url, config=config)
        except Exception as e:
            logger.warning(f"Crawl failed for {url}: {e}")
            return [], []

        if not result.success:
            logger.warning(f"Crawl unsuccessful for {url}: {result.error_message}")
            return [], []

        # Collect internal links from this page for frontier expansion
        internal_links = result.links.get("internal", [])

        # Extract decision makers
        decision_makers: list[DecisionMaker] = []
        if result.extracted_content:
            decision_makers = self._parse_extraction(result.extracted_content)

        return decision_makers, internal_links

    def _parse_extraction(self, raw: str) -> list[DecisionMaker]:
        """Parse and validate the LLM extraction output."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("LLM returned invalid JSON")
            return []

        # crawl4ai may return a list of chunk results or a single dict
        if isinstance(data, list):
            all_makers: list[dict] = []
            for item in data:
                if isinstance(item, dict):
                    makers = item.get("decision_makers", [item])
                    if isinstance(makers, list):
                        all_makers.extend(makers)
            data_list = all_makers
        elif isinstance(data, dict):
            data_list = data.get("decision_makers", [])
        else:
            return []

        # Validate each entry — balanced validation that trusts the LLM
        # for decision-maker identification but filters out:
        # 1. Junk/invalid names
        # 2. People with titles that are clearly non-decision-maker roles
        validated: list[DecisionMaker] = []
        for entry in data_list:
            try:
                dm = DecisionMaker.model_validate(entry)

                name = dm.name.strip()

                # Reject empty / too-short names
                if len(name) < 2:
                    continue

                # Reject names that are clearly not person names
                if _JUNK_NAME_PATTERNS.search(name):
                    continue

                # Name must have at least one letter
                if not any(c.isalpha() for c in name):
                    continue

                # Reject names that look like business names
                if _BUSINESS_NAME_WORDS.search(name):
                    logger.debug(f"Filtered business name: {name}")
                    continue

                # Reject if title is a known non-decision-maker role
                if dm.title and _is_non_decision_title(dm.title):
                    logger.debug(f"Filtered non-decision-maker: {name} ({dm.title})")
                    continue

                # Reject first-name-only entries with no title
                # (likely junk from the LLM guessing)
                if dm.title is None and " " not in name:
                    logger.debug(f"Filtered first-name-only with no title: {name}")
                    continue

                validated.append(dm)
            except Exception:
                continue

        return validated

    async def close(self) -> None:
        """Clean up crawler/browser resources."""
        if self._crawler:
            try:
                await self._crawler.close()
            except Exception as e:
                logger.debug(f"Error closing crawler: {e}")
            self._crawler = None
