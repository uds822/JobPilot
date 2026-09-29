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
from app.ai_job_search.providers.ats_registry import GREENHOUSE_BOARDS
from app.ai_job_search.providers.base import JobProvider
from app.ai_job_search.schemas import NormalizedJobSchema

logger = logging.getLogger(__name__)

# Retained for compatibility with existing imports.
CURATED_GREENHOUSE_BOARDS = [entry["board"] for entry in GREENHOUSE_BOARDS]


class GreenhouseProvider(JobProvider):
    """Greenhouse public job-board provider with bounded board concurrency."""

    def __init__(self) -> None:
        super().__init__(name="greenhouse")

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
            boards=[{"company": company, "board": company}],
            concurrency=1,
        )
        return jobs[:max_results]

    async def fetch(
        self,
        queries: list[str],
        target_locations: list[str],
        concurrency: int = 8,
        boards: Iterable[dict[str, str]] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> list[NormalizedJobSchema]:
        configured_boards = list(GREENHOUSE_BOARDS if boards is None else boards)
        semaphore = asyncio.Semaphore(concurrency)

        async def run(active_client: httpx.AsyncClient):
            tasks = [
                self._fetch_board(
                    active_client,
                    semaphore,
                    entry,
                    queries,
                    target_locations,
                )
                for entry in configured_boards
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
                logger.warning("Greenhouse board task failed: %s", result)
                continue
            success, raw, title_matched, location_matched, board_jobs = result
            successful += int(success)
            failed += int(not success)
            raw_count += raw
            title_count += title_matched
            location_count += location_matched
            jobs.extend(board_jobs)

        logger.info(
            "Greenhouse: boards_configured=%d boards_successful=%d boards_failed=%d "
            "raw_jobs=%d title_matched=%d location_matched=%d",
            len(configured_boards),
            successful,
            failed,
            raw_count,
            title_count,
            location_count,
        )
        return jobs

    async def _fetch_board(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        board_entry: dict[str, str],
        queries: list[str],
        target_locations: list[str],
    ) -> tuple[bool, int, int, int, list[NormalizedJobSchema]]:
        company = board_entry["company"]
        board = board_entry["board"]
        url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"

        try:
            async with semaphore:
                response = await client.get(url)
            if response.status_code != 200:
                logger.warning("Greenhouse board '%s' returned HTTP %d", board, response.status_code)
                return False, 0, 0, 0, []
            raw_jobs = response.json().get("jobs", [])
        except Exception as exc:
            logger.warning("Greenhouse board '%s' failed: %s", board, exc)
            return False, 0, 0, 0, []

        title_matched = location_matched = 0
        accepted: list[NormalizedJobSchema] = []
        for item in raw_jobs:
            title = str(item.get("title") or "")
            if not title_matches_queries(title, queries):
                continue
            title_matched += 1

            description = html_to_text(item.get("content"))
            location = self._location(item)
            if not ats_location_matches(location, description, target_locations):
                continue
            location_matched += 1

            normalized = self._normalize(company, board, item, location, description)
            if normalized is not None:
                accepted.append(normalized)

        return True, len(raw_jobs), title_matched, location_matched, accepted

    @staticmethod
    def _location(item: dict[str, Any]) -> str:
        location = item.get("location") or {}
        if isinstance(location, dict) and location.get("name"):
            return str(location["name"])
        offices = item.get("offices") or []
        office_names = [
            str(office.get("name"))
            for office in offices
            if isinstance(office, dict) and office.get("name")
        ]
        return " / ".join(office_names) or "Remote"

    def _normalize(
        self,
        company: str,
        board: str,
        item: dict[str, Any],
        location: str,
        description: str,
    ) -> NormalizedJobSchema | None:
        external_id = str(item.get("id") or "").strip()
        if not external_id:
            return None
        provider_id = f"{board}_{external_id}"
        apply_url = item.get("absolute_url") or f"https://boards.greenhouse.io/{board}/jobs/{external_id}"
        title = str(item.get("title") or "Software Engineer")

        return NormalizedJobSchema(
            job_hash=self.generate_job_hash(self.name, provider_id),
            source=self.name,
            external_id=provider_id,
            title=title,
            company=company,
            location=location,
            remote="remote" in f"{location} {title}".lower(),
            description=description or None,
            salary_min=None,
            salary_max=None,
            salary_currency=None,
            salary_interval=None,
            salary_source=None,
            apply_url=str(apply_url),
            source_url=str(apply_url),
            posted_date=parse_provider_datetime(item.get("updated_at")),
            is_active=True,
        )


async def fetch(
    queries: list[str],
    target_locations: list[str],
    concurrency: int = 8,
    boards: Iterable[dict[str, str]] | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[NormalizedJobSchema]:
    return await GreenhouseProvider().fetch(
        queries=queries,
        target_locations=target_locations,
        concurrency=concurrency,
        boards=boards,
        client=client,
    )
