"""LLM extraction strategy builder with anti-hallucination prompt."""

from crawl4ai import LLMConfig
from crawl4ai.extraction_strategy import LLMExtractionStrategy

from .models import DecisionMakersResponse

EXTRACTION_INSTRUCTION = """\
You are a precise data extraction assistant. Your task is to find the \
business owner or decision maker from the provided web page content.

WHO TO EXTRACT — identify the person who OWNS or RUNS this business:
1. People with explicit titles: Owner, CEO, Founder, President, Director, \
   Partner, Principal, Managing Member, General Manager, or any C-suite role.
2. Licensed professionals who own the business: Master Plumber, Licensed \
   Plumber, Licensed Electrician, Licensed Contractor, General Contractor, \
   Dentist (DDS/DMD), Doctor (MD/DO), Attorney, CPA, Architect, etc. \
   If a license holder's name appears on a service business website, they \
   are very likely the owner.
3. People whose name IS the business name or is part of it \
   (e.g. "Smith Plumbing" → John Smith is the owner).
4. People identified through context clues on the page such as:
   - "Family-owned by [Name]" or "[Name] started this company in..."
   - A personal name in the copyright line: "© 2024 John Smith Plumbing"
   - "Call [Name]" or "[Name] and his team..."
   - "About [Name]" sections, personal bios, or owner introductions
   - License numbers tied to a person: "License #12345 - John Smith"
   - A person featured prominently on the homepage with a photo
5. If the website is clearly a small/local business (plumber, electrician, \
   HVAC, roofer, landscaper, cleaning service, etc.) and ONE person's name \
   appears prominently, they are almost certainly the owner — extract them \
   with title "Owner" even if that exact word doesn't appear.

WHO NOT TO EXTRACT:
- Technicians, assistants, dispatchers, office staff, receptionists
- Names that only appear in customer testimonials/reviews
- Names that only appear in blog post author bylines
- Generic team mentions without specific names

CONTACT INFORMATION RULES:
- For email/phone: extract if it appears ANYWHERE on the page. On a small \
  business site, the main phone/email IS the owner's contact info.
- For LinkedIn: only if an actual LinkedIn URL appears on the page.
- NEVER fabricate or guess contact information. Return null if not found.

CRITICAL ANTI-HALLUCINATION RULES:
- The person's name MUST actually appear as text on the page.
- Do NOT invent names, titles, or contact info under any circumstances.
- If no owner/decision maker can be identified, return {"decision_makers": []}.
- Preserve exact spelling of names as they appear on the page.

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
