import asyncio
import hashlib
import selectors
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import BackgroundTasks
from sqlalchemy import select

from app.ai_job_search.models import AIJob, AIJobMatch, SearchRun, UserResumeProfile
from app.ai_job_search.router import get_ai_matched_jobs, list_search_companies, trigger_company_search
from app.ai_job_search.schemas import CompanySearchRequest, NormalizedJobSchema
from app.ai_job_search.services import _fetch_company_directory_jobs, _fetch_stored_company_watch_jobs
from app.company_watch.models import CompanyIntelligence, CompanySource
from app.database.database import AsyncSessionLocal, engine
from app.models.companies import Company
from app.models.users import User


def test_company_results_are_exact_scoped_and_strong_fits_require_experience():
    async def scenario():
        suffix = uuid4().hex
        async with AsyncSessionLocal() as db:
            try:
                user = User(username=f"company_search_{suffix}", email=f"company_search_{suffix}@example.com", password_hash="test")
                companies = [Company(name=f"Alpha {suffix}"), Company(name=f"Alpha Other {suffix}")]
                db.add_all([user, *companies])
                await db.flush()
                profile = UserResumeProfile(
                    user_id=user.id,
                    parsed_profile={"skills": ["Python"], "years_experience": 2},
                    user_preferences={"experience_min_years": 1, "experience_max_years": 2},
                )
                db.add(profile)
                for company in companies:
                    db.add(CompanyIntelligence(company_id=company.id, discovery_status="source_verified"))
                await db.flush()
                sources = [CompanySource(
                    company_id=company.id, provider="greenhouse", identifier=f"test-{index}-{suffix}",
                    source_url=f"https://boards.greenhouse.io/test-{index}-{suffix}",
                    status="healthy", last_verified_at=datetime.utcnow(),
                ) for index, company in enumerate(companies)]
                db.add_all(sources)
                await db.flush()
                now = datetime.utcnow()
                broad_run = SearchRun(user_id=user.id, profile_version_id=profile.id, search_scope="general", status="completed", started_at=now - timedelta(minutes=2))
                company_run = SearchRun(user_id=user.id, profile_version_id=profile.id, search_scope="company", company_id=companies[0].id, status="completed", started_at=now)
                db.add_all([broad_run, company_run])
                await db.flush()
                jobs = []
                for index, source in enumerate([sources[0], sources[0], sources[1]]):
                    job = AIJob(
                        job_hash=hashlib.sha256(f"{suffix}-{index}".encode()).hexdigest(),
                        source="greenhouse", external_id=f"{suffix}-{index}",
                        title="Python Engineer", company=companies[0].name if index < 2 else companies[1].name,
                        location="Bengaluru", description="Python engineering role",
                        description_completeness="full", experience_parse_version=1,
                        required_experience_min=1 if index != 1 else None,
                        required_experience_max=2 if index != 1 else None,
                        experience_source="description" if index != 1 else "unknown",
                        experience_confidence=0.9 if index != 1 else 0,
                        apply_url=f"https://example.com/{suffix}/{index}",
                        ingestion_source_id=source.id,
                    )
                    db.add(job)
                    jobs.append(job)
                directory_job = AIJob(
                    job_hash=hashlib.sha256(f"{suffix}-directory".encode()).hexdigest(),
                    source="adzuna", external_id=f"{suffix}-directory",
                    title="Python Engineer", company=companies[0].name,
                    location="Bengaluru", description="Python role",
                    description_completeness="snippet",
                    apply_url=f"https://example.com/{suffix}/directory",
                )
                db.add(directory_job)
                await db.flush()
                for index, job in enumerate(jobs):
                    db.add(AIJobMatch(
                        user_id=user.id, job_id=job.id,
                        search_run_id=company_run.id if index < 2 else broad_run.id,
                        match_score=91, created_at=now,
                    ))
                db.add(AIJobMatch(
                    user_id=user.id, job_id=directory_job.id,
                    search_run_id=company_run.id, match_score=92, created_at=now,
                ))
                await db.flush()

                companies_response = await list_search_companies(current_user=user, db=db)
                assert next(item for item in companies_response if item["id"] == companies[0].id)["fetchable"] is True
                corpus, _ = await _fetch_stored_company_watch_jobs(db, company_id=companies[0].id)
                assert {job.external_id for job in corpus} == {jobs[0].external_id, jobs[1].external_id}

                async def cards(view, qualified=False):
                    return await get_ai_matched_jobs(
                        view=view, industry=None, company_type=None, company_name=None,
                        company_id=companies[0].id, qualified_only=qualified,
                        min_score=60, min_salary=None, remote_only=False,
                        sort_by="relevance", offset=0, limit=20,
                        current_user=user, db=db,
                    )

                assert {card.job_id for card in await cards("company")} == {jobs[0].id, jobs[1].id, directory_job.id}
                assert [card.job_id for card in await cards("company", True)] == [jobs[0].id]
                assert [card.job_id for card in await cards("new")] == [jobs[2].id]
            finally:
                await db.rollback()

    async def run():
        try:
            await scenario()
        finally:
            await engine.dispose()

    with asyncio.Runner(loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())) as runner:
        runner.run(run())


