"""decision-scraper: Generic decision-maker scraper for any website."""

from .models import DecisionMaker, ScrapeResult
from .scraper import scrape_decision_makers, scrape_multiple

__all__ = [
    "DecisionMaker",
    "ScrapeResult",
    "scrape_decision_makers",
    "scrape_multiple",
]
