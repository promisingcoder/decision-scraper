"""LLM extraction strategy builder with anti-hallucination prompt."""

from crawl4ai import LLMConfig
from crawl4ai.extraction_strategy import LLMExtractionStrategy

from .models import DecisionMakersResponse

EXTRACTION_INSTRUCTION = """\
You are a precise data extraction assistant. Your task is to extract decision-maker \
information from the provided web page content.

RULES — YOU MUST FOLLOW ALL OF THESE:
1. ONLY extract people who are explicitly named on the page.
2. ONLY include people with a senior/executive title that is explicitly stated on the page. \
   Qualifying titles include:
   - Corporate: Owner, CEO, Founder, Co-Founder, President, Vice President (VP), \
     Director, Managing Director, Partner, Principal, General Manager.
   - C-suite: CTO, CFO, COO, CMO, CIO, CPO, or any other "Chief" title.
   - Professional practice owners: Doctor (MD, DO), Dentist (DDS, DMD), \
     Attorney, Architect, or any licensed professional who is the named \
     principal/owner of the practice or firm shown on the website.
3. Do NOT include regular employees, managers, supervisors, coordinators, analysts, \
   engineers, designers, hygienists, assistants, receptionists, or any non-executive staff.
4. For each field (email, phone, linkedin): return the value ONLY if it appears on the page \
   in direct association with that person. If you cannot find it, return null. \
   NEVER guess, infer, or generate contact information.
5. If a general phone number or email is shown on the page (not tied to a specific person), \
   you MAY associate it with the primary decision maker if the page clearly belongs to \
   their practice or business.
6. If the page contains no qualifying decision makers, return {"decision_makers": []}.
7. Do NOT fabricate names, titles, emails, phone numbers, or LinkedIn URLs under any \
   circumstances.
8. Preserve the exact spelling of names and titles as they appear on the page.

Return valid JSON matching the provided schema.\
"""


def build_extraction_strategy(api_token: str) -> LLMExtractionStrategy:
    """Build the LLM extraction strategy for decision-maker extraction."""
    return LLMExtractionStrategy(
        llm_config=LLMConfig(
            provider="openai/gpt-4o-mini",
            api_token=api_token,
            temperature=0.0,
        ),
        schema=DecisionMakersResponse.model_json_schema(),
        extraction_type="schema",
        instruction=EXTRACTION_INSTRUCTION,
        chunk_token_threshold=2048,
        overlap_rate=0.1,
        apply_chunking=True,
        input_format="fit_markdown",
    )
