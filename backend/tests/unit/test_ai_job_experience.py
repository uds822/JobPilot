import json
from types import SimpleNamespace

from app.ai_job_search.enrichment import extract_structured_description
from app.ai_job_search.experience import assess_experience, extract_experience_facts, facts_from_job
from app.ai_job_search.matching import experience_fit_score
from app.ai_job_search.schemas import NormalizedJobSchema, ResumeProfileSchema


def test_total_experience_overrides_skill_years_in_quality_engineer_postings():
    examples = (
        ("Quality Engineer II", "3-6 years of total experience in testing enterprise software/product with 2+ years of experience in test automation for APIs, Integrations, and UI.", 3, 6),
        ("Lead Quality Engineer", "8-12 years of total experience in testing enterprise software/product with 8+ years of experience in automation framework development and design.", 8, 12),
    )
    for title, description, minimum, maximum in examples:
        facts = extract_experience_facts(title, description, completeness="full")
        assert (facts.required_min, facts.required_max) == (minimum, maximum)
        assert facts.source == "description"
        assert assess_experience(facts, 1, 2).status == "mismatched"


def test_run_86_snippet_shapes_are_unknown_and_seniority_is_separate():
    snippet = ("Syndigo gets great products chosen. " * 20)[:500]
    for title, conflict in (
        ("Quality Engineer II", False),
        ("Lead Quality Engineer", True),
        ("Generative AI Quality Engineer - Assistant Vice President", True),
    ):
        facts = extract_experience_facts(title, snippet, completeness="snippet")
        decision = assess_experience(facts, 1, 2)
        assert facts.required_min is None
        assert decision.status == "unknown"
        assert decision.seniority_conflict is conflict
        assert not decision.recommendation_eligible


def test_preferred_and_skill_only_years_do_not_become_hard_total_requirements():
    for description in (
        "5 years preferred.",
        "2 years with Python and 3 years of experience in test automation.",
    ):
        facts = extract_experience_facts("Python Engineer", description, completeness="full")
        assert facts.required_min is None
        assert assess_experience(facts, 1, 2).status == "unknown"
    matched = extract_experience_facts(
        "Python Engineer", "Requires 1-2 years of total experience.", completeness="full"
    )
    assert assess_experience(matched, 1, 2).recommendation_eligible


def test_short_snippet_cannot_confirm_a_positive_match():
    facts = extract_experience_facts(
        "Python Engineer", "Requires 1-2 years of total experience.", completeness="snippet"
    )
    decision = assess_experience(facts, 1, 2)
    assert (facts.required_min, facts.required_max) == (1, 2)
    assert decision.status == "unknown"
    assert not decision.recommendation_eligible


def test_legacy_full_ats_description_is_usable_but_legacy_adzuna_is_not():
    posting = "Requires 1-2 years of total experience building Python services."
    for source, expected in (("greenhouse", "matched"), ("lever", "matched"), ("ashby", "matched"), ("adzuna", "unknown")):
        job = SimpleNamespace(
            source=source, title="Python Engineer", description=posting,
            description_completeness="unknown", experience_parse_version=0,
        )
        assert assess_experience(facts_from_job(job), 1, 2).status == expected


def test_experience_subscore_is_neutral_for_unknown_and_low_for_senior_conflict():
    base = dict(
        job_hash="test", source="adzuna", external_id="test",
        company="Example", location="India", description="Short snippet",
        description_completeness="snippet", apply_url="https://example.com/job",
    )
    profile = ResumeProfileSchema(skills=["Python"])
    preferences = {"experience_min_years": 1, "experience_max_years": 2}
    assert experience_fit_score(
        NormalizedJobSchema(title="Python Engineer", **base), profile, preferences
    ) == 70
    assert experience_fit_score(
        NormalizedJobSchema(title="Lead Python Engineer", **base), profile, preferences
    ) == 20


def test_enrichment_accepts_only_matching_full_jobposting():
    posting = {
        "@context": "https://schema.org", "@type": "JobPosting",
        "title": "Quality Engineer II", "hiringOrganization": {"name": "Syndigo"},
        "description": "<p>3-6 years of total experience.</p>" + "Build reliable products. " * 40,
    }
    html = f'<script type="application/ld+json">{json.dumps(posting)}</script>'
    full = extract_structured_description(html, "Quality Engineer II", "Syndigo", "short snippet")
    assert full and "3-6 years of total experience" in full
    assert extract_structured_description(html, "Quality Engineer II", "Other Company", "short snippet") is None
