import pytest
import httpx
from app.services.job_scraper import fetch_job_page
from app.services.job_scraper_service import scrape_job


def test_fetch_job_page_http_404(monkeypatch):
    """
    6. HTTP 404 from an external job page.
    Asserts no real HTTP connection occurs and HTTPStatusError is raised.
    """
    def mock_get(*args, **kwargs):
        url = args[0] if args else kwargs.get("url", "https://example.com")
        request = httpx.Request("GET", url)
        return httpx.Response(404, request=request)

    monkeypatch.setattr("app.services.job_scraper.httpx.get", mock_get)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        fetch_job_page("https://example.com/jobs/nonexistent-404")

    assert exc_info.value.response.status_code == 404


def test_fetch_job_page_timeout(monkeypatch):
    """
    7. HTTP timeout.
    Asserts no real HTTP connection occurs and TimeoutException is raised.
    """
    def mock_get(*args, **kwargs):
        raise httpx.TimeoutException("Connection timed out after 10 seconds")

    monkeypatch.setattr("app.services.job_scraper.httpx.get", mock_get)

    with pytest.raises(httpx.TimeoutException):
        fetch_job_page("https://example.com/jobs/timeout")


def test_scrape_job_playwright_fallback_without_real_browser(monkeypatch):
    """
    10. Playwright fallback behavior without launching a real browser.
    Mocks both HTTP fetch and Playwright browser fetch to verify fallback execution.
    """
    # Static HTTP fetch returns incomplete page missing title and company
    incomplete_static_html = "<html><body><div>Loading JavaScript app...</div></body></html>"
    monkeypatch.setattr("app.services.job_scraper_service.fetch_job_page", lambda url: incomplete_static_html)

    dynamic_rendered_html = """
    <html>
    <body>
        <h1 class="job-title">Staff Software Architect</h1>
        <div class="company" data-company="Dynamic Enterprise Inc">Dynamic Enterprise Inc</div>
        <div class="job-location">New York, NY</div>
    </body>
    </html>
    """
    playwright_call_log = []

    def mock_fetch_dynamic_page(url: str) -> str:
        playwright_call_log.append(url)
        return dynamic_rendered_html

    monkeypatch.setattr("app.services.job_scraper_service.fetch_dynamic_page", mock_fetch_dynamic_page)

    target_url = "https://example.com/jobs/dynamic-single-page-app"
    result = scrape_job(target_url)

    # Verify Playwright fallback was triggered exactly once without opening a browser
    assert len(playwright_call_log) == 1
    assert playwright_call_log[0] == target_url

    # Verify merged data
    assert result["title"] == "Staff Software Architect"
    assert result["company"] == "Dynamic Enterprise Inc"
    assert result["location"] == "New York, NY"


def test_scrape_job_url_domain_fallback(monkeypatch):
    """
    Verify domain inference fallback when parsing returns no company name.
    """
    # Static fetch returns title but no company name
    static_html = "<html><body><h1>Software Engineer</h1></body></html>"
    monkeypatch.setattr("app.services.job_scraper_service.fetch_job_page", lambda url: static_html)

    # Playwright also returns no company name
    monkeypatch.setattr("app.services.job_scraper_service.fetch_dynamic_page", lambda url: static_html)

    result = scrape_job("https://www.amazon.jobs/en/jobs/99999/sde")
    assert result["title"] == "Software Engineer"
    assert result["company"] == "Amazon"
