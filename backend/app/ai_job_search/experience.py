"""Experience evidence from postings and candidate-specific eligibility."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from typing import Literal

from bs4 import BeautifulSoup


ExperienceStatus = Literal["matched", "mismatched", "unknown"]
_YEARS = re.compile(
    r"\b(?P<low>\d{1,2}(?:\.\d+)?)\s*"
    r"(?:(?:-|\u2013|to)\s*(?P<high>\d{1,2}(?:\.\d+)?))?\s*"
    r"(?:\+\s*)?(?:years?|yrs?)(?:['\u2019])?(?!\w)",
    re.IGNORECASE,
)
_SENIOR_TITLE = re.compile(
    r"\b(?:senior|sr\.?|staff|principal|director|distinguished|lead|"
    r"assistant\s+vice\s+president|vice\s+president|avp|vp)\b|\bhead\s+of\b",
    re.IGNORECASE,
)
_MID_TITLE = re.compile(r"\b(?:engineer|developer|analyst|designer)\s+(?:ii|2)\b", re.IGNORECASE)
_ENTRY_TITLE = re.compile(r"\b(?:junior|graduate|trainee|intern|entry.level)\b", re.IGNORECASE)
_SKILL_CONTEXT = re.compile(
    r"\b(?:python|java|javascript|react|api|automation|framework|sql|cloud|"
    r"kubernetes|aws|azure|testing\s+tools)\b",
    re.IGNORECASE,
)
_PREFERRED = re.compile(r"\b(?:preferred|nice.to.have|bonus|desirable|plus)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ExperienceFacts:
    required_min: float | None = None
    required_max: float | None = None
    source: str = "unknown"
    confidence: float = 0.0
    evidence: str | None = None
    seniority_level: str | None = None
    seniority_confidence: float = 0.0
    description_completeness: str = "unknown"


@dataclass(frozen=True)
class ExperienceAssessment:
    status: ExperienceStatus
    seniority_conflict: bool
    reason: str

    @property
    def recommendation_eligible(self) -> bool:
        return self.status == "matched" and not self.seniority_conflict


def _plain_text(description: str) -> str:
    if "<" in description and ">" in description:
        return BeautifulSoup(description, "html.parser").get_text(" ", strip=True)
    return unescape(description)


def infer_title_seniority(title: str) -> tuple[str | None, float]:
    if _SENIOR_TITLE.search(title):
        return "senior", 0.9
    if _MID_TITLE.search(title):
        return "mid", 0.65
    if _ENTRY_TITLE.search(title):
        return "entry", 0.85
    return None, 0.0


def _requirement_kind(suffix: str) -> str | None:
    lower = suffix.lower()
    if re.match(r"\s*(?:of\s+)?(?:total|overall)\s+experience\b", lower):
        return "total"
    if re.match(r"\s*(?:with|using)\b", lower):
        return "skill"
    if re.match(r"\s*(?:of\s+)?experience\s+(?:with|using|in)\b", lower):
        detail = re.split(r"[.;\n]", lower, maxsplit=1)[0][:85]
        if _SKILL_CONTEXT.search(detail):
            return "skill"
        return "total"
    if re.match(r"\s*(?:of\s+)?(?:[a-z][\w/-]*\s+){0,5}(?:experience|exp)\b", lower):
        detail = lower[:85]
        return "skill" if _SKILL_CONTEXT.search(detail.split("experience")[0]) else "total"
    if re.match(r"\s+(?:in|within)\s+(?:a\s+)?(?:[\w/-]+\s+){0,6}(?:role|position|engineering|development|industry|testing)\b", lower):
        return "total"
    return None


def extract_experience_facts(
    title: str, description: str | None, *, completeness: str = "unknown"
) -> ExperienceFacts:
    """Only explicit hard total-experience statements become numeric requirements."""
    seniority_level, seniority_confidence = infer_title_seniority(title)
    text = _plain_text(description or "")
    hard: list[tuple[float, float | None, str]] = []
    for match in _YEARS.finditer(text):
        low = float(match.group("low"))
        high = float(match.group("high")) if match.group("high") else None
        if low > 40 or (high is not None and (high > 40 or high < low)):
            continue
        suffix = text[match.end():match.end() + 105]
        kind = _requirement_kind(suffix)
        if kind != "total":
            continue
        context = text[max(0, match.start() - 35):min(len(text), match.end() + 85)]
        clause = re.split(r"[.;\n]", context, maxsplit=1)[0].strip()
        if _PREFERRED.search(context[:35]) or _PREFERRED.search(suffix[:28]):
            continue
        hard.append((low, high, clause[:180]))

    if hard:
        low = max(item[0] for item in hard)
        upper_bounds = [item[1] for item in hard if item[1] is not None]
        high = min(upper_bounds) if upper_bounds else None
        if high is None or low <= high:
            evidence = next(item[2] for item in hard if item[0] == low)
            return ExperienceFacts(
                required_min=low, required_max=high, source="description",
                confidence=0.95, evidence=evidence,
                seniority_level=seniority_level,
                seniority_confidence=seniority_confidence,
                description_completeness=completeness,
            )
    return ExperienceFacts(
        seniority_level=seniority_level,
        seniority_confidence=seniority_confidence,
        description_completeness=completeness,
    )


def facts_from_job(job: object) -> ExperienceFacts:
    """Use persisted evidence when present; evaluate legacy rows from their stored text."""
    completeness = getattr(job, "description_completeness", None) or (
        "snippet" if getattr(job, "source", None) == "adzuna" else "unknown"
    )
    if (
        (getattr(job, "experience_parse_version", None) or 0) < 1
        and completeness == "unknown"
        and getattr(job, "source", None) in {"greenhouse", "lever", "ashby"}
        and getattr(job, "description", None)
    ):
        completeness = "full"
    if (getattr(job, "experience_parse_version", None) or 0) < 1:
        return extract_experience_facts(
            getattr(job, "title", ""), getattr(job, "description", None),
            completeness=completeness,
        )
    return ExperienceFacts(
        required_min=getattr(job, "required_experience_min", None),
        required_max=getattr(job, "required_experience_max", None),
        source=getattr(job, "experience_source", "unknown"),
        confidence=getattr(job, "experience_confidence", 0.0),
        evidence=getattr(job, "experience_evidence", None),
        seniority_level=getattr(job, "seniority_level", None),
        seniority_confidence=getattr(job, "seniority_confidence", 0.0),
        description_completeness=completeness,
    )


def assess_experience(
    facts: ExperienceFacts, candidate_min: float | None, candidate_max: float | None
) -> ExperienceAssessment:
    seniority_conflict = bool(
        candidate_max is not None and candidate_max <= 2.5
        and facts.seniority_level == "senior"
        and facts.seniority_confidence >= 0.8
    )
    if candidate_min is None and candidate_max is None:
        return ExperienceAssessment("unknown", False, "Set your experience range")
    if facts.required_min is None:
        reason = "Experience requirement not verified"
        if seniority_conflict:
            reason = "Title indicates a senior role; years are not stated"
        return ExperienceAssessment("unknown", seniority_conflict, reason)
    if candidate_max is not None and facts.required_min > candidate_max:
        return ExperienceAssessment(
            "mismatched", seniority_conflict,
            f"Requires at least {facts.required_min:g} years",
        )
    if facts.required_max is not None and candidate_min is not None and facts.required_max < candidate_min:
        return ExperienceAssessment(
            "mismatched", seniority_conflict,
            f"Role lists at most {facts.required_max:g} years",
        )
    if facts.description_completeness != "full":
        return ExperienceAssessment(
            "unknown", seniority_conflict,
            "Full experience requirements not verified",
        )
    return ExperienceAssessment("matched", seniority_conflict, "Experience range overlaps")
