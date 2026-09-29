import asyncio
import hashlib
import selectors
from datetime import datetime, timedelta
from uuid import uuid4

import httpx
from sqlalchemy import delete, func, select

from app.ai_job_search.models import AIJob
from app.ai_job_search.schemas import NormalizedJobSchema
from app.company_watch.models import CompanySource, CompanySourceCheck, CompanyWatchRun
from app.company_watch.service import (
    ClaimedSource,
    IngestionResult,
    SourceCheckResult,
    _claim_due_sources,
    _ingest_one,
    _record_ingestion_results,
)
from app.database.database import AsyncSessionLocal, engine
from app.models.companies import Company


def _run(coro):
    async def run_and_dispose():
        try:
            return await coro
        finally:
            await engine.dispose()

    with asyncio.Runner(
        loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())
    ) as runner:
        return runner.run(run_and_dispose())


def _claim(source, company_name, token):
    return ClaimedSource(
        id=source.id,
        company_id=source.company_id,
        company=company_name,
        provider=source.provider,
        identifier=source.identifier,
        source_url=source.source_url,
        claim_token=token,
    )


def test_malformed_greenhouse_snapshot_is_not_complete():
    async def scenario():
        claimed = ClaimedSource(
            id=1,
            company_id=1,
            company="Example",
            provider="greenhouse",
            identifier="example",
            source_url="https://boards-api.greenhouse.io/v1/boards/example/jobs?content=false",
            claim_token="test-token",
        )

        def handler(request: httpx.Request):
            return httpx.Response(200, json={})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await _ingest_one(client, asyncio.Semaphore(1), claimed)

        assert result.snapshot_complete is False
        assert result.source_result.status == "temporary_failure"
        assert result.jobs == ()

    asyncio.run(scenario())


def test_confirmed_missing_lifecycle_and_reappearance():
    async def scenario():
        suffix = uuid4().hex
        company_id = source_id = job_id = None
        run_ids = []
        try:
            async with AsyncSessionLocal() as db:
                company = Company(name=f"Watch Lifecycle {suffix}")
                db.add(company)
                await db.flush()
                company_id = company.id
                source = CompanySource(
                    company_id=company.id,
                    provider="greenhouse",
                    identifier=f"watch-{suffix}",
                    source_url=f"https://example.com/{suffix}",
                    status="healthy",
                    next_check_at=datetime.utcnow(),
                    next_verify_at=datetime.utcnow(),
                )
                db.add(source)
                await db.flush()
                source_id = source.id
                canonical = AIJob(
                    job_hash=hashlib.sha256(suffix.encode()).hexdigest(),
                    source="greenhouse",
                    external_id=f"watch-{suffix}_1",
                    title="Software Engineer",
                    company=company.name,
                    location="Bengaluru",
                    description="Python",
                    apply_url=f"https://example.com/{suffix}/apply",
                    source_url=f"https://example.com/{suffix}/job",
                    ingestion_source_id=source.id,
                    is_active=True,
                    last_seen_at=datetime.utcnow() - timedelta(days=1),
                )
                db.add(canonical)
                await db.commit()
                job_id = canonical.id

            for missing_count in (1, 2):
                observed_at = datetime.utcnow()
                token = str(uuid4())
                async with AsyncSessionLocal() as db:
                    source = await db.get(CompanySource, source_id)
                    source.claim_token = token
                    source.claimed_until = observed_at + timedelta(minutes=5)
                    run = CompanyWatchRun(
                        run_type="ingest", status="running", sources_claimed=1
                    )
                    db.add(run)
                    await db.commit()
                    run_ids.append(run.id)
                    claimed = _claim(source, f"Watch Lifecycle {suffix}", token)

                result = IngestionResult(
                    SourceCheckResult(
                        claimed,
                        "healthy_empty",
                        200,
                        0,
                        0,
                        10,
                        observed_at=observed_at,
                    ),
                    (),
                    True,
                )
                await _record_ingestion_results(run.id, [result])

                async with AsyncSessionLocal() as db:
                    canonical = await db.get(AIJob, job_id)
                    assert canonical.missing_poll_count == missing_count
                    assert canonical.is_active is (missing_count < 2)

            observed_at = datetime.utcnow()
            token = str(uuid4())
            async with AsyncSessionLocal() as db:
                source = await db.get(CompanySource, source_id)
                source.claim_token = token
                source.claimed_until = observed_at + timedelta(minutes=5)
                run = CompanyWatchRun(
                    run_type="ingest", status="running", sources_claimed=1
                )
                db.add(run)
                await db.commit()
                run_ids.append(run.id)
                claimed = _claim(source, f"Watch Lifecycle {suffix}", token)

            returned_job = NormalizedJobSchema(
                job_hash=hashlib.sha256(suffix.encode()).hexdigest(),
                source="greenhouse",
                external_id=f"watch-{suffix}_1",
                title="Software Engineer II",
                company=f"Watch Lifecycle {suffix}",
                location="Bengaluru",
                description="Python FastAPI",
                apply_url=f"https://example.com/{suffix}/apply",
                source_url=f"https://example.com/{suffix}/job",
            )
            await _record_ingestion_results(
                run.id,
                [
                    IngestionResult(
                        SourceCheckResult(
                            claimed,
                            "healthy",
                            200,
                            1,
                            1,
                            10,
                            observed_at=observed_at,
                        ),
                        (returned_job,),
                        True,
                    )
                ],
            )
            async with AsyncSessionLocal() as db:
                canonical = await db.get(AIJob, job_id)
                source = await db.get(CompanySource, source_id)
                assert canonical.is_active is True
                assert canonical.missing_poll_count == 0
                assert canonical.title == "Software Engineer II"
                assert canonical.last_verified_at == observed_at
                assert source.last_ingested_at == observed_at
        finally:
            async with AsyncSessionLocal() as db:
                if job_id is not None:
                    await db.execute(delete(AIJob).where(AIJob.id == job_id))
                if source_id is not None:
                    await db.execute(
                        delete(CompanySourceCheck).where(
                            CompanySourceCheck.company_source_id == source_id
                        )
                    )
                    await db.execute(
                        delete(CompanySource).where(CompanySource.id == source_id)
                    )
                if run_ids:
                    await db.execute(
                        delete(CompanyWatchRun).where(CompanyWatchRun.id.in_(run_ids))
                    )
                if company_id is not None:
                    await db.execute(delete(Company).where(Company.id == company_id))
                await db.commit()

    _run(scenario())


