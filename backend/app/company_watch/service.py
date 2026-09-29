from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_job_search.providers.ats_filters import (
    ats_location_matches,
    title_matches_queries,
)
from app.company_watch.providers import SUPPORTED_PROVIDERS, get_adapter, source_url
from app.company_watch.http import RequestBudget, public_client, request_public
from app.company_watch.registry import load_registry, register_companies
from app.ai_job_search.schemas import NormalizedJobSchema
from app.ai_job_search.models import AIJob
from app.ai_job_search.persistence import upsert_canonical_jobs
from app.database.database import AsyncSessionLocal
from app.models.applications import Application as _Application
from app.models.companies import Company
from app.models.jobs import Job as _Job
from app.models.users import User as _User
from app.company_watch.models import (
    CompanyIntelligence,
    CompanySource,
    CompanySourceCheck,
    CompanyWatchRun,
)

logger = logging.getLogger(__name__)
LEASE_DURATION = timedelta(minutes=5)
LEASE_HEARTBEAT_SECONDS = 60
MAX_BACKOFF_HOURS = 72
STALE_RECHECK_DAYS = 30
MISSING_POSTING_POLLS_BEFORE_DEACTIVATE = 2
GENERIC_INGESTION_QUERIES = [
    "engineer", "developer", "software", "data scientist", "data analyst",
    "devops", "qa", "technical", "security analyst", "ux designer",
    "ui designer", "sre", "machine learning", "firmware", "embedded",
]


@dataclass(frozen=True)
class ClaimedSource:
    id: int
    company_id: int
    company: str
    provider: str
    identifier: str
    source_url: str
    claim_token: str


@dataclass(frozen=True)
class SourceCheckResult:
    source: ClaimedSource
    status: str
    http_status: int | None
    jobs_found: int
    india_jobs_found: int
    duration_ms: int
    error_message: str | None = None
    observed_at: datetime | None = None


@dataclass(frozen=True)
class IngestionResult:
    source_result: SourceCheckResult
    jobs: tuple[NormalizedJobSchema, ...]
    snapshot_complete: bool = False
    inventory_scope: str = "india_technical_v1"


async def seed_existing_ats_registry(db: AsyncSession) -> int:
    """Compatibility wrapper for the complete bootstrap registry."""
    summary = await register_companies(db, load_registry())
    return summary["new_sources"]


async def _claim_due_sources(
    limit: int,
    force: bool = False,
    run_type: str = "verify",
    source_ids: list[int] | None = None,
) -> tuple[int, list[ClaimedSource]]:
    now = datetime.utcnow()
    token = str(uuid4())
    async with AsyncSessionLocal() as db:
        run = CompanyWatchRun(run_type=run_type, status="running")
        db.add(run)
        await db.flush()

        conditions = [
            CompanySource.is_active.is_(True),
            CompanySource.provider.in_(SUPPORTED_PROVIDERS),
            CompanySource.status.not_in(("unsupported", "adapter_required", "ownership_conflict")),
            CompanySource.ownership_status.in_(("registry_trusted", "ownership_verified")),
            ~select(CompanyIntelligence.company_id).where(
                CompanyIntelligence.company_id == CompanySource.company_id,
                CompanyIntelligence.is_active.is_(False),
            ).exists(),
            (CompanySource.claimed_until.is_(None) | (CompanySource.claimed_until <= now)),
        ]
        if source_ids is not None:
            conditions.append(CompanySource.id.in_(source_ids))
        if run_type != "verify":
            conditions.extend([
                (CompanySource.last_verified_at.is_not(None) | CompanySource.last_success_at.is_not(None)),
                CompanySource.status.not_in(("unverified", "stale", "unsupported", "adapter_required", "ownership_conflict")),
            ])
        due_column = (
            CompanySource.next_check_at
            if run_type != "verify"
            else CompanySource.next_verify_at
        )
        if not force:
            conditions.append(due_column <= now)
        sources = (
            await db.execute(
                select(CompanySource, Company.name)
                .join(Company, Company.id == CompanySource.company_id)
                .where(*conditions)
                .order_by(due_column, CompanySource.id)
                .limit(limit)
                .with_for_update(of=CompanySource, skip_locked=True)
            )
            ).all()

        claimed = [
            ClaimedSource(
                id=source.id,
                company_id=source.company_id,
                company=company_name,
                provider=source.provider,
                identifier=source.identifier,
                source_url=source.source_url,
                claim_token=token,
            )
            for source, company_name in sources
        ]
        for source, _ in sources:
            source.claim_token = token
            source.claimed_until = now + LEASE_DURATION
        run.sources_claimed = len(claimed)
        if not claimed:
            run.status = "completed"
            run.completed_at = now
        await db.commit()
        return run.id, claimed


