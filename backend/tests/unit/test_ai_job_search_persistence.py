import asyncio
import hashlib
import selectors
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.ai_job_search import services
from app.ai_job_search.models import AIJob, AIJobMatch, SearchRun, UserJobState, UserResumeProfile
from app.ai_job_search.schemas import NormalizedJobSchema
from app.database.database import AsyncSessionLocal, engine
from app.company_watch.models import CompanySource
from app.models.companies import Company
from app.models.users import User


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


def _job(external_id: str, *, source: str = "adzuna", title: str = "Python Engineer", job_hash: str | None = None):
    return NormalizedJobSchema(
        job_hash=job_hash or hashlib.sha256(f"{source}:{external_id}".encode()).hexdigest(),
        source=source,
        external_id=external_id,
        title=title,
        company="Persistence Test Co",
        location="Bengaluru",
        description="Python FastAPI PostgreSQL AWS",
        apply_url=f"https://example.com/jobs/{source}/{external_id}",
        source_url=f"https://example.com/source/{source}/{external_id}",
        salary_min=1000000,
        salary_max=2000000,
        salary_currency="INR",
        is_active=True,
    )


async def _delete_canonical_jobs(external_id: str):
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AIJob).where(AIJob.external_id == external_id))
        await db.commit()


def test_upsert_inserts_new_job_and_updates_it_on_later_run():
    async def scenario():
        external_id = f"upsert-{uuid4()}"
        await _delete_canonical_jobs(external_id)
        try:
            async with AsyncSessionLocal() as db:
                ids, inserted, updated, skipped = await services._upsert_canonical_jobs(
                    db, [_job(external_id, title="Original title", job_hash="old-hash")]
                )
                await db.commit()
                original_id = ids[("adzuna", external_id)]
                assert (inserted, updated, skipped) == (1, 0, 0)

            async with AsyncSessionLocal() as db:
                ids, inserted, updated, skipped = await services._upsert_canonical_jobs(
                    db, [_job(external_id, title="Updated title", job_hash="new-hash")]
                )
                await db.commit()
                assert ids[("adzuna", external_id)] == original_id
                assert (inserted, updated, skipped) == (0, 1, 0)

                row = (
                    await db.execute(
                        select(AIJob).where(
                            AIJob.source == "adzuna",
                            AIJob.external_id == external_id,
                        )
                    )
                ).scalar_one()
                assert row.title == "Updated title"
                assert row.job_hash == "new-hash"
        finally:
            await _delete_canonical_jobs(external_id)

    _run(scenario())


def test_same_external_id_from_different_sources_creates_two_jobs():
    async def scenario():
        external_id = f"cross-source-{uuid4()}"
        await _delete_canonical_jobs(external_id)
        try:
            async with AsyncSessionLocal() as db:
                ids, inserted, updated, skipped = await services._upsert_canonical_jobs(
                    db,
                    [
                        _job(external_id, source="adzuna"),
                        _job(external_id, source="greenhouse"),
                    ],
                )
                await db.commit()
                assert len(ids) == 2
                assert (inserted, updated, skipped) == (2, 0, 0)
        finally:
            await _delete_canonical_jobs(external_id)

    _run(scenario())


def test_duplicate_provider_job_inside_batch_is_skipped():
    async def scenario():
        external_id = f"batch-duplicate-{uuid4()}"
        await _delete_canonical_jobs(external_id)
        try:
            async with AsyncSessionLocal() as db:
                ids, inserted, updated, skipped = await services._upsert_canonical_jobs(
                    db,
                    [
                        _job(external_id, title="Highest-ranked version"),
                        _job(external_id, title="Duplicate version", job_hash="duplicate-hash"),
                    ],
                )
                await db.commit()
                assert len(ids) == 1
                assert (inserted, updated, skipped) == (1, 0, 1)

                count = await db.scalar(
                    select(func.count(AIJob.id)).where(AIJob.external_id == external_id)
                )
                assert count == 1
        finally:
            await _delete_canonical_jobs(external_id)

    _run(scenario())


def test_concurrent_upserts_share_one_canonical_row():
    async def scenario():
        external_id = f"concurrent-{uuid4()}"
        await _delete_canonical_jobs(external_id)

        async def worker(title: str):
            async with AsyncSessionLocal() as db:
                result = await services._upsert_canonical_jobs(
                    db, [_job(external_id, title=title, job_hash=f"hash-{title}")]
                )
                await db.commit()
                return result

        try:
            results = await asyncio.gather(worker("Writer A"), worker("Writer B"))
            returned_ids = {
                result[0][("adzuna", external_id)]
                for result in results
            }
            assert len(returned_ids) == 1

            async with AsyncSessionLocal() as db:
                count = await db.scalar(
                    select(func.count(AIJob.id)).where(
                        AIJob.source == "adzuna",
                        AIJob.external_id == external_id,
                    )
                )
                assert count == 1
        finally:
            await _delete_canonical_jobs(external_id)

    _run(scenario())


