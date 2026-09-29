import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select

from app.ai_job_search import services as search
from app.ai_job_search.models import AIJob
from app.company_watch import service
from app.company_watch.models import CompanyAlias, CompanyIntelligence, CompanyLocation, CompanySource, CompanyWatchRun
from app.company_watch.providers import get_adapter, source_url
from app.company_watch.registry import RegistryDocument, canonicalize_registry, load_registry, register_companies
from app.database.database import AsyncSessionLocal
from app.models.companies import Company
from tests.unit.test_company_watch_service import _run


def _ashby_job(**updates):
    posting = "d3037ac5-cb98-4be0-b3c8-fb608c9ef135"
    item = {
        "title": "Software Engineer",
        "location": "Bengaluru",
        "address": {"postalAddress": {"addressCountry": "IND", "addressLocality": "Bengaluru"}},
        "isListed": True,
        "isRemote": False,
        "jobUrl": f"https://jobs.ashbyhq.com/example/{posting}",
        "applyUrl": f"https://jobs.ashbyhq.com/example/{posting}/application",
        "descriptionPlain": "Python FastAPI PostgreSQL",
        "publishedAt": "2026-09-01T10:00:00Z",
    }
    item.update(updates)
    return item


def _claimed(provider="ashby", identifier="example"):
    return service.ClaimedSource(1, 1, "Example", provider, identifier, source_url(provider, identifier), "token")


async def _cleanup(companies, runs=()):
    async with AsyncSessionLocal() as db:
        sources = select(CompanySource.id).where(CompanySource.company_id.in_(companies))
        await db.execute(delete(AIJob).where(AIJob.ingestion_source_id.in_(sources)))
        await db.execute(delete(Company).where(Company.id.in_(companies)))
        if runs:
            await db.execute(delete(CompanyWatchRun).where(CompanyWatchRun.id.in_(runs)))
        await db.commit()


def test_bootstrap_consumes_all_groups_and_three_providers():
    document = load_registry()
    by_name = {company.name: company for company in document.companies}
    assert len(by_name) == 152
    assert set(by_name["NVIDIA"].categories) == {"big_tech", "semiconductor"}
    assert set(by_name["Cisco"].categories) == {"big_tech", "networking"}
    assert by_name["Google"].sources == []
    assert by_name["Walmart Global Tech"].sources == []
    assert {source.provider for company in document.companies for source in company.sources} == {"greenhouse", "lever", "ashby"}


@pytest.mark.parametrize("companies", [
    [{"name": "One", "aliases": ["Two"]}, {"name": "Two"}],
    [{"name": "One", "sources": [{"provider": "lever", "identifier": "shared"}]},
     {"name": "Two", "sources": [{"provider": "lever", "identifier": "shared"}]}],
    [{"name": "One", "sources": [{"provider": "lever", "identifier": "one", "source_url": "https://example.com/jobs"}]}],
])
def test_ambiguous_identity_or_source_is_rejected_before_import(companies):
    with pytest.raises(ValueError):
        canonicalize_registry(RegistryDocument(companies=companies))


