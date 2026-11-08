"""Bounded full-description enrichment for Adzuna snippets."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from sqlalchemy import or_, select, update

from app.ai_job_search.experience import extract_experience_facts
from app.ai_job_search.models import AIJob
from app.company_watch.http import RequestBudget, public_client, request_public
from app.database.database import AsyncSessionLocal


logger = logging.getLogger(__name__)
MAX_BATCH = 30
MAX_CONCURRENCY = 3
RETRY_AFTER = timedelta(days=1)


def _same_job(expected_title: str, expected_company: str, posting: dict) -> bool:
    title = str(posting.get("title") or "")
    organization = posting.get("hiringOrganization") or {}
    company = str(organization.get("name") or "") if isinstance(organization, dict) else ""
    def words(value: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", value.lower()))
    expected_words = words(expected_title)
    title_words = words(title)
    if not expected_words or len(expected_words & title_words) < max(1, len(expected_words) - 1):
        return False
    expected_company_words = words(expected_company)
    company_words = words(company)
    return bool(company_words and expected_company_words & company_words)


def _job_postings(value):
    if isinstance(value, list):
        for item in value:
            yield from _job_postings(item)
    elif isinstance(value, dict):
        types = value.get("@type") or []
        if types == "JobPosting" or "JobPosting" in (types if isinstance(types, list) else [types]):
            yield value
        for key in ("@graph", "mainEntity"):
            if key in value:
                yield from _job_postings(value[key])


def extract_structured_description(
    page_html: str, expected_title: str, expected_company: str, excerpt: str
) -> str | None:
    """Accept only a larger structured description for the expected employer and role."""
    soup = BeautifulSoup(page_html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or script.get_text())
        except (TypeError, ValueError):
            continue
        for posting in _job_postings(data):
            if not _same_job(expected_title, expected_company, posting):
                continue
            raw_description = posting.get("description")
            if not isinstance(raw_description, str):
                continue
            full_text = BeautifulSoup(raw_description, "html.parser").get_text("\n", strip=True)
            if len(full_text) >= max(400, len(excerpt) + 80):
                return full_text[:100_000]
    return None


async def _fetch_full_description(client, job: AIJob) -> str | None:
    source_url = job.source_url or ""
    host = (urlsplit(source_url).hostname or "").lower()
    if urlsplit(source_url).scheme != "https" or not (host == "adzuna.in" or host.endswith(".adzuna.in")):
        return None
    response = await request_public(
        client, source_url,
        budget=RequestBudget(remaining=3, max_bytes=600_000, max_redirects=2),
    )
    chain = response.extensions.get("redirect_chain", [])
    if any(urlsplit(url).scheme != "https" for url in chain):
        return None
    if response.status_code != 200 or "text/html" not in response.headers.get("content-type", ""):
        return None
    return extract_structured_description(
        response.text, job.title, job.company, job.description_excerpt or job.description or ""
    )


async def enrich_due_jobs(
    *, limit: int = 20, concurrency: int = 3, job_ids: list[int] | None = None
) -> dict[str, int]:
    """Enrich a limited batch without delaying an on-demand user search."""
    limit = max(1, min(limit, MAX_BATCH))
    concurrency = max(1, min(concurrency, MAX_CONCURRENCY))
    cutoff = datetime.utcnow() - RETRY_AFTER
    async with AsyncSessionLocal() as db:
        stmt = select(AIJob).where(
            AIJob.source == "adzuna",
            AIJob.description_completeness == "snippet",
            AIJob.is_active.is_(True),
            or_(
                AIJob.description_enrichment_checked_at.is_(None),
                AIJob.description_enrichment_checked_at < cutoff,
            ),
        )
        if job_ids is not None:
            stmt = stmt.where(AIJob.id.in_(job_ids))
        rows = await db.execute(
            stmt.order_by(AIJob.first_seen_at.desc(), AIJob.id.desc())
            .limit(limit).with_for_update(skip_locked=True)
        )
        jobs = rows.scalars().all()
        claimed_at = datetime.utcnow()
        for job in jobs:
            job.description_enrichment_checked_at = claimed_at
            job.description_enrichment_status = "pending"
        await db.commit()

    stats = {"attempted": len(jobs), "enriched": 0, "unavailable": 0}
    if not jobs:
        return stats
    semaphore = asyncio.Semaphore(concurrency)
    async with public_client() as client:
        async def inspect(job: AIJob):
            async with semaphore:
                try:
                    return job, await _fetch_full_description(client, job)
                except Exception as error:
                    logger.info("Description enrichment unavailable for job %s: %s", job.id, error)
                    return job, None

        results = await asyncio.gather(*(inspect(job) for job in jobs))

    async with AsyncSessionLocal() as db:
        for job, full_text in results:
            values = {"description_enrichment_status": "unavailable"}
            if full_text:
                facts = extract_experience_facts(job.title, full_text, completeness="full")
                values.update({
                    "description": full_text,
                    "description_excerpt": job.description_excerpt or job.description,
                    "description_completeness": "full",
                    "description_enrichment_status": "enriched",
                    "required_experience_min": facts.required_min,
                    "required_experience_max": facts.required_max,
                    "experience_source": facts.source,
                    "experience_confidence": facts.confidence,
                    "experience_evidence": facts.evidence,
                    "seniority_level": facts.seniority_level,
                    "seniority_confidence": facts.seniority_confidence,
                    "experience_parse_version": 1,
                })
            result = await db.execute(
                update(AIJob).where(
                    AIJob.id == job.id,
                    AIJob.description_completeness == "snippet",
                    AIJob.description_enrichment_checked_at == claimed_at,
                ).values(**values)
            )
            if result.rowcount:
                stats["enriched" if full_text else "unavailable"] += 1
        await db.commit()
    return stats


def main():
    parser = argparse.ArgumentParser(description="Enrich a bounded batch of Adzuna job descriptions")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--job-ids", type=int, nargs="*")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(enrich_due_jobs(
        limit=args.limit, concurrency=args.concurrency, job_ids=args.job_ids
    )), sort_keys=True))


if __name__ == "__main__":
    main()
