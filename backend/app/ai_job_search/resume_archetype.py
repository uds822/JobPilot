"""
Step 2 — Resume archetype classifier.

Pipeline:
  parsed resume (ResumeProfileSchema)
      ↓
  weighted skill vector  (skill → float weight)
      ↓
  cosine similarity vs each archetype skill set
      ↓
  ranked top 1-3 archetypes with confidence scores

Formulas are fixed and deterministic per the plan (Sections 8 & 9).
"""
from __future__ import annotations

import math
import logging
from collections import defaultdict
from typing import TYPE_CHECKING

from app.ai_job_search.skill_normalizer import normalize_skill, normalize_skills
from app.ai_job_search.archetypes import ARCHETYPES

if TYPE_CHECKING:
    from app.ai_job_search.schemas import ResumeProfileSchema

logger = logging.getLogger(__name__)

# ── Weight constants (context-based) ─────────────────────────────────────────
WEIGHT_FLAT_SKILL = 1.0       # skill appears only in the flat skills list
WEIGHT_RECENT_ROLE = 2.0      # skill found in most-recent role/title text
WEIGHT_PROJECT_DESC = 2.0     # skill found in a project description
WEIGHT_PROJECT_TITLE = 3.0    # skill found in a project title

# ── Frequency boost cap ───────────────────────────────────────────────────────
FREQUENCY_BOOST_CAP = 3


def frequency_boost(mention_count: int, cap: int = FREQUENCY_BOOST_CAP) -> float:
    """
    Diminishing-return multiplier for repeated skill mentions.

    mention_count: how many times the skill appears in one context bucket.
    cap:           hard ceiling on counted occurrences.

    Returns a multiplier ≥ 1.0 (or 0.0 if count == 0).
    """
    effective = min(mention_count, cap)
    if effective <= 0:
        return 0.0
    return 1.0 + math.log1p(effective - 1)


def _count_skill_in_text(skill: str, text: str) -> int:
    """Count (normalized) occurrences of a skill in a body of text."""
    if not text:
        return 0
    return text.lower().count(skill)


def build_weighted_skill_vector(profile: "ResumeProfileSchema") -> dict[str, float]:
    """
    Build a weighted skill vector from a parsed resume profile.

    Each skill accumulates weight from every context it appears in:
      - flat skills list        × 1.0  (× frequency_boost)
      - most-recent role/title × 2.0  (× frequency_boost)
      - project descriptions   × 2.0  (× frequency_boost)
      - project titles         × 3.0  (× frequency_boost)

    Skills are normalized before accumulation so aliases don't double-count.
    """
    accumulator: dict[str, float] = defaultdict(float)

    # --- flat skills list ---
    flat_normalized = normalize_skills(profile.skills)
    for skill in flat_normalized:
        accumulator[skill] += WEIGHT_FLAT_SKILL * frequency_boost(1)

    # --- most-recent role/title ---
    # ResumeProfileSchema has recent_titles (list of strings)
    role_text = " ".join(profile.recent_titles).lower() if profile.recent_titles else ""
    for skill in flat_normalized:
        cnt = _count_skill_in_text(skill, role_text)
        if cnt:
            accumulator[skill] += WEIGHT_RECENT_ROLE * frequency_boost(cnt)

    # ResumeProfileSchema doesn't carry structured project data yet.
    # When project fields are added (project_titles, project_descriptions),
    # wire them in here with WEIGHT_PROJECT_TITLE / WEIGHT_PROJECT_DESC.
    # For now we treat industries / preferred_industries as light description context.
    desc_text = " ".join(
        (profile.industries or []) + (profile.preferred_industries or [])
    ).lower()
    for skill in flat_normalized:
        cnt = _count_skill_in_text(skill, desc_text)
        if cnt:
            accumulator[skill] += WEIGHT_PROJECT_DESC * frequency_boost(cnt)

    return dict(accumulator)


def _archetype_vector(archetype_name: str) -> dict[str, float]:
    """
    Build a flat unit-weight vector for an archetype.
    All archetype skills get weight 1.0 (no context weighting for requirements).
    """
    skills = ARCHETYPES[archetype_name]["skills"]
    return {normalize_skill(s): 1.0 for s in skills}


def cosine_similarity(
    resume_vec: dict[str, float],
    archetype_vec: dict[str, float],
) -> float:
    """
    Cosine similarity between resume weighted vector and archetype unit vector.
    Returns a float in [0, 1].
    """
    shared = set(resume_vec) & set(archetype_vec)
    dot = sum(resume_vec[s] * archetype_vec[s] for s in shared)
    resume_norm = math.sqrt(sum(v ** 2 for v in resume_vec.values()))
    arch_norm = math.sqrt(sum(v ** 2 for v in archetype_vec.values()))
    if resume_norm == 0 or arch_norm == 0:
        return 0.0
    return dot / (resume_norm * arch_norm)


def classify_resume(
    profile: "ResumeProfileSchema",
    top_n: int = 3,
) -> dict:
    """
    Classify a resume into role archetypes.

    Returns:
    {
        "top_archetypes": [
            {"name": "AI_ENGINEER", "confidence": 0.91},
            ...
        ],
        "weighted_skill_vector": {"python": 4.2, "fastapi": 4.8, ...},
        "all_scores": {"AI_ENGINEER": 0.91, "BACKEND_DEV": 0.84, ...}
    }
    """
    skill_vector = build_weighted_skill_vector(profile)

    scores: dict[str, float] = {}
    for archetype_name in ARCHETYPES:
        arch_vec = _archetype_vector(archetype_name)
        scores[archetype_name] = round(cosine_similarity(skill_vector, arch_vec), 4)

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top = [{"name": name, "confidence": conf} for name, conf in ranked[:top_n] if conf > 0]

    # Ensure at least one archetype is returned
    if not top:
        top = [{"name": "BACKEND_DEV", "confidence": 0.0}]

    logger.info(f"Archetype classification: {top}")

    return {
        "top_archetypes": top,
        "weighted_skill_vector": skill_vector,
        "all_scores": dict(ranked),
    }
