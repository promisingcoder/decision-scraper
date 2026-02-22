"""CLI entry point for the decision-scraper."""

import argparse
import asyncio
import json
import logging
import os
import sys

from .scraper import scrape_decision_makers, scrape_multiple


def _ensure_utf8() -> None:
    """Ensure stdout/stderr use UTF-8 on Windows to avoid charmap errors."""
    if sys.platform == "win32":
        os.environ.setdefault("PYTHONUTF8", "1")
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    _ensure_utf8()
    parser = argparse.ArgumentParser(
        prog="decision-scraper",
        description="Scrape decision makers (CEOs, owners, founders, etc.) from websites",
    )
    parser.add_argument(
        "urls",
        nargs="+",
        help="One or more website URLs to scrape",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="OpenAI API key (or set OPENAI_API_KEY env var)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=20,
        help="Maximum pages to crawl per site (default: 20)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help="Max concurrent workers (default: auto-detect from system resources)",
    )
    parser.add_argument(
        "--output",
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Resolve API key
    api_key = args.api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        parser.error("--api-key is required or set OPENAI_API_KEY env var")
        sys.exit(1)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    async def run() -> list:
        return await scrape_multiple(
            urls=args.urls,
            api_token=api_key,
            max_pages_per_site=args.max_pages,
        )

    results = asyncio.run(run())

    if args.output == "json":
        output = [r.model_dump() for r in results]
        print(json.dumps(output, indent=2))
    else:
        # Table output
        for result in results:
            print(f"\n{'='*60}")
            print(f"  Site: {result.url}")
            print(f"  Pages crawled: {result.pages_crawled}")
            if result.errors:
                print(f"  Errors: {len(result.errors)}")
            print(f"  Decision makers found: {len(result.decision_makers)}")
            print(f"{'='*60}")
            for dm in result.decision_makers:
                print(f"  Name:     {dm.name}")
                print(f"  Title:    {dm.title or 'N/A'}")
                print(f"  Email:    {dm.email or 'N/A'}")
                print(f"  Phone:    {dm.phone or 'N/A'}")
                print(f"  LinkedIn: {dm.linkedin or 'N/A'}")
                print(f"  {'-'*40}")

        if not any(r.decision_makers for r in results):
            print("\nNo decision makers found across all sites.")


if __name__ == "__main__":
    main()
