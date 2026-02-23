"""Pydantic models for decision-maker extraction."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class DecisionMaker(BaseModel):
    """A single decision-maker extracted from a web page."""

    name: str = Field(
        description="Full name of the business owner or decision maker. Must be explicitly stated on the page."
    )
    title: Optional[str] = Field(
        default=None,
        description=(
            "Their role or title. Use exactly what the page says if available. "
            "If the page doesn't state an explicit title but the person is "
            "clearly the business owner (their name is the business, they hold "
            "the license, they are the only person featured), use 'Owner'. "
            "Examples: Owner, CEO, Founder, Master Plumber, Licensed Contractor, "
            "Dentist, President, Director, Partner. "
            "Return null only if you truly cannot determine their role."
        ),
    )
    email: Optional[str] = Field(
        default=None,
        description=(
            "Email address. On small business sites the main contact email "
            "IS the owner's email. Return null if no email found on the page."
        ),
    )
    phone: Optional[str] = Field(
        default=None,
        description=(
            "Phone number. On small business sites the main phone number "
            "IS the owner's phone. Return null if no phone found on the page."
        ),
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
            "List of business owners or decision makers found on this page. "
            "Include anyone who owns or runs the business — even on small "
            "local service company websites where the owner may not have a "
            "formal title. If no one can be identified, return an empty list."
        ),
    )


class ScrapeResult(BaseModel):
    """Final result returned to the library consumer."""

    url: str = Field(description="The root website URL that was scraped")
    decision_makers: list[DecisionMaker] = Field(default_factory=list)
    pages_crawled: int = Field(default=0)
    pages_skipped: int = Field(default=0)
    errors: list[str] = Field(default_factory=list)
