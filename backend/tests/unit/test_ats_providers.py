import asyncio

import httpx

from app.ai_job_search import services
from app.ai_job_search.matching import compute_match_score_deterministic
from app.ai_job_search.providers.ats_filters import (
    ats_location_matches,
    title_matches_queries,
)
import app.ai_job_search.providers.greenhouse as greenhouse_provider
from app.ai_job_search.providers.greenhouse import GreenhouseProvider
import app.ai_job_search.providers.lever as lever_provider
from app.ai_job_search.providers.lever import LeverProvider
from app.ai_job_search.schemas import NormalizedJobSchema, ResumeProfileSchema


def _job(source: str, external_id: str) -> NormalizedJobSchema:
    return NormalizedJobSchema(
        job_hash=f"{source}-{external_id}",
        source=source,
        external_id=external_id,
        title="Backend Software Engineer",
        company="Example",
        location="Bengaluru, Karnataka, India",
        description="Python FastAPI PostgreSQL",
        apply_url=f"https://example.com/{source}/{external_id}",
    )


def test_deterministic_title_filter_rejects_unrelated_roles():
    queries = ["backend software engineer", "AI engineer"]

    assert title_matches_queries("Senior Software Engineer, Backend", queries)
    assert title_matches_queries("AI Engineer", queries)
    assert not title_matches_queries("Sales Manager", queries)
    assert not title_matches_queries("Engineering Recruiter", queries)


def test_ats_remote_description_fallback_is_used_only_when_location_is_ambiguous():
    assert ats_location_matches(
        "Remote",
        "Candidates may work from anywhere in India.",
        ["India"],
    )
    assert not ats_location_matches(
        "Remote",
        "Candidates must reside in the United States.",
        ["India"],
    )
    assert not ats_location_matches(
        "London, UK",
        "Our engineering team also has an office in India.",
        ["India"],
    )


def test_ats_country_codes_are_safe_for_all_india_and_city_searches():
    assert ats_location_matches("IN", None, ["India"])
    assert not ats_location_matches("IN", None, ["Bengaluru"])
    assert not ats_location_matches("US", "Our engineering team is in India.", ["India"])


def test_remote_india_is_eligible_for_a_selected_indian_city():
    assert ats_location_matches("Remote - India", None, ["Bengaluru"])
    assert ats_location_matches(
        "Remote",
        "Candidates may work from anywhere in India.",
        ["Hyderabad"],
    )
    assert not ats_location_matches(
        "Remote",
        "Candidates must reside in the United States.",
        ["Bengaluru"],
    )


def test_ats_indian_city_aliases_match_selected_locations():
    assert ats_location_matches("Bangalore, Karnataka, India", None, ["Bengaluru"])
    assert ats_location_matches("Hyderabad, Telangana", None, ["Hyderabad"])
    assert ats_location_matches("Pune, Maharashtra", None, ["Pune"])
    assert not ats_location_matches("Pune, Maharashtra", None, ["Hyderabad"])


def test_service_location_gate_keeps_remote_ats_job_for_selected_city():
    ats_job = _job("greenhouse", "remote-bengaluru")
    ats_job.location = "Remote"
    ats_job.description = "This position is available to candidates in Bengaluru."

    assert services._matches_target_locations(ats_job, ["Bengaluru"])

    adzuna_job = ats_job.model_copy(update={"source": "adzuna"})
    assert not services._matches_target_locations(adzuna_job, ["Bengaluru"])


def test_greenhouse_fetch_filters_title_location_and_isolates_invalid_board():
    async def scenario():
        payload = {
            "jobs": [
                {
                    "id": 101,
                    "title": "Senior Software Engineer, Backend",
                    "location": {"name": "Bangalore, India"},
                    "content": "<p>Build Python services.</p>",
                    "absolute_url": "https://boards.greenhouse.io/example/jobs/101",
                },
                {
                    "id": 102,
                    "title": "Sales Manager",
                    "location": {"name": "Bengaluru, India"},
                    "content": "<p>Sales role.</p>",
                },
                {
                    "id": 103,
                    "title": "Backend Software Engineer",
                    "location": {"name": "London, UK"},
                    "content": "<p>Backend role.</p>",
                },
                {
                    "id": 104,
                    "title": "AI Engineer",
                    "location": {"name": "Remote"},
                    "content": "<p>Available to candidates located in India.</p>",
                },
            ]
        }

        def handler(request: httpx.Request):
            if "/invalid/" in str(request.url):
                return httpx.Response(404, json={})
            return httpx.Response(200, json=payload)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            jobs = await GreenhouseProvider().fetch(
                queries=["backend software engineer", "AI engineer"],
                target_locations=["India"],
                boards=[
                    {"company": "Example", "board": "example"},
                    {"company": "Invalid", "board": "invalid"},
                ],
                concurrency=2,
                client=client,
            )

        assert {job.external_id for job in jobs} == {"example_101", "example_104"}
        assert all(job.source == "greenhouse" for job in jobs)
        assert jobs[0].salary_min is None
        assert "<p>" not in (jobs[0].description or "")

    asyncio.run(scenario())


