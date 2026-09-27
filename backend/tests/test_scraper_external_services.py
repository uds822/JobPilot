import httpx
import pytest

from app.services import browser_scraper, job_parser, job_scraper, job_scraper_service


JSON_LD_HTML = """
<html><head>
  <script type="application/ld+json">
  {
    "@type": "JobPosting",
    "title": "Senior Python Engineer",
    "hiringOrganization": {"name": "Example Labs"},
    "jobLocation": {"address": {
      "addressLocality": "New York",
      "addressRegion": "NY",
      "addressCountry": "US"
    }},
    "description": "Build reliable backend systems."
  }
  </script>
</head></html>
"""

META_HTML = """
<html>
  <head>
    <title>Fallback Job Page</title>
    <meta property="og:title" content="Platform Engineer at Meta Example">
    <meta property="og:description" content="Build platform tooling.">
  </head>
</html>
"""

EMBEDDED_JSON_HTML = """
<html><body>
  <script>
  {"title": "Frontend Engineer", "company": "Embedded Co",
   "location": "Remote", "description": "Ship user experiences."}
  </script>
</body></html>
"""


def test_parse_json_ld_job_posting():
    result = job_parser.parse_job_page(JSON_LD_HTML)

    assert result == {
        "title": "Senior Python Engineer",
        "company": "Example Labs",
        "location": "New York, NY, US",
        "description": "Build reliable backend systems.",
    }


def test_parse_meta_and_opengraph_fallback():
    result = job_parser.parse_job_page(META_HTML)

    assert result["title"] == "Platform Engineer at Meta Example"
    assert result["description"] == "Build platform tooling."
    assert result["company"] is None
    assert result["location"] is None


def test_parse_embedded_json_fallback():
    result = job_parser.parse_job_page(EMBEDDED_JSON_HTML)

    assert result == {
        "title": "Frontend Engineer",
        "company": "Embedded Co",
        "location": "Remote",
        "description": "Ship user experiences.",
    }


@pytest.mark.parametrize(
    "html",
    [
        "<html><body><h1>Only a title</h1></body></html>",
        "<html><body><div class='company'>Only a company</div></body></html>",
        "<html><body><p>No job fields here</p></body></html>",
    ],
)
def test_parse_missing_title_or_company_is_explicit(html: str):
    result = job_parser.parse_job_page(html)

    assert set(result) == {"title", "company", "location", "description"}
    assert result["title"] is None or result["company"] is None


def test_parse_malformed_html_returns_safe_partial_result():
    result = job_parser.parse_job_page(
        "<html><head><title>Broken <b>Job</head><body><h1>Engineer"
    )

    assert result["title"] == "BrokenJob"
    assert result["company"] is None


def test_fetch_job_page_returns_static_response_without_network(monkeypatch):
    response = httpx.Response(200, text=JSON_LD_HTML, request=httpx.Request("GET", "https://jobs.example/test"))
    calls: list[tuple[str, dict, int, bool]] = []

    def fake_get(url, headers, timeout, follow_redirects):
        calls.append((url, headers, timeout, follow_redirects))
        return response

    monkeypatch.setattr(job_scraper.httpx, "get", fake_get)

    assert job_scraper.fetch_job_page("https://jobs.example/test") == JSON_LD_HTML
    assert calls[0][0] == "https://jobs.example/test"
    assert calls[0][2:] == (10, True)


def test_fetch_job_page_propagates_http_404(monkeypatch):
    response = httpx.Response(404, text="Not found", request=httpx.Request("GET", "https://jobs.example/missing"))
    monkeypatch.setattr(job_scraper.httpx, "get", lambda *args, **kwargs: response)

    with pytest.raises(httpx.HTTPStatusError) as error:
        job_scraper.fetch_job_page("https://jobs.example/missing")

    assert error.value.response.status_code == 404


def test_fetch_job_page_propagates_timeout(monkeypatch):
    def raise_timeout(*args, **kwargs):
        raise httpx.ReadTimeout("upstream timed out")

    monkeypatch.setattr(job_scraper.httpx, "get", raise_timeout)

    with pytest.raises(httpx.ReadTimeout, match="upstream timed out"):
        job_scraper.fetch_job_page("https://jobs.example/slow")


