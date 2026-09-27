import pytest
from app.services.job_parser import (
    parse_job_page,
    parse_json_ld,
    parse_meta_tags,
    parse_embedded_json,
    parse_common_html,
    validate_location,
)
from app.services.url_parser import extract_company_from_url


# ---------------------------------------------------------------------------
# Static HTML/JSON Fixtures
# ---------------------------------------------------------------------------

JSON_LD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <script type="application/ld+json">
    {
        "@context": "https://schema.org/",
        "@type": "JobPosting",
        "title": "Senior Python Engineer",
        "hiringOrganization": {
            "@type": "Organization",
            "name": "Acme Innovations"
        },
        "jobLocation": {
            "@type": "Place",
            "address": {
                "@type": "PostalAddress",
                "addressLocality": "San Francisco",
                "addressRegion": "CA",
                "addressCountry": "USA"
            }
        },
        "description": "We are hiring a Senior Python Engineer to scale backend services."
    }
    </script>
</head>
<body></body>
</html>
"""

META_OG_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Frontend Developer Position</title>
    <meta property="og:title" content="Lead Frontend Architect" />
    <meta property="og:description" content="Build world-class UI apps using React and TypeScript." />
</head>
<body></body>
</html>
"""

EMBEDDED_JSON_HTML = """
<!DOCTYPE html>
<html>
<head>
    <script>
    {
        "title": "DevOps Lead",
        "company": "Cloud Operations Ltd",
        "location": "Remote - US",
        "description": "Manage Kubernetes clusters and CI/CD pipelines."
    }
    </script>
</head>
<body></body>
</html>
"""

COMMON_HTML_HTML = """
<!DOCTYPE html>
<html>
<body>
    <h1 class="job-title">Backend Systems Developer</h1>
    <div class="company-name" data-company="DataScale Systems">DataScale Systems</div>
    <div class="job-location" data-location="Austin, TX">Austin, TX</div>
    <div class="job-description">Build scalable streaming pipelines in Rust and Python.</div>
</body>
</html>
"""

MISSING_FIELDS_HTML = """
<!DOCTYPE html>
<html>
<body>
    <div>Welcome to our careers portal. Check back soon!</div>
</body>
</html>
"""

MALFORMED_HTML = """
<<<invalid tag>>><<<head><script type="application/ld+json">{broken_json: true}</script>
<h1 class="job-title">Unclosed header tag
<div>Malformed markup /// <>>>
"""


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_parse_json_ld_job_posting():
    """
    2. JSON-LD JobPosting parsing.
    """
    parsed = parse_job_page(JSON_LD_HTML)
    assert parsed["title"] == "Senior Python Engineer"
    assert parsed["company"] == "Acme Innovations"
    assert parsed["location"] == "San Francisco, CA, USA"
    assert "Senior Python Engineer" in parsed["description"]


def test_parse_meta_og_fallback():
    """
    3. Meta/OpenGraph fallback parsing.
    """
    parsed = parse_job_page(META_OG_HTML)
    assert parsed["title"] == "Lead Frontend Architect"
    assert "React and TypeScript" in parsed["description"]
    assert parsed["company"] is None


def test_parse_embedded_json_fallback():
    """
    4. Embedded JSON fallback.
    """
    parsed = parse_job_page(EMBEDDED_JSON_HTML)
    assert parsed["title"] == "DevOps Lead"
    assert parsed["company"] == "Cloud Operations Ltd"
    assert parsed["location"] == "Remote - US"
    assert "Kubernetes" in parsed["description"]


def test_parse_common_html_selectors():
    """
    1. Successful parsing of representative static HTML fixtures.
    """
    parsed = parse_job_page(COMMON_HTML_HTML)
    assert parsed["title"] == "Backend Systems Developer"
    assert parsed["company"] == "DataScale Systems"
    assert parsed["location"] == "Austin, TX"
    assert "streaming pipelines" in parsed["description"]


def test_missing_job_title_and_company_handling():
    """
    5. Missing job title/company handling.
    """
    parsed = parse_job_page(MISSING_FIELDS_HTML)
    assert parsed["title"] is None
    assert parsed["company"] is None
    assert parsed["location"] is None
    assert parsed["description"] is None


def test_malformed_invalid_html():
    """
    8. Malformed/invalid HTML handling.
    """
    # Beautiful Soup handles malformed HTML without throwing exceptions
    parsed = parse_job_page(MALFORMED_HTML)
    assert isinstance(parsed, dict)
    assert "title" in parsed
    assert "company" in parsed
    assert "location" in parsed
    assert "description" in parsed


def test_unsupported_url_domain_inference():
    """
    9. Unsupported URL/page behavior for company extraction.
    """
    # Supported domains
    assert extract_company_from_url("https://www.amazon.jobs/en/jobs/123") == "Amazon"
    assert extract_company_from_url("https://careers.microsoft.com/us/en/job/456") == "Microsoft"

    # Unsupported domains return None
    assert extract_company_from_url("https://unknown-company-jobs.org/role/789") is None
    assert extract_company_from_url("not-a-valid-url") is None


def test_validate_location_cleaning():
    """
    Utility check for location validation logic matching production behavior.
    """
    assert validate_location("San Francisco, CA") == "San Francisco, CA"
    assert validate_location("  ") == ""
    assert validate_location("search jobs by location") is None
    assert validate_location(None) is None