def test_registration_deduplicates_merges_categories_preserves_health_and_manual_metadata():
    async def scenario():
        suffix = uuid4().hex
        name = f"Registry NVIDIA {suffix}"
        companies = []
        document = RegistryDocument(companies=[
            {"name": name, "categories": ["big_tech"], "website_url": "https://example.com", "careers_url": "https://example.com/careers", "aliases": [f"Registry NV {suffix}"], "office_locations": [{"country": "India", "region": "Karnataka", "city": "Bengaluru"}], "sources": [{"provider": "greenhouse", "identifier": suffix}]},
            {"name": name.lower(), "categories": ["semiconductor"]},
            {"name": f"Registry Lever {suffix}", "sources": [{"provider": "lever", "identifier": suffix}]},
            {"name": f"Registry Ashby {suffix}", "sources": [{"provider": "ashby", "identifier": suffix}]},
            {"name": f"Registry Pending {suffix}", "categories": ["gcc"]},
        ])
        try:
            async with AsyncSessionLocal() as db:
                first = await register_companies(db, document)
                assert first == {"registered_companies": 4, "new_companies": 4, "new_sources": 3, "configured_sources": 3, "discovery_pending": 1}
                rows = (await db.execute(select(Company).where(Company.name.like(f"%{suffix}")))).scalars().all()
                companies.extend(row.id for row in rows)
                canonical = next(row for row in rows if row.name == name)
                metadata = await db.get(CompanyIntelligence, canonical.id)
                assert set(metadata.tags) == {"big_tech", "semiconductor"}
                assert metadata.careers_url == "https://example.com/careers"
                assert metadata.india_hiring is False
                canonical.website = "https://manual.example.com"
                metadata.tags = [*metadata.tags, "manual_tag"]
                source = await db.scalar(select(CompanySource).where(CompanySource.company_id == canonical.id))
                source.status = "healthy"
                source.last_success_at = datetime.utcnow()
                source.next_check_at = datetime.utcnow() + timedelta(days=1)
                next_check = source.next_check_at
                await db.commit()
            async with AsyncSessionLocal() as db:
                second = await register_companies(db, document)
                assert second["new_companies"] == second["new_sources"] == 0
                canonical = await db.get(Company, canonical.id)
                assert canonical.website == "https://manual.example.com"
                metadata = await db.get(CompanyIntelligence, canonical.id)
                assert "manual_tag" in metadata.tags
                source = await db.get(CompanySource, source.id)
                assert source.status == "healthy" and source.last_success_at is not None
                assert source.next_check_at == next_check
                aliases = (await db.execute(select(CompanyAlias).where(CompanyAlias.company_id == canonical.id))).scalars().all()
                assert len(aliases) == 2
                offices = (await db.execute(select(CompanyLocation).where(CompanyLocation.company_id == canonical.id))).scalars().all()
                assert len(offices) == 1 and offices[0].city == "Bengaluru"
            statuses = [row for row in await service.source_health_status() if row["company_id"] in companies]
            assert sum(row["status"] == "needs_careers_url" for row in statuses) == 1
            assert sum(row["fetchable"] for row in statuses) == 1
        finally:
            await _cleanup(companies)
    _run(scenario())


@pytest.mark.parametrize("item,target,eligible", [
    (_ashby_job(), "Bengaluru", True),
    (_ashby_job(), "Gurugram", False),
    (_ashby_job(location="Gurgaon", address={"postalAddress": {"addressCountry": "India"}}), "Gurugram", True),
    (_ashby_job(location="Delhi / Noida", address={"postalAddress": {"addressCountry": "India"}}), "Gurugram", False),
    (_ashby_job(location="India", address={"postalAddress": {"addressCountry": "India"}}), "Bengaluru", False),
    (_ashby_job(location="India", isRemote=True), "Gurugram", True),
    (_ashby_job(location="New York", address={"postalAddress": {"addressCountry": "USA"}}, isRemote=True), "Gurugram", False),
    (_ashby_job(location="New York", address={"postalAddress": {"addressCountry": "USA"}}, secondaryLocations=[{"location": "Gurgaon", "address": {"addressCountry": "India"}}]), "Gurugram", True),
])
def test_ashby_geography_uses_posting_locations_not_offices(item, target, eligible):
    job = get_adapter("ashby").normalize("Example", "example", item)
    assert bool(job and search._matches_target_locations(job, [target])) is eligible


def test_ashby_identity_visibility_compensation_and_normalized_schema():
    adapter = get_adapter("ashby")
    item = _ashby_job(compensation={"summaryComponents": [{"compensationType": "Salary", "currencyCode": "INR", "interval": "1 YEAR", "minValue": 1000000, "maxValue": 2000000}]})
    job = adapter.normalize("Example", "example", item)
    assert job.source == "ashby" and job.external_id.startswith("example_")
    assert job.salary_min == 1000000 and job.salary_currency == "INR"
    assert job.salary_interval == "annual" and job.posted_date == datetime(2026, 9, 1, 10)
    assert adapter.normalize("Example", "example", _ashby_job(title="Updated title")).external_id == job.external_id
    assert adapter.normalize("Example", "example", _ashby_job(isListed=False)) is None


@pytest.mark.parametrize("payload", [{}, {"jobs": None}, {"jobs": [None]}, {"jobs": [_ashby_job(), _ashby_job()]}, {"jobs": [_ashby_job(jobUrl="https://jobs.ashbyhq.com/another/not-a-posting")]}])
def test_ashby_malformed_snapshot_never_allows_deactivation(payload):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))) as client:
            result = await service._ingest_one(client, asyncio.Semaphore(1), _claimed())
        assert result.snapshot_complete is False
        assert result.source_result.status == "temporary_failure"
    asyncio.run(scenario())


