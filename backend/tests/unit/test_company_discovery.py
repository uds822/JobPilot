import asyncio
import hashlib
import socket
from datetime import datetime, timedelta
from uuid import uuid4

import httpcore
import httpx
import pytest
from sqlalchemy import delete, select

from app.ai_job_search.models import AIJob
from app.ai_job_search.schemas import NormalizedJobSchema
from app.company_watch import discovery, service
from app.company_watch.detection import Candidate, canonical_url, detect_url, inspect_page
from app.company_watch.http import PublicNetworkBackend, RequestBudget, request_public, validate_destination
from app.company_watch.models import CompanyDiscoveryAttempt, CompanyIntelligence, CompanySource, CompanyWatchRun
from app.company_watch.providers import get_adapter
from app.company_watch.registry import RegistryDocument, register_companies
from app.database.database import AsyncSessionLocal
from app.models.companies import Company
from tests.unit.test_company_watch_service import _run


@pytest.mark.parametrize("url,provider,identifier", [
    ("https://job-boards.greenhouse.io/example", "greenhouse", "example"),
    ("https://boards.greenhouse.io/embed/job_board?for=example", "greenhouse", "example"),
    ("https://jobs.lever.co/example/123", "lever", "example"),
    ("https://jobs.ashbyhq.com/example", "ashby", "example"),
    ("https://example.wd5.myworkdayjobs.com/en-US/External/job/id", "workday", "example.wd5.myworkdayjobs.com:example:External"),
    ("https://jobs.smartrecruiters.com/BoschGroup", "smartrecruiters", "BoschGroup"),
    ("https://careers.example.icims.com/jobs/search", "icims", None),
    ("https://jobs.jobvite.com/example", "jobvite", None),
    ("https://example.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1", "oracle", None),
    ("https://example.successfactors.com/career", "successfactors", None),
    ("https://nvidia.eightfold.ai/careers", "eightfold", "nvidia.eightfold.ai"),
    ("https://www.google.com/about/careers/applications/", "google", "google"),
])
def test_evidence_based_detection(url, provider, identifier):
    result = detect_url(url)
    assert result.provider == provider
    if identifier:
        assert result.identifier == identifier


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://127.0.0.1", "http://169.254.169.254/latest", "http://[::1]/", "http://localhost", "https://example.local", "https://user:pass@example.com/", "https://example.com:8080/", "http://10.0.0.1"])
def test_unsafe_destinations_are_blocked(url):
    with pytest.raises(ValueError):
        validate_destination(url)


def test_redirect_validation_and_response_budget():
    async def scenario():
        seen = []
        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ValueError):
                await request_public(client, "https://example.com/careers")
        assert len(seen) == 1
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="abcdef"))) as client:
            with pytest.raises(ValueError, match="page-size"):
                await request_public(client, "https://example.com", budget=RequestBudget(max_bytes=3))
    asyncio.run(scenario())


def test_compressed_pages_are_decoded_exactly_once():
    async def scenario():
        import gzip
        def handler(request):
            return httpx.Response(200, content=gzip.compress(b"careers page"), headers={"content-encoding": "gzip"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response = await request_public(client, "https://example.com")
        assert response.text == "careers page"
    asyncio.run(scenario())


def test_private_dns_answers_are_blocked_at_connection(monkeypatch):
    async def scenario():
        async def resolve(*args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443))]
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
        with pytest.raises(httpcore.ConnectError, match="nonpublic"):
            await PublicNetworkBackend().connect_tcp("example.com", 443)
    asyncio.run(scenario())


