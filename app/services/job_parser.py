import json

from bs4 import BeautifulSoup


def parse_job_page(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    result = {
        "title": None,
        "company": None,
        "location": None,
        "description": None,
    }

    parsers = [
        parse_json_ld,
        parse_meta_tags,
        parse_embedded_json,
        parse_common_html,
    ]

    for parser in parsers:
        data = parser(soup)

        if not data:
            continue

        for field in result:
            value = data.get(field)

            if value and not result[field]:
                result[field] = value

    # Validate extracted values
    result["location"] = validate_location(result["location"])

    return result

def validate_location(location: str | None) -> str | None:
    if not location:
        return None

    invalid_values = {
        "location",
        "search for jobs by title or keyword search job by location",
        "search jobs by location",
    }

    cleaned = location.strip()

    if cleaned.lower() in invalid_values:
        return None

    return cleaned

def parse_json_ld(soup: BeautifulSoup) -> dict | None:
    scripts = soup.find_all(
        "script",
        type="application/ld+json"
    )

    for script in scripts:
        try:
            data = json.loads(script.string)

            if isinstance(data, dict):
                items = [data]
            elif isinstance(data, list):
                items = data
            else:
                continue

            for item in items:
                if item.get("@type") != "JobPosting":
                    continue

                company = item.get(
                    "hiringOrganization",
                    {}
                )

                return {
                    "title": item.get("title"),
                    "company": company.get("name"),
                    "location": extract_location(item),
                    "description": item.get("description"),
                }

        except (json.JSONDecodeError, AttributeError):
            continue

    return None


def extract_location(data: dict) -> str | None:
    location = data.get("jobLocation")

    if not location:
        return None

    if isinstance(location, list):
        location = location[0]

    if not isinstance(location, dict):
        return None

    address = location.get("address", {})

    if isinstance(address, str):
        return address

    if not isinstance(address, dict):
        return None

    parts = []

    for field in [
        "addressLocality",
        "addressRegion",
        "addressCountry",
    ]:
        value = address.get(field)

        if isinstance(value, str):
            parts.append(value)

        elif isinstance(value, dict):
            # Some sites represent country/region as objects
            name = value.get("name")
            if isinstance(name, str):
                parts.append(name)

    return ", ".join(parts) or None

def parse_meta_tags(soup: BeautifulSoup) -> dict | None:
    title = None
    description = None

    # Normal HTML title
    if soup.title:
        title = soup.title.get_text(strip=True)

    # Meta description
    meta_description = soup.find(
        "meta",
        attrs={"name": "description"}
    )

    if meta_description:
        description = meta_description.get("content")

    # OpenGraph title
    og_title = soup.find(
        "meta",
        attrs={"property": "og:title"}
    )

    if og_title:
        title = og_title.get("content") or title

    # OpenGraph description
    og_description = soup.find(
        "meta",
        attrs={"property": "og:description"}
    )

    if og_description:
        description = og_description.get("content") or description

    if not title and not description:
        return None

    return {
        "title": title,
        "company": None,
        "location": None,
        "description": description,
    }

def parse_common_html(soup: BeautifulSoup) -> dict:
    title = None
    company = None
    location = None
    description = None

    # Title
    for selector in [
        "h1",
        '[class*="job-title"]',
        '[class*="jobTitle"]',
        '[class*="title"]',
    ]:
        element = soup.select_one(selector)

        if element:
            title = element.get_text(" ", strip=True)
            break

    # Company
    for selector in [
        '[class*="company"]',
        '[class*="employer"]',
        '[class*="organization"]',
        '[data-company]',
        '[data-testid*="company"]',
    ]:
        element = soup.select_one(selector)

        if element:
            company = (
                element.get("data-company")
                or element.get_text(" ", strip=True)
            )
            break

    # Location
    for selector in [
        # '[class*="location"]',
        '[class*="job-location"]',
        '[class*="jobLocation"]',
        '[data-location]',
        '[data-testid*="location"]',
    ]:
        element = soup.select_one(selector)

        if element:
            location = (
                element.get("data-location")
                or element.get_text(" ", strip=True)
            )
            break

    # Description
    for selector in [
        '[class*="description"]',
        '[class*="job-description"]',
        '[class*="jobDescription"]',
    ]:
        element = soup.select_one(selector)

        if element:
            description = element.get_text(" ", strip=True)
            break

    return {
        "title": title,
        "company": company,
        "location": location,
        "description": description,
    }

def parse_embedded_json(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script"):
        if not script.string:
            continue

        text = script.string.strip()

        if not text.startswith("{"):
            continue

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue

        # Look for common job fields
        title = data.get("title")
        company = data.get("company")
        location = data.get("location")
        description = data.get("description")

        if title or company or location or description:
            return {
                "title": title,
                "company": company,
                "location": location,
                "description": description,
            }

    return None