def test_concurrent_claims_are_distinct_and_stale_worker_result_is_ignored():
    async def scenario():
        suffix = uuid4().hex
        company_ids = []
        source_ids = []
        run_ids = []
        try:
            async with AsyncSessionLocal() as db:
                for index in range(2):
                    company = Company(name=f"Claim Test {index} {suffix}")
                    db.add(company)
                    await db.flush()
                    company_ids.append(company.id)
                    source = CompanySource(
                        company_id=company.id,
                        provider="greenhouse",
                        identifier=f"claim-{index}-{suffix}",
                        source_url=f"https://example.com/{suffix}/{index}",
                        status="healthy",
                        last_success_at=datetime.utcnow(),
                        next_check_at=datetime.utcnow() - timedelta(minutes=1),
                        next_verify_at=datetime.utcnow() - timedelta(minutes=1),
                    )
                    db.add(source)
                    await db.flush()
                    source_ids.append(source.id)
                await db.commit()

            first, second = await asyncio.gather(
                _claim_due_sources(1, run_type="ingest", source_ids=source_ids),
                _claim_due_sources(1, run_type="ingest", source_ids=source_ids),
            )
            run_ids.extend([first[0], second[0]])
            claimed = first[1] + second[1]
            assert len(claimed) == 2
            assert {item.id for item in claimed} == set(source_ids)
            assert len({item.claim_token for item in claimed}) == 2

            stale_claim = claimed[0]
            async with AsyncSessionLocal() as db:
                source = await db.get(CompanySource, stale_claim.id)
                source.claim_token = str(uuid4())
                source.claimed_until = datetime.utcnow() + timedelta(minutes=5)
                await db.commit()

            await _record_ingestion_results(
                first[0],
                [
                    IngestionResult(
                        SourceCheckResult(
                            stale_claim,
                            "healthy_empty",
                            200,
                            0,
                            0,
                            10,
                            observed_at=datetime.utcnow(),
                        ),
                        (),
                        True,
                    )
                ],
            )

            async with AsyncSessionLocal() as db:
                check_count = await db.scalar(
                    select(func.count(CompanySourceCheck.id)).where(
                        CompanySourceCheck.company_source_id == stale_claim.id
                    )
                )
                source = await db.get(CompanySource, stale_claim.id)
                assert check_count == 0
                assert source.claim_token != stale_claim.claim_token
                assert source.last_ingested_at is None
        finally:
            async with AsyncSessionLocal() as db:
                if source_ids:
                    await db.execute(
                        delete(CompanySourceCheck).where(
                            CompanySourceCheck.company_source_id.in_(source_ids)
                        )
                    )
                    await db.execute(
                        delete(CompanySource).where(CompanySource.id.in_(source_ids))
                    )
                if run_ids:
                    await db.execute(
                        delete(CompanyWatchRun).where(CompanyWatchRun.id.in_(run_ids))
                    )
                if company_ids:
                    await db.execute(delete(Company).where(Company.id.in_(company_ids)))
                await db.commit()

    _run(scenario())
