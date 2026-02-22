"""Crawl4ai-only crawler with link discovery and LLM extraction."""

import json
import logging
import os
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

# Executive title keywords used for post-extraction validation
QUALIFYING_TITLES = [
    "owner", "ceo", "founder", "co-founder", "president",
    "vp", "vice president", "director", "partner", "principal",
    "chief", "cto", "cfo", "coo", "cmo", "cio", "cpo",
    "managing director", "general manager", "dentist", "doctor",
    "dds", "dmd", "md", "physician", "surgeon",
]


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

        # Validate each entry
        validated: list[DecisionMaker] = []
        for entry in data_list:
            try:
                dm = DecisionMaker.model_validate(entry)

                # Name must be a real name (not a URL, not empty)
                if not dm.name or len(dm.name.strip()) < 2:
                    continue
                if dm.name.startswith("http"):
                    continue

                # Title validation: must contain a qualifying keyword
                if dm.title:
                    title_lower = dm.title.lower()
                    if not any(q in title_lower for q in QUALIFYING_TITLES):
                        continue  # Skip non-decision-makers
                else:
                    # No title at all — skip (we need at least a title
                    # to confirm they are a decision maker)
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