def test_ashby_complete_empty_and_nontechnical_snapshots():
    async def scenario():
        for jobs in ([], [_ashby_job(title="Account Manager")], [_ashby_job(isListed=False)]):
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"jobs": jobs}))) as client:
                result = await service._ingest_one(client, asyncio.Semaphore(1), _claimed())
            assert result.snapshot_complete is True and result.jobs == ()
    asyncio.run(scenario())


def test_unsupported_provider_is_skipped_without_http():
    async def scenario():
        claimed = service.ClaimedSource(1, 1, "Unsupported", "icims", "example", "https://example.com/jobs", "token")
        def handler(request):
            pytest.fail("Unsupported providers must not make requests")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await service._ingest_one(client, asyncio.Semaphore(1), claimed)
        assert result.source_result.status == "unsupported"
    asyncio.run(scenario())


def test_ingestion_claims_require_verification_and_exclude_unsupported_stale_and_busy():
    async def scenario():
        suffix = uuid4().hex
        companies, ids, runs = [], [], []
        try:
            async with AsyncSessionLocal() as db:
                for index, (provider, status, verified, busy) in enumerate([
                    ("greenhouse", "healthy", True, False),
                    ("lever", "unverified", False, False),
                    ("ashby", "healthy", True, False),
                    ("workday", "unsupported", True, False),
                    ("greenhouse", "stale", True, False),
                    ("lever", "healthy", True, True),
                ]):
                    company = Company(name=f"Eligibility {index} {suffix}")
                    db.add(company)
                    await db.flush()
                    companies.append(company.id)
                    source = CompanySource(company_id=company.id, provider=provider, identifier=f"test-{index}-{suffix}", source_url="https://example.com/jobs", status=status, last_success_at=datetime.utcnow() if verified else None, claimed_until=datetime.utcnow() + timedelta(minutes=5) if busy else None)
                    db.add(source)
                    await db.flush()
                    ids.append(source.id)
                await db.commit()
            first, second = await asyncio.gather(
                service._claim_due_sources(10, force=True, run_type="ingest", source_ids=ids),
                service._claim_due_sources(10, force=True, run_type="ingest", source_ids=ids),
            )
            runs.extend([first[0], second[0]])
            assert {source.id for source in [*first[1], *second[1]]} == {ids[0], ids[2]}
            assert len(first[1]) + len(second[1]) == 2
        finally:
            await _cleanup(companies, runs)
    _run(scenario())


def test_ashby_db_ingestion_search_retrieval_failure_isolation_and_no_duplicate_fetch(monkeypatch):
    async def scenario():
        suffix = uuid4().hex
        companies, ids, runs, requests = [], [], [], []
        original_client = httpx.AsyncClient
        def handler(request):
            requests.append(str(request.url))
            if request.url.host == "boards-api.greenhouse.io":
                return httpx.Response(503)
            item = _ashby_job()
            item["jobUrl"] = item["jobUrl"].replace("/example/", f"/{suffix}/")
            item["applyUrl"] = item["applyUrl"].replace("/example/", f"/{suffix}/")
            return httpx.Response(200, json={"jobs": [item]})
        monkeypatch.setattr(service, "public_client", lambda: original_client(transport=httpx.MockTransport(handler)))
        try:
            async with AsyncSessionLocal() as db:
                for provider in ("greenhouse", "ashby"):
                    company = Company(name=f"Ingest {provider} {suffix}")
                    db.add(company)
                    await db.flush()
                    companies.append(company.id)
                    source = CompanySource(company_id=company.id, provider=provider, identifier=suffix, source_url=source_url(provider, suffix), status="healthy" if provider == "greenhouse" else "unverified", last_success_at=datetime.utcnow() if provider == "greenhouse" else None)
                    db.add(source)
                    await db.flush()
                    ids.append(source.id)
                await db.commit()
            pending = await service.ingest_due_sources(source_ids=[ids[1]])
            runs.append(pending["run_id"])
            assert pending["claimed"] == 0 and requests == []
            verified = await service.verify_due_sources(source_ids=[ids[1]])
            runs.append(verified["run_id"])
            assert verified["successful"] == 1
            result = await service.ingest_due_sources(source_ids=ids)
            runs.append(result["run_id"])
            assert (result["claimed"], result["successful"], result["failed"], result["inserted"]) == (2, 1, 1, 1)
            count = len(requests)
            second = await service.ingest_due_sources(source_ids=ids)
            runs.append(second["run_id"])
            assert second["claimed"] == 0 and len(requests) == count
            async with AsyncSessionLocal() as db:
                jobs, keys = await search._fetch_stored_company_watch_jobs(db)
                found = [job for job in jobs if job.source == "ashby" and job.external_id.startswith(suffix)]
                assert len(found) == 1 and ("ashby", found[0].external_id) in keys
                source = await db.get(CompanySource, ids[1])
                observed_at = source.last_ingested_at
                assert observed_at is not None
                assert source.last_success_at == source.last_verified_at == observed_at
        finally:
            await _cleanup(companies, runs)
    _run(scenario())


