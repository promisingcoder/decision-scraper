# decision-scraper

Generic decision-maker scraper — finds owners, CEOs, founders and their contact information from any website.

## Installation

```bash
pip install decision-scraper
```

## Usage

### As a library

```python
import asyncio
from decision_scraper import scrape_decision_makers

async def main():
    result = await scrape_decision_makers(
        url="https://example.com",
        api_token="sk-...",
    )
    for dm in result.decision_makers:
        print(f"{dm.name} - {dm.title}")
        print(f"  Email: {dm.email}")
        print(f"  Phone: {dm.phone}")

asyncio.run(main())
```

### As a CLI

```bash
decision-scraper https://example.com --api-key sk-... --output table
```