def test_connection_uses_checked_ip_without_second_hostname_resolution(monkeypatch):
    async def scenario():
        from httpcore._backends.auto import AutoBackend
        connected = []
        async def resolve(*args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
        async def connect(self, host, port, *args, **kwargs):
            connected.append((host, port))
            return "stream"
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
        monkeypatch.setattr(AutoBackend, "connect_tcp", connect)
        assert await PublicNetworkBackend().connect_tcp("example.com", 443) == "stream"
        assert connected == [("8.8.8.8", 443)]
    asyncio.run(scenario())


def test_request_budget_stops_unbounded_redirects():
    async def scenario():
        count = 0
        def handler(request):
            nonlocal count
            count += 1
            return httpx.Response(302, headers={"location": f"/next/{count}"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ValueError, match="budget"):
                await request_public(client, "https://example.com", budget=RequestBudget(remaining=2))
        assert count == 2
    asyncio.run(scenario())


def test_no_provider_guessing_and_url_canonicalization():
    assert detect_url("https://google-fake.example.com/careers") is None
    assert canonical_url("https://EXAMPLE.com/jobs?b=2&utm_source=test&a=1#fragment") == "https://example.com/jobs?a=1&b=2"
    sources, _, _ = inspect_page('<iframe src="https://jobs.lever.co/Example"></iframe>', "https://example.com/careers")
    assert sources[0].identity == "lever:example"
    _, links, _ = inspect_page('<a href="https://news.example.com/challenges-and-opportunities">Challenges and opportunities</a>', "https://example.com")
    assert links == []
    _, links, _ = inspect_page('<a href="https://news.example.com/an-assistant-will-do-the-job-in-10-minutes">AI will do the job</a>', "https://example.com")
    assert links == []


def test_unreachable_careers_link_is_not_saved_as_discovered_url():
    async def scenario():
        def handler(request):
            if request.url.path == "/":
                return httpx.Response(200, text='<a href="/careers">Careers</a>')
            return httpx.Response(403)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await discovery.inspect_company(client, discovery.ClaimedCompany(1, "Example", None, "https://example.com/", "token"), asyncio.Semaphore(1), {})
        assert result.careers_url is None and result.candidates == ()
    asyncio.run(scenario())


def test_discovery_company_failure_does_not_abort_other_companies(monkeypatch):
    async def scenario():
        claims = [discovery.ClaimedCompany(index, "Example", "https://example.com/careers", None, str(index)) for index in (1, 2)]
        async def claim(*args, **kwargs):
            return claims
        async def inspect(client, company, *args):
            return discovery.DiscoveryResult(company, error="No source")
        async def record(result):
            if result.company.id == 1:
                raise RuntimeError("Persistence unavailable")
            return {"status": "discovery_failed", "source_ids": []}
        monkeypatch.setattr(discovery, "claim_due_companies", claim)
        monkeypatch.setattr(discovery, "inspect_company", inspect)
        monkeypatch.setattr(discovery, "record_discovery", record)
        result = await discovery.discover_due_companies()
        assert result["claimed"] == result["failed"] == 2
    asyncio.run(scenario())


def google_page(total=1, next_page=False, organization="Google", identity="123", title="Software Engineer"):
    next_link = '<a aria-label="Go to next page" href="?location=India&page=2"></a>' if next_page else ""
    return f'<div class="rZt9ff"><span class="SWhIm">{total}</span> jobs matched</div><ul><li><h3>{title}</h3><span class="RP7SMd">corporate_fare {organization}</span><span class="r0wTof">Gurugram, Haryana, India</span><div class="Xsxa1e">Python PostgreSQL</div><a href="jobs/results/{identity}-software-engineer"></a></li></ul>{next_link}'


def claimed(provider, url, identifier="example", company="Example"):
    return service.ClaimedSource(1, 1, company, provider, identifier, url, "token")


def test_google_pagination_failure_retains_observed_jobs_and_scope():
    async def scenario():
        def handler(request):
            return httpx.Response(503) if "page=2" in str(request.url) else httpx.Response(200, text=google_page(total=2, next_page=True))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await service._ingest_one(client, asyncio.Semaphore(1), claimed("google", "https://www.google.com/about/careers/applications/", "google", "Google"))
        assert result.snapshot_complete is False and len(result.jobs) == 1
        assert result.inventory_scope == "india_technical_v1" and result.source_result.status == "partial"
    asyncio.run(scenario())


def test_google_complete_pagination_stable_identity_and_subsidiary_filter():
    async def scenario():
        current_title = "Software Engineer"
        def handler(request):
            return httpx.Response(200, text=google_page(title=current_title))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            source = claimed("google", "https://www.google.com/about/careers/applications/", "google", "Google")
            first = await service._ingest_one(client, asyncio.Semaphore(1), source)
            current_title = "Software Engineer II"
            second = await service._ingest_one(client, asyncio.Semaphore(1), source)
        assert first.snapshot_complete and first.jobs[0].external_id == second.jobs[0].external_id
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=google_page(organization="YouTube")))) as client:
            result = await service._ingest_one(client, asyncio.Semaphore(1), source)
        assert result.jobs == ()
    asyncio.run(scenario())


def test_google_layout_failure_is_not_an_empty_inventory():
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="Sign in"))) as client:
            result = await service._ingest_one(client, asyncio.Semaphore(1), claimed("google", "https://www.google.com/about/careers/applications/", "google", "Google"))
        assert not result.snapshot_complete and result.source_result.status == "temporary_failure"
    asyncio.run(scenario())