def test_failed_verification_never_fabricates_or_advances_success_evidence(monkeypatch):
    async def scenario():
        suffix = uuid4().hex
        companies, runs = [], []
        original_client = httpx.AsyncClient
        valid = False
        def handler(request):
            item = _ashby_job()
            item["jobUrl"] = item["jobUrl"].replace("/example/", f"/{suffix}/")
            item["applyUrl"] = item["applyUrl"].replace("/example/", f"/{suffix}/")
            return httpx.Response(200, json={"jobs": [item]} if valid else {})
        monkeypatch.setattr(service, "public_client", lambda: original_client(transport=httpx.MockTransport(handler)))
        try:
            async with AsyncSessionLocal() as db:
                company = Company(name=f"Verification {suffix}")
                db.add(company)
                await db.flush()
                companies.append(company.id)
                source = CompanySource(company_id=company.id, provider="ashby", identifier=suffix, source_url=source_url("ashby", suffix))
                db.add(source)
                await db.commit()
                source_id = source.id
            for valid in (False, True, False):
                result = await service.verify_due_sources(force=True, source_ids=[source_id])
                runs.append(result["run_id"])
                async with AsyncSessionLocal() as db:
                    source = await db.get(CompanySource, source_id)
                    if len(runs) == 1:
                        assert source.last_success_at is source.last_verified_at is None
                    elif len(runs) == 2:
                        evidence = source.last_success_at
                        assert evidence is not None and source.last_verified_at == evidence
                    else:
                        assert source.last_success_at == source.last_verified_at == evidence
                        assert source.status == "temporary_failure"
        finally:
            await _cleanup(companies, runs)
    _run(scenario())


def test_expired_heartbeat_cannot_revive_a_lease(monkeypatch):
    async def scenario():
        suffix = uuid4().hex
        companies, runs = [], []
        stop = asyncio.Event()
        heartbeat = None
        monkeypatch.setattr(service, "LEASE_HEARTBEAT_SECONDS", 0.01)
        try:
            expired_at = datetime.utcnow() - timedelta(minutes=1)
            async with AsyncSessionLocal() as db:
                company = Company(name=f"Expired lease {suffix}")
                db.add(company)
                await db.flush()
                companies.append(company.id)
                source = CompanySource(company_id=company.id, provider="greenhouse", identifier=suffix, source_url=source_url("greenhouse", suffix), status="healthy", last_success_at=datetime.utcnow(), claim_token="expired", claimed_until=expired_at)
                db.add(source)
                await db.commit()
                claim = service.ClaimedSource(source.id, company.id, company.name, source.provider, source.identifier, source.source_url, "expired")
            heartbeat = asyncio.create_task(service._renew_claims_until_stopped([claim], stop))
            await asyncio.sleep(0.1)
            stop.set()
            await heartbeat
            async with AsyncSessionLocal() as db:
                source = await db.get(CompanySource, claim.id)
                assert source.claimed_until == expired_at
            recovered = await service._claim_due_sources(1, run_type="ingest", source_ids=[claim.id])
            runs.append(recovered[0])
            assert len(recovered[1]) == 1 and recovered[1][0].claim_token != "expired"
        finally:
            stop.set()
            if heartbeat is not None:
                await heartbeat
            await _cleanup(companies, runs)
    _run(scenario())