async def _request_with_retries(
    client: httpx.AsyncClient,
    global_semaphore: asyncio.Semaphore,
    url: str,
    host_semaphores: dict[str, asyncio.Semaphore] | None = None,
    *,
    budget: RequestBudget | None = None,
    method: str = "GET",
    json=None,
    deadline: float | None = None,
) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(3):
        if deadline is not None and time.perf_counter() >= deadline:
            raise ValueError("Fetch time budget exhausted")
        try:
            response = await request_public(client, url, budget=budget, method=method, json=json,
                semaphore=global_semaphore, hosts=host_semaphores)
            if response.status_code != 429 and response.status_code < 500:
                return response
            if attempt == 2:
                return response
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_error = exc
            if attempt == 2:
                raise
        await asyncio.sleep(0.25 * (2**attempt))
    if last_error is not None:
        raise last_error
    raise RuntimeError("Source request failed without a response")


async def _renew_claims_until_stopped(
    sources: list[ClaimedSource],
    stop_event: asyncio.Event,
) -> None:
    if not sources:
        return
    while True:
        try:
            await asyncio.wait_for(
                stop_event.wait(), timeout=LEASE_HEARTBEAT_SECONDS
            )
            return
        except asyncio.TimeoutError:
            pass

        renewed_until = datetime.utcnow() + LEASE_DURATION
        async with AsyncSessionLocal() as db:
            for source in sources:
                await db.execute(
                    update(CompanySource)
                    .where(
                        CompanySource.id == source.id,
                        CompanySource.claim_token == source.claim_token,
                        CompanySource.claimed_until > datetime.utcnow(),
                    )
                    .values(claimed_until=renewed_until)
                )
            await db.commit()


async def _verify_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    source: ClaimedSource,
    host_semaphores: dict[str, asyncio.Semaphore] | None = None,
) -> SourceCheckResult:
    ingestion = await _ingest_one(client, semaphore, source, host_semaphores)
    return ingestion.source_result


async def _record_results(run_id: int, results: list[SourceCheckResult]) -> None:
    for result in results:
        observed_at = result.observed_at or datetime.utcnow()
        try:
            async with AsyncSessionLocal() as db:
                source = await db.scalar(
                    select(CompanySource)
                    .where(CompanySource.id == result.source.id)
                    .with_for_update()
                )
                if (
                    source is None
                    or source.claim_token != result.source.claim_token
                    or source.claimed_until is None
                    or source.claimed_until <= datetime.utcnow()
                ):
                    await db.rollback()
                    logger.warning(
                        "Ignoring verification result after lease loss for source_id=%s",
                        result.source.id,
                    )
                    continue

                run = await db.get(CompanyWatchRun, run_id)
                if run is None:
                    await db.rollback()
                    continue

                source.status = result.status
                source.last_http_status = result.http_status
                source.last_error = result.error_message
                source.claim_token = None
                source.claimed_until = None
                if result.status in {"healthy", "healthy_empty"}:
                    source.last_success_at = observed_at
                    source.last_verified_at = observed_at
                    source.consecutive_failures = 0
                    source.next_verify_at = observed_at + timedelta(
                        minutes=source.poll_interval_minutes
                    )
                    if result.jobs_found:
                        source.last_job_seen_at = observed_at
                    intelligence = await db.get(CompanyIntelligence, source.company_id)
                    if intelligence is not None and result.india_jobs_found:
                        intelligence.india_hiring = True
                elif result.status == "partial":
                    source.last_verified_at = observed_at
                    if result.error_message:
                        source.consecutive_failures += 1
                        source.last_failure_at = observed_at
                        source.next_verify_at = observed_at + timedelta(hours=min(72, 2 ** min(source.consecutive_failures - 1, 7)))
                    else:
                        source.consecutive_failures = 0
                        source.next_verify_at = observed_at + timedelta(minutes=source.poll_interval_minutes)
                else:
                    source.last_failure_at = observed_at
                    source.consecutive_failures += 1
                    if result.status == "stale":
                        source.next_verify_at = observed_at + timedelta(
                            days=STALE_RECHECK_DAYS
                        )
                    else:
                        delay = min(
                            2 ** min(source.consecutive_failures - 1, 7),
                            MAX_BACKOFF_HOURS,
                        )
                        source.next_verify_at = observed_at + timedelta(hours=delay)

                db.add(
                    CompanySourceCheck(
                        company_source_id=source.id,
                        run_id=run_id,
                        checked_at=observed_at,
                        status=result.status,
                        http_status=result.http_status,
                        jobs_found=result.jobs_found,
                        india_jobs_found=result.india_jobs_found,
                        duration_ms=result.duration_ms,
                        error_message=result.error_message,
                    )
                )
                if result.status in {"healthy", "healthy_empty"}:
                    run.sources_successful += 1
                elif result.status != "partial" or result.error_message:
                    run.sources_failed += 1
                run.raw_jobs += result.jobs_found
                run.india_jobs += result.india_jobs_found
                await db.commit()
        except Exception:
            logger.exception(
                "Failed to record verification result for source_id=%s",
                result.source.id,
            )

    async with AsyncSessionLocal() as db:
        run = await db.get(CompanyWatchRun, run_id)
        if run is not None:
            run.status = "completed"
            run.completed_at = datetime.utcnow()
            await db.commit()