def test_lever_fetch_filters_title_location_and_isolates_invalid_site():
    async def scenario():
        payload = [
            {
                "id": "lev-1",
                "text": "Backend Software Engineer",
                "categories": {"location": "Hyderabad, India"},
                "descriptionPlain": "Build Python services.",
                "hostedUrl": "https://jobs.lever.co/example/lev-1",
                "createdAt": 1_700_000_000_000,
            },
            {
                "id": "lev-2",
                "text": "Product Marketing Manager",
                "categories": {"location": "Pune, India"},
            },
            {
                "id": "lev-3",
                "text": "AI Engineer",
                "categories": {"location": "Singapore"},
            },
            {
                "id": "lev-4",
                "text": "AI Engineer",
                "categories": {"location": "Remote"},
                "descriptionPlain": "This role is open to candidates across India.",
                "workplaceType": "remote",
            },
        ]

        def handler(request: httpx.Request):
            if "/invalid?" in str(request.url):
                return httpx.Response(404, json={})
            return httpx.Response(200, json=payload)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            jobs = await LeverProvider().fetch(
                queries=["backend software engineer", "AI engineer"],
                target_locations=["India"],
                sites=[
                    {"company": "Example", "site": "example"},
                    {"company": "Invalid", "site": "invalid"},
                ],
                concurrency=2,
                client=client,
            )

        assert {job.external_id for job in jobs} == {"example_lev-1", "example_lev-4"}
        assert all(job.source == "lever" for job in jobs)
        assert next(job for job in jobs if job.external_id == "example_lev-4").remote

    asyncio.run(scenario())


def test_explicit_empty_ats_registry_does_not_fetch_default_sources():
    async def scenario():
        requests = 0

        def handler(request: httpx.Request):
            nonlocal requests
            requests += 1
            return httpx.Response(500)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            greenhouse_jobs = await GreenhouseProvider().fetch(
                queries=["software engineer"],
                target_locations=["India"],
                boards=[],
                client=client,
            )
            lever_jobs = await LeverProvider().fetch(
                queries=["software engineer"],
                target_locations=["India"],
                sites=[],
                client=client,
            )

        assert greenhouse_jobs == []
        assert lever_jobs == []
        assert requests == 0

    asyncio.run(scenario())


def test_module_provider_wrappers_forward_registry_filters():
    async def scenario():
        greenhouse_requests = []
        lever_requests = []

        def greenhouse_handler(request: httpx.Request):
            greenhouse_requests.append(str(request.url))
            return httpx.Response(200, json={"jobs": []})

        def lever_handler(request: httpx.Request):
            lever_requests.append(str(request.url))
            return httpx.Response(200, json=[])

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(greenhouse_handler)
        ) as greenhouse_client:
            greenhouse_jobs = await greenhouse_provider.fetch(
                queries=["software engineer"],
                target_locations=["India"],
                boards=[],
                client=greenhouse_client,
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lever_handler)
        ) as lever_client:
            lever_jobs = await lever_provider.fetch(
                queries=["software engineer"],
                target_locations=["India"],
                sites=[],
                client=lever_client,
            )

        assert greenhouse_jobs == []
        assert lever_jobs == []
        assert greenhouse_requests == []
        assert lever_requests == []

    asyncio.run(scenario())


def test_provider_merge_keeps_successful_results_when_one_provider_fails(monkeypatch):
    async def adzuna_fetch(**kwargs):
        return [_job("adzuna", "a-1")]

    async def greenhouse_fetch(**kwargs):
        raise httpx.TimeoutException("greenhouse unavailable")

    async def lever_fetch(**kwargs):
        return [_job("lever", "l-1")]

    monkeypatch.setattr(services.adzuna_provider, "fetch", adzuna_fetch)
    monkeypatch.setattr(services.greenhouse_provider, "fetch", greenhouse_fetch)
    monkeypatch.setattr(services.lever_provider, "fetch", lever_fetch)

    jobs = asyncio.run(
        services._fetch_jobs_from_providers(
            queries=["backend software engineer"],
            target_locations=["India"],
        )
    )

    assert [(job.source, job.external_id) for job in jobs] == [
        ("adzuna", "a-1"),
        ("lever", "l-1"),
    ]


def test_ats_job_is_compatible_with_existing_deterministic_scoring():
    profile = ResumeProfileSchema(
        skills=["Python", "FastAPI", "PostgreSQL"],
        years_experience=3,
        recent_titles=["Backend Engineer"],
        preferred_locations=["Bengaluru"],
    )

    result = compute_match_score_deterministic(
        _job("greenhouse", "gh-1"),
        profile,
        {"python", "fastapi", "postgresql"},
        {"preferred_locations": ["Bengaluru"]},
    )

    assert result["match_score"] >= 80
    assert result["skills_overlap"] == 100


def test_direct_ats_job_wins_only_an_exact_score_tie():
    adzuna = (_job("adzuna", "a-1"), {"match_score": 75.0})
    greenhouse = (_job("greenhouse", "g-1"), {"match_score": 75.0})
    lever = (_job("lever", "l-1"), {"match_score": 74.0})

    ranked = sorted(
        [adzuna, lever, greenhouse],
        key=services._candidate_sort_key,
        reverse=True,
    )

    assert [job.source for job, _ in ranked] == [
        "greenhouse",
        "adzuna",
        "lever",
    ]
