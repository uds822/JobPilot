from urllib.parse import urlparse


def extract_company_from_url(url: str) -> str | None:
    hostname = urlparse(url).hostname

    if not hostname:
        return None

    hostname = hostname.lower()

    company_domains = {
        "amazon.jobs": "Amazon",
        "www.amazon.jobs": "Amazon",
        "careers.microsoft.com": "Microsoft",
        "www.google.com": "Google",
    }

    return company_domains.get(hostname)