from app.services.job_scraper import fetch_job_page
from app.services.browser_scraper import fetch_dynamic_page
from app.services.job_parser import parse_job_page
from app.services.url_parser import extract_company_from_url

# ─────────────────────────────────────────────────────────────────────────────
# SCRAPING STRATEGY (3-tier fallback):
#
# Tier 1: Async HTTP (httpx.AsyncClient)
#   Fast (~1–3s), non-blocking, works for most static job pages.
#
# Tier 2: Async Playwright (headless Chromium)
#   Slower (~5–30s), but handles JavaScript-rendered pages.
#   Only used if Tier 1 fails to find title or company.
#
# Tier 3: URL inference (extract_company_from_url)
#   Zero network calls. Parses the domain from the URL itself.
#   e.g. "jobs.google.com" → "google"
#   Only used if both Tier 1 and Tier 2 fail to find the company.
# ─────────────────────────────────────────────────────────────────────────────


async def scrape_job(url: str) -> dict:
    """
    Orchestrate the 3-tier job scraping strategy and return extracted job data.

    Returns a dict with keys: company, title, location, description.
    Values may be None if extraction fails at all tiers.

    All operations are async so the event loop is never blocked.
    """
    # ── Tier 1: Fast async HTTP scrape ────────────────────────────────────
    # await: yields control to event loop while waiting for HTTP response
    html = await fetch_job_page(url)

    # parse_job_page is pure CPU (BeautifulSoup parsing) — no await needed
    job = parse_job_page(html)

    # ── Tier 2: Async Playwright fallback ─────────────────────────────────
    # Only trigger Playwright if critical fields are missing.
    # Playwright is expensive (~5–30s) so we avoid it when possible.
    if not job.get("title") or not job.get("company"):
        # await: yields control while Playwright launches browser + loads page
        dynamic_html = await fetch_dynamic_page(url)

        # Again, parsing is pure CPU — no await
        dynamic_job = parse_job_page(dynamic_html)

        # Merge strategy: keep good data from Tier 1,
        # only fill MISSING fields from Playwright result
        for field in job:
            if not job[field] and dynamic_job.get(field):
                job[field] = dynamic_job[field]

    # ── Tier 3: URL inference ─────────────────────────────────────────────
    # extract_company_from_url is pure Python string parsing — no await needed
    if not job.get("company"):
        job["company"] = extract_company_from_url(url)

    return job