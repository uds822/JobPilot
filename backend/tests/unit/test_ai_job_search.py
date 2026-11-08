import asyncio

import pypdf

import app.ai_job_search.parser as resume_parser
from app.ai_job_search.matching import (
    classify_company,
    experience_range_matches,
    compute_match_score_deterministic,
    extract_required_experience,
    extract_required_experience_range,
)
from app.ai_job_search.parser import _heuristic_parse, _infer_target_roles
from app.ai_job_search.query_generator import generate_queries
from app.ai_job_search.schemas import NormalizedJobSchema, ResumeProfileSchema, UserPreferencesUpdate


def test_pdf_text_extraction_uses_pypdf(monkeypatch):
    class Page:
        def extract_text(self):
            return "Software Engineer Python FastAPI PostgreSQL"

    class Reader:
        pages = [Page()]

    monkeypatch.setattr(pypdf, "PdfReader", lambda _: Reader())

    assert "FastAPI" in resume_parser.extract_text_from_file(b"%PDF-test", "resume.pdf")


def test_unreadable_pdf_fails_instead_of_decoding_binary_bytes():
    try:
        resume_parser.extract_text_from_file(b"%PDF-invalid", "resume.pdf")
    except ValueError as error:
        assert "Could not read this PDF" in str(error)
    else:
        raise AssertionError("invalid PDF should not be accepted as extracted resume text")


def test_empty_llm_resume_parse_falls_back_to_extracted_text(monkeypatch):
    resume_text = (
        "Software Engineer Python FastAPI PostgreSQL SQLAlchemy REST APIs. "
        "Built LangGraph and LangChain agents, Azure AI Foundry, RAG, "
        "Semantic Kernel, and Sentence Transformers applications."
    )
    monkeypatch.setattr(resume_parser, "extract_text_from_file", lambda *_: resume_text)

    async def empty_llm_result(_):
        return {"skills": [], "recent_titles": [], "target_roles": []}

    monkeypatch.setattr(resume_parser, "_try_llm_parse", empty_llm_result)
    profile = asyncio.run(resume_parser.parse_resume_content(b"pdf", "resume.pdf"))

    assert profile.parse_method == "heuristic"
    assert {"Python", "FastAPI", "PostgreSQL"}.issubset(profile.skills)
    assert {
        "Software Development Engineer I",
        "Python Backend Engineer",
        "Backend Developer",
        "Applied AI Engineer",
        "Generative AI Engineer",
        "AI Backend Engineer",
        "LLM Application Engineer",
        "Applied Machine Learning Engineer",
        "Machine Learning Engineer",
    }.issubset(profile.target_roles)


def test_resume_parser_heuristic():
    profile = _heuristic_parse(
        "Experienced Senior Python Engineer with 5+ years of experience in "
        "FastAPI, PostgreSQL, React, and AWS."
    )

    assert "Python" in profile.skills
    assert profile.years_experience >= 5.0
    assert profile.seniority_level == "senior"
    assert "Python Backend Engineer" in _infer_target_roles(profile).target_roles


def test_resume_title_is_preserved_when_skill_archetypes_are_missing():
    profile = ResumeProfileSchema(recent_titles=["Backend Engineer"])

    assert _infer_target_roles(profile).target_roles == ["Backend Engineer"]


def test_resume_parser_does_not_invent_roles_or_skills():
    profile = _heuristic_parse("Account manager with experience in customer relationships and sales operations.")

    assert profile.skills == []
    assert profile.target_roles == []
    assert profile.years_experience == 0


def test_resume_roles_lead_job_queries_and_deduplicate_archetype_queries():
    queries = generate_queries(
        [{"name": "BACKEND_DEV", "confidence": 0.9}],
        ["Platform Engineer", "Backend Engineer", "platform engineer"],
    )

    assert queries[:2] == ["Platform Engineer", "Backend Engineer"]
    assert len(queries) == len({query.lower() for query in queries})
    assert len(generate_queries([], [f"role {index}" for index in range(15)])) == 10


def test_result_count_preferences_only_accept_supported_options():
    assert UserPreferencesUpdate(new_jobs_limit=5, top_matches_limit=50)
    for invalid in (4, 15, 100):
        try:
            UserPreferencesUpdate(top_matches_limit=invalid)
        except ValueError:
            continue
        raise AssertionError(f"unsupported result count accepted: {invalid}")


def test_experience_preferences_validate_range_order():
    assert UserPreferencesUpdate(experience_min_years=2, experience_max_years=4)
    try:
        UserPreferencesUpdate(experience_min_years=5, experience_max_years=3)
    except ValueError:
        pass
    else:
        raise AssertionError("minimum experience greater than maximum was accepted")


def test_experience_extraction_uses_minimum_of_a_range():
    assert extract_required_experience(
        "Software Engineer I",
        "Requires 1 to 1.5 years experience in Python.",
    ) == 1.0
    assert extract_required_experience(
        "Senior Distributed Lead",
        "Requires 5+ years of experience.",
    ) == 5.0


def test_experience_extraction_and_candidate_range_eligibility():
    assert extract_required_experience_range(
        "Python Engineer", "Requires 2-4 years of relevant experience."
    ) == (2.0, 4.0)
    assert extract_required_experience_range(
        "Backend Engineer", "At least 5 years of experience required."
    ) == (5.0, None)
    assert extract_required_experience_range(
        "Backend Engineer", "5+ years of software engineering experience."
    ) == (5.0, None)
    assert extract_required_experience_range(
        "Backend Engineer", "8+ years' experience preferred."
    ) == (8.0, None)
    assert extract_required_experience_range(
        "Backend Engineer", "8+ yrs exp preferred."
    ) == (8.0, None)
    assert experience_range_matches("Python Engineer", "", 2, 4)
    assert experience_range_matches(
        "Python Engineer", "Requires 3-5 years of experience.", 2, 4
    )
    assert not experience_range_matches(
        "Python Engineer", "Requires 6+ years of experience.", 2, 4
    )
    assert not experience_range_matches(
        "Python Engineer", "Requires 1-2 years of experience.", 3, 5
    )
    assert experience_range_matches("Python Engineer", "Experience not specified.", 2, 4)
    assert not experience_range_matches("Senior Software Engineer", "", 1, 2)
    assert not experience_range_matches("Principal Engineer", "", 1, 2)


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


def test_primary_resume_skills_outweigh_tool_keywords():
    profile = ResumeProfileSchema(
        skills=["Python", "Docker"],
        skill_groups={"primary": ["Python"], "tools": ["Docker"]},
        target_roles=["Backend Engineer"],
    )
    job = NormalizedJobSchema(
        job_hash="weighted-skill-test",
        source="test",
        external_id="weighted-skill-test",
        title="Senior Backend Engineer",
        company="Example",
        location="Remote",
        description="Build backend services.",
        apply_url="https://example.com/job",
    )
    primary_match = compute_match_score_deterministic(job, profile, {"python"}, {})
    tool_match = compute_match_score_deterministic(job, profile, {"docker"}, {})

    assert primary_match["skills_overlap"] > tool_match["skills_overlap"]
    assert primary_match["role_similarity"] > compute_match_score_deterministic(
        job.model_copy(update={"title": "Senior Data Analyst"}), profile, {"python"}, {}
    )["role_similarity"]