def test_unique_constraint_remains_enforced_for_raw_inserts():
    async def scenario():
        external_id = f"constraint-{uuid4()}"
        await _delete_canonical_jobs(external_id)
        try:
            async with AsyncSessionLocal() as db:
                first = _job(external_id, job_hash="constraint-hash-one")
                db.add(AIJob(**services._canonical_job_values(first, first.fetched_at)))
                await db.commit()

                duplicate = _job(external_id, job_hash="constraint-hash-two")
                with pytest.raises(IntegrityError):
                    async with db.begin_nested():
                        db.add(
                            AIJob(
                                **services._canonical_job_values(
                                    duplicate, duplicate.fetched_at
                                )
                            )
                        )
                        await db.flush()

                count = await db.scalar(
                    select(func.count(AIJob.id)).where(
                        AIJob.source == "adzuna",
                        AIJob.external_id == external_id,
                    )
                )
                assert count == 1
        finally:
            await _delete_canonical_jobs(external_id)

    _run(scenario())


def test_reading_stored_company_watch_job_does_not_refresh_observation_time():
    async def scenario():
        suffix = uuid4().hex
        external_id = f"stored-read-{suffix}"
        company_id = source_id = job_id = None
        observed_at = datetime.utcnow() - timedelta(days=2)
        verified_at = observed_at - timedelta(minutes=5)
        try:
            async with AsyncSessionLocal() as db:
                company = Company(name=f"Stored Read {suffix}")
                db.add(company)
                await db.flush()
                company_id = company.id
                source = CompanySource(
                    company_id=company.id,
                    provider="greenhouse",
                    identifier=f"stored-{suffix}",
                    source_url=f"https://example.com/{suffix}",
                    status="healthy",
                    last_ingested_at=observed_at,
                    next_check_at=datetime.utcnow() + timedelta(hours=1),
                    next_verify_at=datetime.utcnow() + timedelta(hours=1),
                )
                db.add(source)
                await db.flush()
                source_id = source.id

                values = services._canonical_job_values(
                    _job(external_id, source="greenhouse"), observed_at
                )
                values.update(
                    ingestion_source_id=source.id,
                    first_seen_at=observed_at,
                    last_seen_at=observed_at,
                    last_verified_at=verified_at,
                    verification_method="company_watch",
                )
                canonical = AIJob(**values)
                db.add(canonical)
                await db.commit()
                job_id = canonical.id

            async with AsyncSessionLocal() as db:
                jobs, ids_by_key = await services._fetch_stored_company_watch_jobs(
                    db, freshness_days=14
                )
                assert ids_by_key[("greenhouse", external_id)] == job_id
                assert any(job.external_id == external_id for job in jobs)

                canonical = await db.get(AIJob, job_id)
                source = await db.get(CompanySource, source_id)
                assert canonical.last_seen_at == observed_at
                assert canonical.last_verified_at == verified_at
                assert source.last_ingested_at == observed_at
        finally:
            async with AsyncSessionLocal() as db:
                if job_id is not None:
                    await db.execute(delete(AIJob).where(AIJob.id == job_id))
                if source_id is not None:
                    await db.execute(
                        delete(CompanySource).where(CompanySource.id == source_id)
                    )
                if company_id is not None:
                    await db.execute(delete(Company).where(Company.id == company_id))
                await db.commit()

    _run(scenario())


