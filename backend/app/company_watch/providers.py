"""Shared complete-snapshot contract for supported employer ATS feeds."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from typing import Awaitable, Callable

from app.ai_job_search.providers.ashby import AshbyProvider
from app.ai_job_search.providers.ats_filters import html_to_text
from app.ai_job_search.providers.greenhouse import GreenhouseProvider
from app.ai_job_search.providers.lever import LeverProvider
from app.ai_job_search.schemas import NormalizedJobSchema

@dataclass(frozen=True)
class FetchResult:
    jobs: tuple[NormalizedJobSchema, ...]
    raw_count: int
    is_complete: bool
    scope: str = "india_technical_v1"
    pages_fetched: int = 1
    error: str | None = None


Request = Callable[..., Awaitable[Any]]


def source_url(provider: str, identifier: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", identifier):
        raise ValueError("Invalid ATS board identifier")
    templates = {
        "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{}/jobs?content=true",
        "lever": "https://api.lever.co/v0/postings/{}?mode=json",
        "ashby": "https://api.ashbyhq.com/posting-api/job-board/{}?includeCompensation=true",
    }
    if provider not in templates:
        raise ValueError(f"Unsupported Company Watch provider: {provider}")
    return templates[provider].format(identifier)


@dataclass(frozen=True)
class ATSAdapter:
    provider: str
    normalizer: Any
    title_field: str
    payload_field: str | None

    async def fetch(self, source, request: Request) -> FetchResult:
        response = await request(source_url(self.provider, source.identifier))
        response.raise_for_status()
        jobs = self.snapshot(source.identifier, response.json())
        normalized = [self.normalize(source.company, source.identifier, item) for item in jobs]
        return FetchResult(tuple(job for job in normalized if job), len(jobs), True)

    def snapshot(self, identifier: str, payload: Any) -> list[dict[str, Any]]:
        if self.payload_field:
            if not isinstance(payload, dict) or self.payload_field not in payload:
                raise ValueError(f"{self.provider} response did not include a jobs snapshot")
            jobs = payload[self.payload_field]
        else:
            jobs = payload
        if not isinstance(jobs, list):
            raise ValueError("Unexpected ATS response shape")
        identities = set()
        for item in jobs:
            if not isinstance(item, dict) or not isinstance(item.get(self.title_field), str) or not item[self.title_field].strip():
                raise ValueError("Snapshot contains a malformed posting")
            if self.provider == "ashby":
                if not isinstance(item.get("isListed"), bool):
                    raise ValueError("Ashby listing visibility is missing")
                identity = self.normalizer.posting_id(identifier, item)
            else:
                identity = str(item.get("id") or "").strip()
            if not identity or identity in identities:
                raise ValueError("Snapshot contains missing or duplicate posting identities")
            identities.add(identity)
        return jobs

    def normalize(self, company: str, identifier: str, item: dict[str, Any]) -> NormalizedJobSchema | None:
        if self.provider == "ashby":
            return self.normalizer._normalize(company, identifier, item)
        description = (
            html_to_text(item.get("content"))
            if self.provider == "greenhouse"
            else self.normalizer._description(item)
        )
        return self.normalizer._normalize(
            company, identifier, item, self.normalizer._location(item), description
        )


ADAPTERS = {
    "greenhouse": ATSAdapter("greenhouse", GreenhouseProvider(), "title", "jobs"),
    "lever": ATSAdapter("lever", LeverProvider(), "text", None),
    "ashby": ATSAdapter("ashby", AshbyProvider(), "title", "jobs"),
}

from app.company_watch.careers_adapters import GoogleAdapter, SmartRecruitersAdapter, StructuredAdapter, WorkdayAdapter

ADAPTERS.update({
    "google": GoogleAdapter(),
    "smartrecruiters": SmartRecruitersAdapter(),
    "workday": WorkdayAdapter(),
    "direct_html": StructuredAdapter("direct_html"),
    "custom_api": StructuredAdapter("custom_api"),
})
SUPPORTED_PROVIDERS = frozenset(ADAPTERS)


def get_adapter(provider: str):
    if provider not in ADAPTERS:
        raise ValueError(f"Unsupported Company Watch provider: {provider}")
    return ADAPTERS[provider]
