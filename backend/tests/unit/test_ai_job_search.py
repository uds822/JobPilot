from app.ai_job_search.matching import (
    classify_company,
    compute_match_score_deterministic,
    extract_required_experience,
)
from app.ai_job_search.parser import _heuristic_parse
from app.ai_job_search.schemas import NormalizedJobSchema, ResumeProfileSchema


def test_resume_parser_heuristic():
    profile = _heuristic_parse(
        "Experienced Senior Python Engineer with 5+ years of experience in "
        "FastAPI, PostgreSQL, React, and AWS."
    )

    assert "Python" in profile.skills
    assert profile.years_experience >= 5.0
    assert profile.seniority_level == "senior"


def test_experience_extraction_uses_minimum_of_a_range():
    assert extract_required_experience(
        "Software Engineer I",
        "Requires 1 to 1.5 years experience in Python.",
    ) == 1.0
    assert extract_required_experience(
        "Senior Distributed Lead",
        "Requires 5+ years of experience.",
    ) == 5.0


def test_company_classification_remains_available_to_scoring():
    industry, company_type, confidence = classify_company(
        "GitHub",
        "Backend Engineer",
        "Build developer tools.",
    )

    assert industry == "Software"
    assert company_type == "product"
    assert confidence > 0.9


def test_current_deterministic_matching_engine():
    profile = ResumeProfileSchema(
        skills=["Python", "FastAPI", "PostgreSQL"],
        years_experience=4.0,
        recent_titles=["Backend Engineer"],
        preferred_locations=["Bengaluru"],
    )
    job = NormalizedJobSchema(
        job_hash="greenhouse-test-123",
        source="greenhouse",
        external_id="test-123",
        title="Senior Backend Engineer",
        company="GitHub",
        location="Bengaluru, India",
        description="Build Python services with FastAPI and PostgreSQL.",
        apply_url="https://example.com/jobs/test-123",
    )

    result = compute_match_score_deterministic(
        job,
        profile,
        {"python", "fastapi", "postgresql"},
        {"preferred_locations": ["Bengaluru"]},
    )

    assert result["match_score"] >= 80
    assert result["skills_overlap"] == 100
    assert result["industry"] == "Software"