def test_smartrecruiters_pagination_partial_and_complete():
    async def scenario():
        fail = True
        def handler(request):
            offset = int(request.url.params["offset"])
            if offset and fail:
                return httpx.Response(429)
            item = {"id": str(offset + 1), "name": "Software Engineer", "location": {"city": "Gurgaon", "country": "in"}}
            return httpx.Response(200, json={"totalFound": 2, "content": [item]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            source = claimed("smartrecruiters", "https://jobs.smartrecruiters.com/Example")
            partial = await service._ingest_one(client, asyncio.Semaphore(1), source)
            fail = False
            complete = await service._ingest_one(client, asyncio.Semaphore(1), source)
        assert not partial.snapshot_complete and len(partial.jobs) == 1
        assert complete.snapshot_complete and len(complete.jobs) == 2
    asyncio.run(scenario())


def test_workday_uses_country_facet_and_stable_requisition_id():
    async def scenario():
        paths = []
        def handler(request):
            import json
            body = json.loads(request.content)
            paths.append(body)
            if not body["appliedFacets"]:
                return httpx.Response(200, json={"facets": [{"facetParameter": "country", "values": [{"descriptor": "India", "id": "in"}]}]})
            return httpx.Response(200, json={"total": 1, "jobPostings": [{"title": "Software Engineer", "externalPath": "/job/India/Engineer_JR1", "bulletFields": ["JR1"], "locationsText": "2 Locations"}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await service._ingest_one(client, asyncio.Semaphore(1), claimed("workday", "https://example.wd5.myworkdayjobs.com/External", "example.wd5.myworkdayjobs.com:example:External"))
        assert result.snapshot_complete and result.jobs[0].location == "India"
        assert paths[1]["appliedFacets"] == {"country": ["in"]}
    asyncio.run(scenario())


def test_workday_later_page_zero_total_does_not_mean_empty_inventory():
    async def scenario():
        import json
        def handler(request):
            body = json.loads(request.content)
            offset = body["offset"]
            return httpx.Response(200, json={"total": 2 if offset == 0 else 0, "jobPostings": [{"title": "Software Engineer", "externalPath": f"/job/India/Engineer_JR{offset}", "bulletFields": [f"JR{offset}"], "locationsText": "Bengaluru, India"}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await service._ingest_one(client, asyncio.Semaphore(1), claimed("workday", "https://example.wd5.myworkdayjobs.com/External", "example.wd5.myworkdayjobs.com:example:External"))
        assert result.snapshot_complete and len(result.jobs) == 2
    asyncio.run(scenario())


def test_structured_job_pages_are_partial_and_owner_checked():
    async def scenario():
        import json
        item = {"@type": "JobPosting", "title": "Software Engineer", "identifier": {"value": "one"}, "url": "https://example.com/jobs/one", "description": "Python", "hiringOrganization": {"name": "Example"}, "jobLocation": {"address": {"addressLocality": "Gurugram", "addressCountry": "IN"}}}
        def handler(request):
            return httpx.Response(200, text=f'<script type="application/ld+json">{json.dumps(item)}</script>')
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await service._ingest_one(client, asyncio.Semaphore(1), claimed("direct_html", "https://example.com/careers"))
            item["hiringOrganization"]["name"] = "Another Employer"
            rejected = await service._ingest_one(client, asyncio.Semaphore(1), claimed("direct_html", "https://example.com/careers"))
        assert not result.snapshot_complete and len(result.jobs) == 1 and result.source_result.status == "partial"
        assert rejected.jobs == () and rejected.source_result.status == "temporary_failure"
    asyncio.run(scenario())


async def cleanup(company_ids, run_ids=()):
    async with AsyncSessionLocal() as db:
        ids = select(CompanySource.id).where(CompanySource.company_id.in_(company_ids))
        await db.execute(delete(AIJob).where(AIJob.ingestion_source_id.in_(ids)))
        await db.execute(delete(Company).where(Company.id.in_(company_ids)))
        if run_ids:
            await db.execute(delete(CompanyWatchRun).where(CompanyWatchRun.id.in_(run_ids)))
        await db.commit()


def test_broken_source_rediscovery_and_missing_url_state():
    async def scenario():
        suffix, companies = uuid4().hex, []
        try:
            async with AsyncSessionLocal() as db:
                await register_companies(db, RegistryDocument(companies=[{"name": f"Broken {suffix}", "careers_url": "https://example.com/careers", "sources": [{"provider": "lever", "identifier": suffix}]}, {"name": f"No URL {suffix}"}]))
                rows = list((await db.execute(select(Company).where(Company.name.like(f"%{suffix}")))).scalars())
                companies.extend(row.id for row in rows)
                broken = next(row for row in rows if row.name.startswith("Broken"))
                no_url = next(row for row in rows if row.name.startswith("No URL"))
                source = await db.scalar(select(CompanySource).where(CompanySource.company_id == broken.id))
                source.status, source.last_success_at = "healthy", datetime.utcnow()
                await db.commit()
            assert await discovery.claim_due_companies(company_ids=companies) == []
            async with AsyncSessionLocal() as db:
                source = await db.get(CompanySource, source.id)
                source.status = "stale"
                metadata = await db.get(CompanyIntelligence, no_url.id)
                assert metadata.discovery_status == "needs_careers_url"
                await db.commit()
            claims = await discovery.claim_due_companies(company_ids=companies)
            assert len(claims) == 1 and claims[0].id == broken.id
        finally:
            await cleanup(companies)
    _run(scenario())


def test_website_discovery_validation_ingestion_and_duplicate_prevention(monkeypatch):
    async def scenario():
        suffix, companies, runs = uuid4().hex, [], []
        original = httpx.AsyncClient
        requests = []
        def handler(request):
            requests.append(str(request.url))
            if request.url.host == "example.com":
                html = '<a href="/careers">Careers</a>' if request.url.path == "/" else f'<a href="https://jobs.lever.co/{suffix}">Open jobs</a>'
                return httpx.Response(200, text=html)
            return httpx.Response(200, json=[{"id": "one", "text": "Software Engineer", "categories": {"location": "Gurgaon, India"}, "descriptionPlain": "Python", "hostedUrl": f"https://jobs.lever.co/{suffix}/one", "applyUrl": f"https://jobs.lever.co/{suffix}/one/apply"}])
        factory = lambda: original(transport=httpx.MockTransport(handler))
        monkeypatch.setattr(discovery, "public_client", factory)
        monkeypatch.setattr(service, "public_client", factory)
        try:
            async with AsyncSessionLocal() as db:
                await register_companies(db, RegistryDocument(companies=[{"name": f"Website {suffix}", "website_url": "https://example.com/"}]))
                company = await db.scalar(select(Company).where(Company.name == f"Website {suffix}"))
                companies.append(company.id)
            result = await discovery.discover_due_companies(company_ids=companies)
            assert result["verified"] == 1
            async with AsyncSessionLocal() as db:
                source = await db.scalar(select(CompanySource).where(CompanySource.company_id == company.id))
                metadata = await db.get(CompanyIntelligence, company.id)
                assert metadata.careers_url == "https://example.com/careers"
                assert source.ownership_status == "ownership_verified" and source.discovery_evidence["link_chain"]
                source_id = source.id
            ingested = await service.ingest_due_sources(source_ids=[source_id])
            runs.append(ingested["run_id"])
            assert ingested["inserted"] == 1
            second = await discovery.discover_due_companies(company_ids=companies)
            assert second["claimed"] == 0
            forced = await discovery.discover_due_companies(force=True, company_ids=companies)
            assert forced["discovered"] == 1
            async with AsyncSessionLocal() as db:
                sources = list((await db.execute(select(CompanySource).where(CompanySource.company_id == company.id))).scalars())
                assert len(sources) == 1
                runs.extend((await db.execute(select(CompanyWatchRun.id).join(service.CompanySourceCheck, service.CompanySourceCheck.run_id == CompanyWatchRun.id).where(service.CompanySourceCheck.company_source_id == source_id))).scalars())
        finally:
            await cleanup(companies, runs)
    _run(scenario())


def test_discovery_claims_expiration_retry_ownership_conflict_and_unsupported():
    async def scenario():
        suffix, companies = uuid4().hex, []
        try:
            async with AsyncSessionLocal() as db:
                for index in range(2):
                    company = Company(name=f"Discovery Claim {index} {suffix}")
                    db.add(company)
                    await db.flush()
                    companies.append(company.id)
                    db.add(CompanyIntelligence(company_id=company.id, careers_url="https://example.com/careers"))
                await db.commit()
            first, second = await asyncio.gather(discovery.claim_due_companies(limit=1, company_ids=companies), discovery.claim_due_companies(limit=1, company_ids=companies))
            claims = [*first, *second]
            assert len({claim.id for claim in claims}) == 2
            candidate = Candidate("icims", suffix, "https://example.icims.com/jobs")
            evidence = {"evidence_url": "https://example.com/careers"}
            recorded = await discovery.record_discovery(discovery.DiscoveryResult(claims[0], ((candidate, evidence),)))
            assert recorded["status"] == "adapter_required"
            conflict = await discovery.record_discovery(discovery.DiscoveryResult(claims[1], ((candidate, evidence),)))
            assert conflict["status"] == "ownership_conflict"
            async with AsyncSessionLocal() as db:
                source = await db.scalar(select(CompanySource).where(CompanySource.identifier == suffix))
                assert source.last_success_at is source.last_verified_at is None
                metadata = await db.get(CompanyIntelligence, claims[0].id)
                assert metadata.next_discovery_at > datetime.utcnow()
                metadata.discovery_claim_token = "expired"
                metadata.discovery_claimed_until = datetime.utcnow() - timedelta(minutes=1)
                metadata.next_discovery_at = datetime.utcnow() - timedelta(minutes=1)
                await db.commit()
            retry = await discovery.claim_due_companies(company_ids=[claims[0].id])
            assert len(retry) == 1 and retry[0].token != "expired"
            lost = await discovery.record_discovery(discovery.DiscoveryResult(claims[0]))
            assert lost["status"] == "lease_lost"
            failed = await discovery.record_discovery(discovery.DiscoveryResult(retry[0], error="timeout"))
            assert failed["status"] == "discovery_failed"
            assert await discovery.claim_due_companies(company_ids=[claims[0].id]) == []
        finally:
            await cleanup(companies)
    _run(scenario())


def test_partial_jobs_persist_without_expiration_or_full_refresh_and_scope_isolation():
    async def scenario():
        suffix, companies, runs = uuid4().hex, [], []
        try:
            async with AsyncSessionLocal() as db:
                company = Company(name=f"Partial {suffix}")
                db.add(company)
                await db.flush()
                companies.append(company.id)
                source = CompanySource(company_id=company.id, provider="google", identifier=suffix, source_url="https://example.com/careers", status="healthy", last_success_at=datetime.utcnow() - timedelta(days=1))
                db.add(source)
                await db.flush()
                previous_success = source.last_success_at
                for identity, scope in (("old", "india_technical_v1"), ("other", "other_scope")):
                    db.add(AIJob(job_hash=hashlib.sha256(f"{suffix}{identity}".encode()).hexdigest(), source="google", external_id=f"{suffix}_{identity}", title="Software Engineer", company=company.name, location="India", apply_url="https://example.com/jobs", ingestion_source_id=source.id, inventory_scope=scope, last_seen_at=datetime.utcnow() - timedelta(days=1)))
                await db.commit()
                source_id = source.id
            job = NormalizedJobSchema(job_hash=hashlib.sha256(suffix.encode()).hexdigest(), source="google", external_id=suffix, title="Software Engineer", company=company.name, location="Gurugram, India", apply_url="https://example.com/jobs/new")
            for complete in (False, True):
                now, token = datetime.utcnow(), str(uuid4())
                async with AsyncSessionLocal() as db:
                    source = await db.get(CompanySource, source_id)
                    source.claim_token, source.claimed_until = token, now + timedelta(minutes=5)
                    run = CompanyWatchRun(run_type="ingest")
                    db.add(run)
                    await db.commit()
                    runs.append(run.id)
                result = service.IngestionResult(service.SourceCheckResult(service.ClaimedSource(source_id, company.id, company.name, "google", suffix, source.source_url, token), "healthy" if complete else "partial", 200, 1, 1, 1, observed_at=now), (job,), complete)
                await service._record_ingestion_results(run.id, [result])
                async with AsyncSessionLocal() as db:
                    listings = {row.external_id: row for row in (await db.execute(select(AIJob).where(AIJob.ingestion_source_id == source_id))).scalars()}
                    source = await db.get(CompanySource, source_id)
                    assert suffix in listings and listings[f"{suffix}_other"].missing_poll_count == 0
                    assert listings[f"{suffix}_old"].missing_poll_count == int(complete)
                    if not complete:
                        assert source.last_success_at == previous_success and source.last_ingested_at is None
                        assert source.last_observed_at == now and source.last_complete_scope is None
        finally:
            await cleanup(companies, runs)
    _run(scenario())