def test_scrape_job_uses_mocked_playwright_fallback(monkeypatch):
    monkeypatch.setattr(
        job_scraper_service,
        "fetch_job_page",
        lambda url: "<html><body><h1>Dynamic Engineer</h1></body></html>",
    )
    monkeypatch.setattr(
        job_scraper_service,
        "parse_job_page",
        lambda html: {"title": None, "company": None, "location": None, "description": None},
    )

    dynamic_calls: list[str] = []

    def fake_dynamic_page(url: str) -> str:
        dynamic_calls.append(url)
        return "dynamic html"

    def parse_dynamic(html: str) -> dict:
        if html == "dynamic html":
            return {
                "title": "Dynamic Engineer",
                "company": "Dynamic Co",
                "location": "Remote",
                "description": "Rendered job",
            }
        return {"title": None, "company": None, "location": None, "description": None}

    monkeypatch.setattr(job_scraper_service, "fetch_dynamic_page", fake_dynamic_page)
    monkeypatch.setattr(job_scraper_service, "parse_job_page", parse_dynamic)

    result = job_scraper_service.scrape_job("https://jobs.example/dynamic")

    assert result["title"] == "Dynamic Engineer"
    assert result["company"] == "Dynamic Co"
    assert dynamic_calls == ["https://jobs.example/dynamic"]


def test_fetch_dynamic_page_uses_mocked_playwright_without_launching_browser(monkeypatch):
    events: list[str] = []

    class FakePage:
        def goto(self, url, wait_until, timeout):
            events.extend(["goto", url, wait_until, str(timeout)])

        def content(self):
            events.append("content")
            return JSON_LD_HTML

    class FakeBrowser:
        def new_page(self):
            events.append("new_page")
            return FakePage()

        def close(self):
            events.append("close")

    class FakeChromium:
        def launch(self, headless):
            events.extend(["launch", str(headless)])
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

        def __enter__(self):
            events.append("enter")
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            events.append("exit")

    monkeypatch.setattr(browser_scraper, "sync_playwright", lambda: FakePlaywright())

    assert browser_scraper.fetch_dynamic_page("https://jobs.example/dynamic") == JSON_LD_HTML
    assert events == [
        "enter", "launch", "True", "new_page", "goto",
        "https://jobs.example/dynamic", "domcontentloaded", "30000",
        "content", "close", "exit",
    ]


def test_scrape_job_uses_known_url_company_fallback(monkeypatch):
    empty_job = {"title": None, "company": None, "location": None, "description": None}
    monkeypatch.setattr(job_scraper_service, "fetch_job_page", lambda url: "empty")
    monkeypatch.setattr(job_scraper_service, "parse_job_page", lambda html: empty_job.copy())
    monkeypatch.setattr(job_scraper_service, "fetch_dynamic_page", lambda url: "empty")

    result = job_scraper_service.scrape_job("https://www.google.com/jobs/123")

    assert result["company"] == "Google"
    assert result["title"] is None


def test_scrape_job_leaves_company_missing_for_unsupported_url(monkeypatch):
    empty_job = {"title": None, "company": None, "location": None, "description": None}
    monkeypatch.setattr(job_scraper_service, "fetch_job_page", lambda url: "empty")
    monkeypatch.setattr(job_scraper_service, "parse_job_page", lambda html: empty_job.copy())
    monkeypatch.setattr(job_scraper_service, "fetch_dynamic_page", lambda url: "empty")

    result = job_scraper_service.scrape_job("https://unsupported.example/jobs/123")

    assert result["company"] is None
    assert result["title"] is None


def test_preview_api_returns_scraped_job_data(auth_client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.application.scrape_job",
        lambda url: {
            "company": "Preview Co",
            "title": "Preview Engineer",
            "location": "Remote",
            "description": "Preview description",
        },
    )

    response = auth_client.post(
        "/applications/url/preview",
        json={"job_url": "https://jobs.example/preview"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "job_url": "https://jobs.example/preview",
        "company_name": "Preview Co",
        "title": "Preview Engineer",
        "location": "Remote",
        "description": "Preview description",
        "notes": None,
        "status": "APPLIED",
    }


def test_preview_api_returns_bad_request_when_scraping_fails(auth_client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.application.scrape_job",
        lambda url: (_ for _ in ()).throw(httpx.ReadTimeout("upstream timed out")),
    )

    response = auth_client.post(
        "/applications/url/preview",
        json={"job_url": "https://jobs.example/timeout"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Could not scrape job page: upstream timed out"}
