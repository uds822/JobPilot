"""Public careers adapters. Unknown shapes fail closed, never imply empty feeds."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from app.ai_job_search.providers.ats_filters import html_to_text
from app.ai_job_search.schemas import NormalizedJobSchema
from app.company_watch.detection import canonical_url, inspect_page, structured_jobs


MAX_PAGES = 20


def normalized_job(source, identity, title, location, url, description=None, posted=None):
    if not title or not identity or not location:
        raise ValueError("Posting lacks identity, title or location")
    canonical_url(url)
    # Host/tenant-scoped hashes fit the canonical external_id column and are stable.
    external = hashlib.sha256(f"{source.identifier.lower()}:{identity}".encode()).hexdigest()
    date = None
    if isinstance(posted, str):
        try:
            date = datetime.fromisoformat(posted.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass
    return NormalizedJobSchema(
        job_hash=hashlib.sha256(f"{source.provider}:{external}".encode()).hexdigest(),
        source=source.provider, external_id=external, title=title.strip(), company=source.company,
        location=location, remote="remote" in location.lower(), description=html_to_text(description),
        apply_url=url, source_url=url, posted_date=date, salary_currency=None,
    )


def fetch_result(jobs, count, complete, pages, error=None):
    from app.company_watch.providers import FetchResult
    return FetchResult(tuple(jobs.values()), count, complete, pages_fetched=pages, error=error)


class GoogleAdapter:
    async def fetch(self, source, request):
        url = "https://www.google.com/about/careers/applications/jobs/results/?location=India"
        jobs, seen, count, total, pages = {}, set(), 0, None, 0
        try:
            for _ in range(MAX_PAGES):
                if url in seen:
                    raise ValueError("Repeated Google pagination URL")
                seen.add(url)
                response = await request(url)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                counter = soup.select_one(".rZt9ff .SWhIm")
                if not counter or not re.fullmatch(r"[\d,]+", counter.get_text(strip=True)):
                    raise ValueError("Google inventory count is missing; page layout may have changed")
                current_total = int(counter.get_text(strip=True).replace(",", ""))
                if total is None:
                    total = current_total
                elif total != current_total:
                    raise ValueError("Google inventory changed during pagination")
                cards = []
                for anchor in soup.select('a[href*="jobs/results/"]'):
                    match = re.search(r"jobs/results/(\d+)-", anchor.get("href", ""))
                    card = anchor.find_parent("li")
                    if match and card and card.find("h3"):
                        cards.append((match.group(1), anchor, card))
                if not cards and total:
                    raise ValueError("Google result cards are missing")
                pages += 1
                for identity, anchor, card in cards:
                    key = f"card:{identity}"
                    if key in seen:
                        raise ValueError("Duplicate Google posting across pages")
                    seen.add(key)
                    count += 1
                    organization = card.select_one(".RP7SMd")
                    # Google Careers also publishes subsidiary jobs: don't relabel them.
                    if not organization or organization.get_text(" ", strip=True).removeprefix("corporate_fare").strip() != "Google":
                        continue
                    locations = list(dict.fromkeys(span.get_text(" ", strip=True) for span in card.select(".r0wTof")))
                    posting_url = urljoin("https://www.google.com/about/careers/applications/", anchor["href"])
                    description = card.select_one(".Xsxa1e")
                    jobs[identity] = normalized_job(source, identity, card.h3.get_text(" ", strip=True), "; ".join(locations), posting_url, description.get_text(" ", strip=True) if description else None)
                next_link = soup.find("a", attrs={"aria-label": "Go to next page"})
                if not next_link:
                    if count != total:
                        raise ValueError("Google posting count does not match complete inventory")
                    return fetch_result(jobs, count, True, pages)
                url = urljoin(str(response.url), next_link["href"])
                parsed = urlsplit(url)
                if parsed.hostname != "www.google.com" or parsed.path != "/about/careers/applications/jobs/results/" or "location=India" not in parsed.query:
                    raise ValueError("Google pagination changed inventory scope")
            raise ValueError("Google page budget exhausted")
        except Exception as exc:
            if not pages:
                raise
            return fetch_result(jobs, count, False, pages, str(exc)[:1000])


class SmartRecruitersAdapter:
    async def fetch(self, source, request):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", source.identifier):
            raise ValueError("Invalid SmartRecruiters tenant")
        base = f"https://api.smartrecruiters.com/v1/companies/{source.identifier}/postings"
        jobs, seen, offset, total, pages, details = {}, set(), 0, None, 0, 0
        try:
            for _ in range(MAX_PAGES):
                response = await request(f"{base}?limit=100&offset={offset}&country=in&destination=PUBLIC")
                response.raise_for_status()
                payload = response.json()
                items, current_total = payload.get("content"), payload.get("totalFound")
                if not isinstance(items, list) or type(current_total) is not int or current_total < 0:
                    raise ValueError("Malformed SmartRecruiters inventory")
                if total is None:
                    total = current_total
                if current_total != total:
                    raise ValueError("SmartRecruiters inventory changed during pagination")
                pages += 1
                for item in items:
                    identity = item.get("id")
                    if not identity or identity in seen:
                        raise ValueError("Missing or duplicate SmartRecruiters posting")
                    seen.add(identity)
                    owner = item.get("company", {}).get("identifier")
                    if owner and owner.lower() != source.identifier.lower():
                        raise ValueError("SmartRecruiters posting belongs to another tenant")
                    address = item.get("location") or {}
                    country = address.get("country", "")
                    location = ", ".join(str(value) for value in (address.get("city"), address.get("region"), "India" if country.lower() in {"in", "ind", "india"} else country) if value)
                    description = item.get("jobAd", {}).get("sections", {})
                    description = " ".join(section.get("text", "") for section in description.values() if isinstance(section, dict))
                    url = item.get("applyUrl") or f"https://jobs.smartrecruiters.com/{source.identifier}/{identity}"
                    if item.get("ref") and details < 8:
                        details += 1
                        try:
                            detail = await request(f"{base}/{identity}")
                            detail.raise_for_status()
                            detail_payload = detail.json()
                            sections = detail_payload.get("jobAd", {}).get("sections", {})
                            description = " ".join(section.get("text", "") for section in sections.values() if isinstance(section, dict)) or description
                            url = detail_payload.get("applyUrl") or url
                        except Exception:
                            pass
                    jobs[identity] = normalized_job(source, identity, item.get("name"), location, url, description, item.get("releasedDate"))
                offset += len(items)
                if offset == total:
                    return fetch_result(jobs, offset, True, pages)
                if not items or offset > total:
                    raise ValueError("SmartRecruiters pagination is incomplete")
            raise ValueError("SmartRecruiters page budget exhausted")
        except Exception as exc:
            if not pages:
                raise
            return fetch_result(jobs, len(seen), False, pages, str(exc)[:1000])


def india_facet(facets):
    for facet in facets:
        if not isinstance(facet, dict):
            continue
        values = facet.get("values", [])
        for value in values:
            parameter = facet.get("facetParameter", "")
            country_parameter = "country" in parameter.lower() or parameter == "locationHierarchy1"
            if isinstance(value, dict) and value.get("descriptor", "").strip().lower() == "india" and value.get("id") and country_parameter:
                return {facet["facetParameter"]: [value["id"]]}
        nested = india_facet(values)
        if nested:
            return nested
    return {}


class WorkdayAdapter:
    async def fetch(self, source, request):
        from app.company_watch.detection import detect_url
        candidate = detect_url(source.source_url)
        if not candidate or candidate.provider != "workday" or candidate.identifier.lower() != source.identifier.lower():
            raise ValueError("Workday source URL and tenant identity disagree")
        host, tenant, site = candidate.identifier.split(":")
        base = f"https://{host}/wday/cxs/{tenant}/{site}"
        jobs, seen, offset, total, pages, facets, details = {}, set(), 0, None, 0, {}, 0
        try:
            initial = await request(f"{base}/jobs", method="POST", json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""})
            initial.raise_for_status()
            facets = india_facet(initial.json().get("facets", []))
            for page in range(MAX_PAGES):
                response = initial if page == 0 and not facets else await request(f"{base}/jobs", method="POST", json={"appliedFacets": facets, "limit": 20, "offset": offset, "searchText": ""})
                response.raise_for_status()
                payload = response.json()
                items, current_total = payload.get("jobPostings"), payload.get("total")
                if not isinstance(items, list) or type(current_total) is not int or current_total < 0:
                    raise ValueError("Malformed Workday inventory")
                if total is None:
                    total = current_total
                # Some Workday tenants return total=0 after the first page.
                # The first-page total and unique observed count still bound completion.
                if current_total not in {total, 0}:
                    raise ValueError("Workday inventory changed during pagination")
                pages += 1
                for item in items:
                    path = item.get("externalPath", "")
                    fields = item.get("bulletFields") or []
                    identity = str(fields[0]) if fields else path
                    if not path.startswith("/job/") or not identity or identity in seen:
                        raise ValueError("Missing or duplicate Workday posting path")
                    seen.add(identity)
                    location = item.get("locationsText", "")
                    # An India country facet proves country eligibility, not a city.
                    if re.fullmatch(r"\d+ Locations?", location):
                        if not facets:
                            raise ValueError("Workday multi-location posting requires country facets or a detail adapter")
                        location = "India"
                    if location.startswith("IN,"):
                        location = location.replace("IN,", "India,", 1)
                    description = None
                    if facets and details < 8:
                        details += 1
                        try:
                            detail = await request(f"{base}{path}")
                            detail.raise_for_status()
                            info = detail.json().get("jobPostingInfo", {})
                            description = info.get("jobDescription")
                            detail_locations = [info.get("location"), *(info.get("additionalLocations") or [])]
                            detail_locations = [value for value in detail_locations if isinstance(value, str) and value]
                            if detail_locations:
                                location = "; ".join(detail_locations)
                        except Exception:
                            pass
                    jobs[identity] = normalized_job(source, identity, item.get("title"), location, f"https://{host}/{site}{path}", description)
                offset += len(items)
                if offset == total:
                    return fetch_result(jobs, offset, True, pages)
                if not items or offset > total:
                    raise ValueError("Workday pagination is incomplete")
            raise ValueError("Workday page budget exhausted")
        except Exception as exc:
            if not pages:
                raise
            return fetch_result(jobs, len(seen), False, pages, str(exc)[:1000])


class StructuredAdapter:
    def __init__(self, provider):
        self.provider = provider

    async def fetch(self, source, request):
        jobs, seen, pages = {}, set(), 0
        queue = [source.source_url]
        root_host = urlsplit(source.source_url).hostname
        try:
            while queue and pages < 6:
                url = queue.pop(0)
                if url in seen:
                    continue
                seen.add(url)
                response = await request(url)
                response.raise_for_status()
                pages += 1
                if self.provider == "custom_api":
                    items = structured_jobs(response.json())
                    links = []
                else:
                    _, links, items = inspect_page(response.text, str(response.url))
                for item in items:
                    organization = item.get("hiringOrganization") or {}
                    owner = re.sub(r"[^a-z0-9]", "", organization.get("name", "").lower())
                    expected = re.sub(r"[^a-z0-9]", "", source.company.lower())
                    if owner != expected:
                        raise ValueError("Structured posting employer does not match source owner")
                    expiry = item.get("validThrough")
                    if isinstance(expiry, str):
                        try:
                            if datetime.fromisoformat(expiry.replace("Z", "+00:00")).replace(tzinfo=None) < datetime.utcnow():
                                continue
                        except ValueError:
                            pass
                    locations = item.get("jobLocation", [])
                    if isinstance(locations, dict):
                        locations = [locations]
                    labels = []
                    for place in locations:
                        address = place.get("address", {})
                        country = address.get("addressCountry", "")
                        if isinstance(country, dict):
                            country = country.get("name", "")
                        labels.append(", ".join(str(value) for value in (address.get("addressLocality"), address.get("addressRegion"), "India" if str(country).lower() in {"in", "ind", "india"} else country) if value))
                    if item.get("jobLocationType") == "TELECOMMUTE":
                        requirements = item.get("applicantLocationRequirements", [])
                        if isinstance(requirements, dict):
                            requirements = [requirements]
                        labels.extend("Remote " + country.get("name", "") for country in requirements)
                    posting_url = urljoin(url, item.get("url") or url)
                    identity = item.get("identifier")
                    if isinstance(identity, dict):
                        identity = identity.get("value")
                    identity = str(identity or canonical_url(posting_url))
                    jobs[identity] = normalized_job(source, identity, item.get("title"), "; ".join(labels), posting_url, item.get("description"), item.get("datePosted"))
                queue.extend(link for link in links if urlsplit(link).hostname == root_host and link not in seen)
            if not jobs:
                raise ValueError("No validated JobPosting data; a site-specific adapter is required")
            # A bounded collection of detail pages never proves a complete inventory.
            return fetch_result(jobs, len(jobs), False, pages)
        except Exception as exc:
            if not jobs:
                raise
            return fetch_result(jobs, len(jobs), False, pages, str(exc)[:1000])
