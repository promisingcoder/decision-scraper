"""Pydantic models for decision-maker extraction."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class DecisionMaker(BaseModel):
    """A single decision-maker extracted from a web page."""

    name: str = Field(
        description="Full name of the decision maker. Must be explicitly stated on the page."
    )
    title: Optional[str] = Field(
        default=None,
        description=(
            "Job title exactly as written on the page. "
            "Must be a senior/executive role: Owner, CEO, Founder, Co-Founder, "
            "President, Vice President, VP, Director, Managing Director, Partner, "
            "Chief Officer (CTO, CFO, COO, CMO, etc.). "
            "Return null if the title is not explicitly stated."
        ),
    )
    email: Optional[str] = Field(
        default=None,
        description="Email address. Must appear on the page. Return null if not found.",
    )
    phone: Optional[str] = Field(
        default=None,
        description="Phone number. Must appear on the page. Return null if not found.",
    )
    linkedin: Optional[str] = Field(
        default=None,
        description="LinkedIn profile URL. Must appear on the page as a link. Return null if not found.",
    )


class DecisionMakersResponse(BaseModel):
    """Container returned by the LLM for each page."""

    decision_makers: list[DecisionMaker] = Field(
        default_factory=list,
        description=(
            "List of decision makers found on this page. "
            "Only include people whose name AND a qualifying senior title are "
            "BOTH explicitly visible on the page. "
            "If no decision makers are found, return an empty list."
        ),
    )


class ScrapeResult(BaseModel):
    """Final result returned to the library consumer."""

    url: str = Field(description="The root website URL that was scraped")
    decision_makers: list[DecisionMaker] = Field(default_factory=list)
    pages_crawled: int = Field(default=0)
    pages_skipped: int = Field(default=0)
    errors: list[str] = Field(default_factory=list)