def test_directory_fallback_accepts_only_exact_company_or_alias(monkeypatch):
    calls = []

    async def fake_fetch(**kwargs):
        calls.append(kwargs)
        return [
            NormalizedJobSchema(
                job_hash=str(index), source="adzuna", external_id=str(index),
                title="Engineer", company=name, location="Bengaluru",
                apply_url=f"https://example.com/{index}",
            )
            for index, name in enumerate(("Ather Energy", "Ather Energy Pvt Ltd", "Ather Technologies", "Ather Energy Staffing"))
        ]

    monkeypatch.setattr("app.ai_job_search.services.adzuna_provider.fetch", fake_fetch)

    async def run():
        company = Company(name="Ather Energy")
        jobs = await _fetch_company_directory_jobs(company, [], ["India"])
        assert [job.company for job in jobs] == ["Ather Energy", "Ather Energy Pvt Ltd"]
        assert calls[0]["pages"] == 2
        assert calls[0]["concurrency"] == 2

    asyncio.run(run())


def test_registered_company_without_verified_source_can_start_directory_search(monkeypatch):
    monkeypatch.setattr("app.ai_job_search.router.settings.ADZUNA_APP_ID", "test-id")
    monkeypatch.setattr("app.ai_job_search.router.settings.ADZUNA_APP_KEY", "test-key")

    async def scenario():
        suffix = uuid4().hex
        user_id = company_id = None
        try:
            async with AsyncSessionLocal() as db:
                user = User(username=f"directory_{suffix}", email=f"directory_{suffix}@example.com", password_hash="test")
                company = Company(name=f"Directory Only {suffix}", website="https://example.com")
                db.add_all([user, company])
                await db.flush()
                user_id, company_id = user.id, company.id
                db.add(UserResumeProfile(user_id=user.id, parsed_profile={"skills": ["Python"]}, user_preferences={}))
                db.add(CompanyIntelligence(company_id=company.id, discovery_status="discovery_failed"))
                await db.commit()

                tasks = BackgroundTasks()
                run = await trigger_company_search(
                    CompanySearchRequest(company_id=company.id), tasks,
                    current_user=user, db=db,
                )
                assert run.search_scope == "company"
                assert run.company_id == company.id
                assert len(tasks.tasks) == 1
        finally:
            async with AsyncSessionLocal() as db:
                from sqlalchemy import delete

                if user_id is not None:
                    await db.execute(delete(SearchRun).where(SearchRun.user_id == user_id))
                    await db.execute(delete(UserResumeProfile).where(UserResumeProfile.user_id == user_id))
                    await db.execute(delete(User).where(User.id == user_id))
                if company_id is not None:
                    await db.execute(delete(CompanyIntelligence).where(CompanyIntelligence.company_id == company_id))
                    await db.execute(delete(Company).where(Company.id == company_id))
                await db.commit()

    async def run():
        try:
            await scenario()
        finally:
            await engine.dispose()

    with asyncio.Runner(loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())) as runner:
        runner.run(run())
