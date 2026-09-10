from app.services.job_scraper import fetch_job_page
from app.services.browser_scraper import fetch_dynamic_page
from app.services.job_parser import parse_job_page
from app.services.url_parser import extract_company_from_url


def scrape_job(url: str) -> dict:
    # 1. Try normal HTTP scraping
    html = fetch_job_page(url)
    job = parse_job_page(html)

    # 2. If important data is missing, try Playwright
    if not job.get("title") or not job.get("company"):
        dynamic_html = fetch_dynamic_page(url)
        dynamic_job = parse_job_page(dynamic_html)

        # Keep good data from the first parser,
        # only fill missing fields from Playwright
        for field in job:
            if not job[field] and dynamic_job.get(field):
                job[field] = dynamic_job[field]

    # 3. If company is still missing, try URL/domain inference
    if not job.get("company"):
        job["company"] = extract_company_from_url(url)

    return job