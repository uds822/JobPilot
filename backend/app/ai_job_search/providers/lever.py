from __future__ import annotations

import asyncio
import logging
from typing import Any, Iterable

import httpx

from app.ai_job_search.providers.ats_filters import (
    ats_location_matches,
    html_to_text,
    parse_provider_datetime,
    title_matches_queries,
)
from app.ai_job_search.providers.ats_registry import LEVER_SITES
from app.ai_job_search.providers.base import JobProvider
from app.ai_job_search.schemas import NormalizedJobSchema

logger = logging.getLogger(__name__)

# Retained for compatibility with existing imports.
CURATED_LEVER_COMPANIES = [entry["site"] for entry in LEVER_SITES]


class LeverProvider(JobProvider):
    """Lever public postings provider with bounded site concurrency."""

    def __init__(self) -> None:
        super().__init__(name="lever")

    async def search(
        self,
        query: str,
        location: str = "India",
        min_salary: float | None = None,
        company: str | None = None,
        max_results: int = 20,
    ) -> list[NormalizedJobSchema]:
        if not company:
            return []
        jobs = await self.fetch(
            queries=[query],
            target_locations=[location],
            sites=[{"company": company, "site": company}],
            concurrency=1,
        )
        return jobs[:max_results]

    async def fetch(
        self,
        queries: list[str],
        target_locations: list[str],
        concurrency: int = 8,
        sites: Iterable[dict[str, str]] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> list[NormalizedJobSchema]:
        configured_sites = list(LEVER_SITES if sites is None else sites)
        semaphore = asyncio.Semaphore(concurrency)

        async def run(active_client: httpx.AsyncClient):
            tasks = [
                self._fetch_site(
                    active_client,
                    semaphore,
                    entry,
                    queries,
                    target_locations,
                )
                for entry in configured_sites
            ]
            return await asyncio.gather(*tasks, return_exceptions=True)

        if client is None:
            async with httpx.AsyncClient(timeout=10.0) as active_client:
                results = await run(active_client)
        else:
            results = await run(client)

        jobs: list[NormalizedJobSchema] = []
        successful = failed = raw_count = title_count = location_count = 0
        for result in results:
            if isinstance(result, Exception):
                failed += 1
                logger.warning("Lever site task failed: %s", result)
                continue
            success, raw, title_matched, location_matched, site_jobs = result
            successful += int(success)
            failed += int(not success)
            raw_count += raw
            title_count += title_matched
            location_count += location_matched
            jobs.extend(site_jobs)

        logger.info(
            "Lever: sites_configured=%d sites_successful=%d sites_failed=%d "
            "raw_jobs=%d title_matched=%d location_matched=%d",
            len(configured_sites),
            successful,
            failed,
            raw_count,
            title_count,
            location_count,
        )
        return jobs

    async def _fetch_site(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        site_entry: dict[str, str],
        queries: list[str],
        target_locations: list[str],
    ) -> tuple[bool, int, int, int, list[NormalizedJobSchema]]:
        company = site_entry["company"]
        site = site_entry["site"]
        url = f"https://api.lever.co/v0/postings/{site}?mode=json"

        try:
            async with semaphore:
                response = await client.get(url)
            if response.status_code != 200:
                logger.warning("Lever site '%s' returned HTTP %d", site, response.status_code)
                return False, 0, 0, 0, []
            raw_jobs = response.json()
            if not isinstance(raw_jobs, list):
                raise ValueError("Lever response was not a postings list")
        except Exception as exc:
            logger.warning("Lever site '%s' failed: %s", site, exc)
            return False, 0, 0, 0, []

        title_matched = location_matched = 0
        accepted: list[NormalizedJobSchema] = []
        for item in raw_jobs:
            title = str(item.get("text") or "")
            if not title_matches_queries(title, queries):
                continue
            title_matched += 1

            description = self._description(item)
            location = self._location(item)
            if not ats_location_matches(location, description, target_locations):
                continue
            location_matched += 1

            normalized = self._normalize(company, site, item, location, description)
            if normalized is not None:
                accepted.append(normalized)

        return True, len(raw_jobs), title_matched, location_matched, accepted

    @staticmethod
    def _description(item: dict[str, Any]) -> str:
        plain_parts = [item.get("descriptionPlain"), item.get("additionalPlain")]
        plain = " ".join(str(part) for part in plain_parts if part)
        if plain:
            return plain
        return html_to_text(item.get("description"))

    @staticmethod
    def _location(item: dict[str, Any]) -> str:
        values: list[str] = []
        categories = item.get("categories") or {}
        if isinstance(categories, dict) and categories.get("location"):
            values.append(str(categories["location"]))

        for location in item.get("allLocations") or []:
            if isinstance(location, dict):
                value = location.get("name") or location.get("location")
            else:
                value = location
            if value and str(value) not in values:
                values.append(str(value))

        country = item.get("country")
        if country and str(country) not in values:
            values.append(str(country))
        return " / ".join(values) or "Remote"

    def _normalize(
        self,
        company: str,
        site: str,
        item: dict[str, Any],
        location: str,
        description: str,
    ) -> NormalizedJobSchema | None:
        external_id = str(item.get("id") or "").strip()
        if not external_id:
            return None
        provider_id = f"{site}_{external_id}"
        apply_url = item.get("hostedUrl") or item.get("applyUrl") or f"https://jobs.lever.co/{site}/{external_id}"
        title = str(item.get("text") or "Software Engineer")
        salary_range = item.get("salaryRange") or {}
        salary_min = salary_range.get("min") if isinstance(salary_range, dict) else None
        salary_max = salary_range.get("max") if isinstance(salary_range, dict) else None

        return NormalizedJobSchema(
            job_hash=self.generate_job_hash(self.name, provider_id),
            source=self.name,
            external_id=provider_id,
            title=title,
            company=company,
            location=location,
            remote=(
                str(item.get("workplaceType") or "").lower() == "remote"
                or "remote" in f"{location} {title}".lower()
            ),
            description=description or None,
            salary_min=float(salary_min) if salary_min is not None else None,
            salary_max=float(salary_max) if salary_max is not None else None,
            salary_currency=salary_range.get("currency") if isinstance(salary_range, dict) else None,
            salary_interval=salary_range.get("interval") if isinstance(salary_range, dict) else None,
            salary_source="provider" if salary_min is not None or salary_max is not None else None,
            apply_url=str(apply_url),
            source_url=str(apply_url),
            posted_date=parse_provider_datetime(item.get("createdAt")),
            is_active=True,
        )


async def fetch(
    queries: list[str],
    target_locations: list[str],
    concurrency: int = 8,
    sites: Iterable[dict[str, str]] | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[NormalizedJobSchema]:
    return await LeverProvider().fetch(
        queries=queries,
        target_locations=target_locations,
        concurrency=concurrency,
        sites=sites,
        client=client,
    )