async def _ingest_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    source: ClaimedSource,
    host_semaphores: dict[str, asyncio.Semaphore] | None = None,
) -> IngestionResult:
    started = time.perf_counter()
    try:
        if source.provider not in SUPPORTED_PROVIDERS:
            return IngestionResult(
                SourceCheckResult(source, "unsupported", None, 0, 0, 0, "No supported adapter"),
                (), False,
            )
        budget = RequestBudget(remaining=45, max_bytes=32_000_000 if source.provider in {"greenhouse", "lever", "ashby"} else 2_000_000)
        deadline = time.perf_counter() + 90
        async def request(url, **kwargs):
            return await _request_with_retries(client, semaphore, url, host_semaphores,
                budget=budget, deadline=deadline, **kwargs)
        adapter = get_adapter(source.provider)
        inventory = await adapter.fetch(source, request)
        elapsed = round((time.perf_counter() - started) * 1000)
        observed_at = datetime.utcnow()
        normalized_jobs = []
        india_jobs = 0
        for normalized in inventory.jobs:
            if not ats_location_matches(normalized.location, normalized.description, ["India"]):
                continue
            india_jobs += 1
            if title_matches_queries(normalized.title, GENERIC_INGESTION_QUERIES):
                normalized_jobs.append(normalized)

        return IngestionResult(
            SourceCheckResult(
                source, ("healthy" if inventory.raw_count else "healthy_empty") if inventory.is_complete else ("partial" if inventory.jobs else "temporary_failure"), 200,
                inventory.raw_count, india_jobs, elapsed, inventory.error,
                observed_at=observed_at,
            ),
            tuple(normalized_jobs),
            inventory.is_complete,
            inventory.scope,
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        return IngestionResult(SourceCheckResult(source, "stale" if status == 404 else "temporary_failure", status, 0, 0,
            round((time.perf_counter() - started) * 1000), f"Source returned HTTP {status}"), (), False)
    except (httpx.TimeoutException, httpx.NetworkError, ValueError) as exc:
        elapsed = round((time.perf_counter() - started) * 1000)
        return IngestionResult(
            SourceCheckResult(
                source, "temporary_failure", None, 0, 0, elapsed,
                (str(exc) or repr(exc))[:1000],
            ),
            (),
            False,
        )
    except Exception as exc:
        elapsed = round((time.perf_counter() - started) * 1000)
        logger.exception("Company source ingestion failed for %s:%s", source.provider, source.identifier)
        return IngestionResult(
            SourceCheckResult(
                source, "temporary_failure", None, 0, 0, elapsed,
                (str(exc) or repr(exc))[:1000],
            ),
            (),
            False,
        )


async def _record_ingestion_results(run_id: int, results: list[IngestionResult]) -> None:
    for ingestion in results:
        result = ingestion.source_result
        observed_at = result.observed_at or datetime.utcnow()
        try:
            async with AsyncSessionLocal() as db:
                source = await db.scalar(
                    select(CompanySource)
                    .where(CompanySource.id == result.source.id)
                    .with_for_update()
                )
                if (
                    source is None
                    or source.claim_token != result.source.claim_token
                    or source.claimed_until is None
                    or source.claimed_until <= datetime.utcnow()
                ):
                    await db.rollback()
                    logger.warning(
                        "Ignoring ingestion result after lease loss for source_id=%s",
                        result.source.id,
                    )
                    continue

                run = await db.get(CompanyWatchRun, run_id)
                if run is None:
                    await db.rollback()
                    continue

                persistence_error = None
                inserted = updated_count = 0
                successful_snapshot = (
                    result.status in {"healthy", "healthy_empty"}
                    and ingestion.snapshot_complete
                    and ingestion.inventory_scope == "india_technical_v1"
                )
                if ingestion.jobs or successful_snapshot:
                    try:
                        async with db.begin_nested():
                            _, inserted, updated_count, _ = await upsert_canonical_jobs(
                                db,
                                list(ingestion.jobs),
                                ingestion_source_id=source.id,
                                observed_at=observed_at,
                                verification_method="company_watch",
                                inventory_scope=ingestion.inventory_scope,
                            )
                            if successful_snapshot:
                                await db.execute(
                                    update(AIJob)
                                    .where(
                                        AIJob.ingestion_source_id == source.id,
                                        AIJob.inventory_scope == ingestion.inventory_scope,
                                        AIJob.last_seen_at < observed_at,
                                        AIJob.is_active.is_(True),
                                    )
                                    .values(
                                        last_verified_at=observed_at,
                                        verification_method="company_watch",
                                        missing_poll_count=AIJob.missing_poll_count + 1,
                                        is_active=(AIJob.missing_poll_count + 1)
                                        < MISSING_POSTING_POLLS_BEFORE_DEACTIVATE,
                                    )
                                )
                    except Exception as exc:
                        persistence_error = (str(exc) or repr(exc))[:1000]
                        logger.exception(
                            "Company source persistence failed for %s:%s",
                            source.provider,
                            source.identifier,
                        )

                if persistence_error:
                    source.status = "persistence_failure"
                    source.last_error = persistence_error
                    run.persistence_failures += 1
                    run.sources_failed += 1
                else:
                    source.status = "partial" if result.status in {"healthy", "healthy_empty"} and not successful_snapshot else result.status
                    source.last_error = result.error_message
                    run.jobs_inserted += inserted
                    run.jobs_updated += updated_count
                    if successful_snapshot:
                        run.sources_successful += 1
                    elif result.status != "partial" or result.error_message:
                        run.sources_failed += 1

                source.last_http_status = result.http_status
                source.claim_token = None
                source.claimed_until = None
                if ingestion.jobs and not persistence_error:
                    source.last_observed_at = observed_at
                    if result.status == "partial":
                        source.last_verified_at = observed_at
                if successful_snapshot and not persistence_error:
                    source.last_success_at = observed_at
                    source.last_verified_at = observed_at
                    source.last_ingested_at = observed_at
                    source.last_complete_scope = ingestion.inventory_scope
                    source.consecutive_failures = 0
                    source.next_check_at = observed_at + timedelta(
                        minutes=source.poll_interval_minutes
                    )
                    source.next_verify_at = source.next_check_at
                    if result.jobs_found:
                        source.last_job_seen_at = observed_at
                    intelligence = await db.get(CompanyIntelligence, source.company_id)
                    if intelligence is not None and result.india_jobs_found:
                        intelligence.india_hiring = True
                elif result.status == "partial" and not persistence_error and not result.error_message:
                    source.consecutive_failures = 0
                    source.next_check_at = observed_at + timedelta(minutes=source.poll_interval_minutes)
                else:
                    source.last_failure_at = observed_at
                    source.consecutive_failures += 1
                    if result.status == "stale":
                        source.next_check_at = observed_at + timedelta(
                            days=STALE_RECHECK_DAYS
                        )
                    else:
                        delay = min(
                            2 ** min(source.consecutive_failures - 1, 7),
                            MAX_BACKOFF_HOURS,
                        )
                        source.next_check_at = observed_at + timedelta(hours=delay)

                db.add(
                    CompanySourceCheck(
                        company_source_id=source.id,
                        run_id=run_id,
                        checked_at=observed_at,
                        status=source.status,
                        http_status=result.http_status,
                        jobs_found=result.jobs_found,
                        india_jobs_found=result.india_jobs_found,
                        duration_ms=result.duration_ms,
                        error_message=source.last_error,
                    )
                )
                run.raw_jobs += result.jobs_found
                run.india_jobs += result.india_jobs_found
                await db.commit()
        except Exception:
            logger.exception(
                "Failed to record ingestion result for source_id=%s",
                result.source.id,
            )

    async with AsyncSessionLocal() as db:
        run = await db.get(CompanyWatchRun, run_id)
        if run is not None:
            run.status = "completed"
            run.completed_at = datetime.utcnow()
            await db.commit()


async def verify_due_sources(
    limit: int = 50,
    concurrency: int = 10,
    force: bool = False,
    source_ids: list[int] | None = None,
    request_semaphore: asyncio.Semaphore | None = None,
    host_semaphores: dict[str, asyncio.Semaphore] | None = None,
) -> dict[str, int]:
    if limit < 1 or concurrency < 1:
        raise ValueError("Limit and concurrency must be positive")
    run_id, sources = await _claim_due_sources(limit, force=force, source_ids=source_ids)
    if not sources:
        return {"run_id": run_id, "claimed": 0, "successful": 0, "failed": 0, "india_jobs": 0}

    semaphore = request_semaphore or asyncio.Semaphore(concurrency)
    host_semaphores = host_semaphores if host_semaphores is not None else {}
    stop_heartbeat = asyncio.Event()
    heartbeat = asyncio.create_task(
        _renew_claims_until_stopped(sources, stop_heartbeat)
    )
    try:
        async with public_client() as client:
            results = await asyncio.gather(
                *(
                    _verify_one(client, semaphore, source, host_semaphores)
                    for source in sources
                )
            )
        await _record_results(run_id, results)
    finally:
        stop_heartbeat.set()
        await heartbeat
    summary = {
        "run_id": run_id,
        "claimed": len(sources),
        "successful": sum(r.status in {"healthy", "healthy_empty"} for r in results),
        "failed": sum(r.status not in {"healthy", "healthy_empty", "partial"} or (r.status == "partial" and bool(r.error_message)) for r in results),
        "partial": sum(r.status == "partial" for r in results),
        "india_jobs": sum(r.india_jobs_found for r in results),
    }
    logger.info("Company source verification summary: %s", summary)
    return summary


async def ingest_due_sources(
    limit: int = 50,
    concurrency: int = 10,
    force: bool = False,
    source_ids: list[int] | None = None,
) -> dict[str, int]:
    if limit < 1 or concurrency < 1:
        raise ValueError("Limit and concurrency must be positive")
    run_id, sources = await _claim_due_sources(limit, force=force, run_type="ingest", source_ids=source_ids)
    if not sources:
        return {
            "run_id": run_id,
            "claimed": 0,
            "successful": 0,
            "failed": 0,
            "india_jobs": 0,
            "raw_jobs": 0,
            "technical_jobs": 0,
            "inserted": 0,
            "updated": 0,
            "persistence_failures": 0,
        }

    semaphore = asyncio.Semaphore(max(1, concurrency))
    host_semaphores: dict[str, asyncio.Semaphore] = {}
    stop_heartbeat = asyncio.Event()
    heartbeat = asyncio.create_task(
        _renew_claims_until_stopped(sources, stop_heartbeat)
    )
    try:
        async with public_client() as client:
            results = await asyncio.gather(
                *(
                    _ingest_one(client, semaphore, source, host_semaphores)
                    for source in sources
                )
            )
        await _record_ingestion_results(run_id, results)
    finally:
        stop_heartbeat.set()
        await heartbeat

    async with AsyncSessionLocal() as db:
        run = await db.get(CompanyWatchRun, run_id)
        summary = {
            "run_id": run_id,
            "claimed": len(sources),
            "successful": run.sources_successful if run else 0,
            "failed": run.sources_failed if run else 0,
            "india_jobs": run.india_jobs if run else 0,
            "raw_jobs": run.raw_jobs if run else 0,
            "technical_jobs": sum(len(result.jobs) for result in results),
            "inserted": run.jobs_inserted if run else 0,
            "updated": run.jobs_updated if run else 0,
            "persistence_failures": run.persistence_failures if run else 0,
        }
    logger.info("Company Watch ingestion summary: %s", summary)
    return summary


async def seed_registry(path: str | None = None) -> dict[str, int]:
    document = load_registry(path)
    async with AsyncSessionLocal() as db:
        return await register_companies(db, document)


async def source_health_status() -> list[dict[str, object]]:
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(Company, CompanyIntelligence, CompanySource)
            .join(CompanyIntelligence, CompanyIntelligence.company_id == Company.id)
            .outerjoin(CompanySource, CompanySource.company_id == Company.id)
            .order_by(Company.name, CompanySource.provider)
        )).all()
        result = []
        for company, metadata, source in rows:
            supported = source is not None and source.provider in SUPPORTED_PROVIDERS
            verified = bool(source and (source.last_verified_at or source.last_success_at))
            status = source.status if source else metadata.discovery_status
            discovery_status = metadata.discovery_status
            if verified and discovery_status == "discovery_pending":
                discovery_status = "source_verified"
            if not source and not metadata.careers_url:
                status = "needs_careers_url"
            if source and not supported:
                status = "adapter_required"
            result.append({
                "company_id": company.id,
                "company": company.name,
                "categories": metadata.tags or [],
                "careers_url": metadata.careers_url,
                "provider": source.provider if source else "pending",
                "identifier": source.identifier if source else "",
                "status": status,
                "discovery_status": discovery_status,
                "discovery_attempts": metadata.discovery_attempts,
                "discovery_error": metadata.discovery_error,
                "next_discovery_at": metadata.next_discovery_at,
                "ownership_status": source.ownership_status if source else None,
                "canonical_identity": source.canonical_identity if source else None,
                "evidence": source.discovery_evidence if source else None,
                "verified": verified,
                "fetchable": bool(supported and verified and source.is_active and metadata.is_active and source.ownership_status in {"registry_trusted", "ownership_verified"} and status not in {"unverified", "stale", "unsupported", "adapter_required", "ownership_conflict"}),
                "healthy": status in {"healthy", "healthy_empty"},
                "last_success_at": source.last_success_at if source else None,
                "last_ingested_at": source.last_ingested_at if source else None,
                "last_observed_at": source.last_observed_at if source else None,
                "last_complete_scope": source.last_complete_scope if source else None,
                "http_status": source.last_http_status if source else None,
                "error": source.last_error if source else None,
                "next_check_at": source.next_check_at if source else None,
            })
        return result