@pytest.mark.parametrize("match_score", [90.0, 42.0])
def test_search_run_completes_when_canonical_job_already_exists(monkeypatch, match_score):
    external_id = "5899549649"
    username = f"ai_search_{uuid4().hex}"
    fetched_job = _job(external_id, title="Fresh provider title", job_hash="fresh-provider-hash")

    async def failing_greenhouse_fetch(**kwargs):
        raise RuntimeError("simulated Greenhouse outage")

    monkeypatch.setattr(services.adzuna_provider, "fetch", lambda **kwargs: asyncio.sleep(0, result=[fetched_job]))
    monkeypatch.setattr(services.greenhouse_provider, "fetch", failing_greenhouse_fetch)
    monkeypatch.setattr(services.lever_provider, "fetch", lambda **kwargs: asyncio.sleep(0, result=[]))
    monkeypatch.setattr(services, "_refresh_company_watch_inventory", lambda: asyncio.sleep(0))
    monkeypatch.setattr(services, "_fetch_stored_company_watch_jobs", lambda db: asyncio.sleep(0, result=([], {})))
    monkeypatch.setattr(services, "classify_resume", lambda profile: {"top_archetypes": ["backend"]})
    monkeypatch.setattr(services, "generate_queries", lambda archetypes: ["Python engineer"])
    monkeypatch.setattr(services, "extract_job_skills", lambda *args, **kwargs: ["Python", "FastAPI", "PostgreSQL"])
    monkeypatch.setattr(
        services,
        "compute_match_score_deterministic",
        lambda *args, **kwargs: {
            "match_score": match_score,
            "match_level": "strong",
            "callback_likelihood": "high",
            "match_reasoning": "Strong test match",
            "strengths": ["Python"],
            "gaps": [],
            "skills_overlap": 95.0,
            "experience_fit": 90.0,
            "role_similarity": 90.0,
            "location_fit": 90.0,
            "industry_fit": 90.0,
            "company_type_fit": 90.0,
            "posting_freshness": 100.0,
        },
    )

    async def scenario():
        user_id = None
        run_id = None
        second_run_id = None
        profile_id = None
        try:
            async with AsyncSessionLocal() as db:
                user = User(
                    username=username,
                    email=f"{username}@example.com",
                    password_hash="test-password-hash",
                )
                db.add(user)
                await db.flush()
                user_id = user.id

                profile = UserResumeProfile(
                    user_id=user.id,
                    raw_resume_text="test",
                    parsed_profile={
                        "skills": ["Python", "FastAPI", "PostgreSQL"],
                        "years_experience": 3.0,
                        "recent_titles": ["Backend Engineer"],
                        "preferred_locations": ["Bengaluru"],
                    },
                    user_preferences={},
                )
                db.add(profile)
                await db.flush()
                profile_id = profile.id

                run = SearchRun(user_id=user.id, profile_version_id=profile.id, status="queued")
                db.add(run)
                existing_job = AIJob(
                    **services._canonical_job_values(
                        _job(external_id, title="Old title", job_hash="different-old-hash"),
                        fetched_job.fetched_at,
                    )
                )
                db.add(existing_job)
                await db.commit()
                run_id = run.id

            await services.run_ai_job_search_task(user_id, run_id)

            async with AsyncSessionLocal() as db:
                completed_run = await db.get(SearchRun, run_id)
                assert completed_run.status == "completed"
                assert completed_run.error_message is None
                assert completed_run.jobs_returned == 1

                canonical_count = await db.scalar(
                    select(func.count(AIJob.id)).where(
                        AIJob.source == "adzuna",
                        AIJob.external_id == external_id,
                    )
                )
                match_count = await db.scalar(
                    select(func.count(AIJobMatch.id)).where(AIJobMatch.search_run_id == run_id)
                )
                assert canonical_count == 1
                assert match_count == 1

            async with AsyncSessionLocal() as db:
                second_run = SearchRun(
                    user_id=user_id,
                    profile_version_id=profile_id,
                    status="queued",
                )
                db.add(second_run)
                await db.commit()
                second_run_id = second_run.id

            await services.run_ai_job_search_task(user_id, second_run_id)

            async with AsyncSessionLocal() as db:
                completed_second_run = await db.get(SearchRun, second_run_id)
                second_run_matches = await db.scalar(
                    select(func.count(AIJobMatch.id)).where(
                        AIJobMatch.search_run_id == second_run_id
                    )
                )
                all_user_matches = await db.scalar(
                    select(func.count(AIJobMatch.id)).where(
                        AIJobMatch.user_id == user_id
                    )
                )
                assert completed_second_run.status == "completed"
                state = await db.scalar(
                    select(UserJobState).where(
                        UserJobState.user_id == user_id,
                        UserJobState.job_id == existing_job.id,
                    )
                )
                assert completed_second_run.jobs_returned == 1
                assert second_run_matches == 1
                assert all_user_matches == 2
                assert state is not None
                assert state.status == "viewed"
                assert state.show_count == 2
        finally:
            async with AsyncSessionLocal() as db:
                if user_id is not None:
                    await db.execute(delete(AIJobMatch).where(AIJobMatch.user_id == user_id))
                    await db.execute(delete(SearchRun).where(SearchRun.user_id == user_id))
                    await db.execute(delete(UserResumeProfile).where(UserResumeProfile.user_id == user_id))
                    await db.execute(delete(User).where(User.id == user_id))
                await db.execute(delete(AIJob).where(AIJob.external_id == external_id))
                await db.commit()

    _run(scenario())
