import pytest
from fastapi.testclient import TestClient


def test_url_preview_api_success(client: TestClient, auth_headers: dict[str, str], monkeypatch):
    """
    11. URL preview API behavior when scraping succeeds.
    """
    mocked_scraped_job = {
        "company": "Stripe",
        "title": "Backend Infrastructure Engineer",
        "location": "San Francisco, CA",
        "description": "Build high availability payment infrastructure.",
    }
    monkeypatch.setattr(
        "app.routers.application.scrape_job",
        lambda url: mocked_scraped_job,
    )

    request_payload = {"job_url": "https://stripe.com/jobs/infrastructure-engineer"}
    response = client.post(
        "/applications/url/preview",
        json=request_payload,
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["job_url"] == request_payload["job_url"]
    assert data["company_name"] == "Stripe"
    assert data["title"] == "Backend Infrastructure Engineer"
    assert data["location"] == "San Francisco, CA"
    assert "payment infrastructure" in data["description"]


def test_url_preview_api_failure(client: TestClient, auth_headers: dict[str, str], monkeypatch):
    """
    12. URL preview API behavior when scraping fails.
    """
    def mock_failing_scrape(url: str):
        raise RuntimeError("External site connection refused")

    monkeypatch.setattr(
        "app.routers.application.scrape_job",
        mock_failing_scrape,
    )

    request_payload = {"job_url": "https://unreachable-job-site.com/role/123"}
    response = client.post(
        "/applications/url/preview",
        json=request_payload,
        headers=auth_headers,
    )

    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "Could not scrape job page: External site connection refused" in data["detail"]