async def coverage_report():
    rows = await source_health_status()
    companies = {row["company_id"] for row in rows}
    def company_count(predicate):
        return len({row["company_id"] for row in rows if predicate(row)})
    counts = {
        "registered": len(companies),
        "with_careers_url": company_count(lambda row: bool(row["careers_url"])),
        "needs_careers_url": company_count(lambda row: not row["careers_url"]),
        "discovery_pending": company_count(lambda row: row["discovery_status"] == "discovery_pending"),
        "discovering": company_count(lambda row: row["discovery_status"] == "discovering"),
        "discovered": company_count(lambda row: bool(row["canonical_identity"])),
        "ownership_verified": company_count(lambda row: row["ownership_status"] in {"registry_trusted", "ownership_verified"}),
        "adapter_required": company_count(lambda row: row["status"] == "adapter_required"),
        "feed_validated": company_count(lambda row: row["verified"]),
        "fetchable": company_count(lambda row: row["fetchable"]),
        "healthy": company_count(lambda row: row["healthy"]),
        "discovery_failed": company_count(lambda row: row["discovery_status"] == "discovery_failed"),
        "ownership_conflict": company_count(lambda row: row["discovery_status"] == "ownership_conflict"),
        "broken": company_count(lambda row: row["status"] in {"stale", "source_broken", "temporary_failure"}),
        "ingested": company_count(lambda row: bool(row["last_ingested_at"])),
        "partial_observations": company_count(lambda row: row["status"] == "partial" and bool(row["last_observed_at"])),
    }
    async with AsyncSessionLocal() as db:
        job_counts = (await db.execute(select(CompanySource.provider, CompanySource.id, func.count(AIJob.id))
            .join(AIJob, AIJob.ingestion_source_id == CompanySource.id).where(AIJob.is_active.is_(True))
            .group_by(CompanySource.provider, CompanySource.id))).all()
    providers = {}
    for provider, source_id, count in job_counts:
        bucket = providers.setdefault(provider, {"active_jobs": 0, "sources": {}})
        bucket["active_jobs"] += count
        bucket["sources"][str(source_id)] = count
    return {"basis": "live_database_observations", "companies": counts, "providers": providers,
        "implemented_adapters": sorted(SUPPORTED_PROVIDERS), "google_direct_ingestion": "included",
        "website_careers_discovery": "included", "adzuna_included_in_direct_coverage": False}
