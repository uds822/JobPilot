"""
Step 3 — Query generation.

Takes top archetypes → returns deduplicated natural-language queries
ready for Adzuna (and future providers).

Queries are defined in archetypes.py, not here.
This module only does the generation + dedup logic.
"""
from __future__ import annotations
import logging
from app.ai_job_search.archetypes import ARCHETYPE_QUERIES

logger = logging.getLogger(__name__)


def generate_queries(top_archetypes: list[dict]) -> list[str]:
    """
    Generate deduplicated Adzuna search queries from the top archetypes.

    Args:
        top_archetypes: list of {"name": str, "confidence": float}
                        from resume_archetype.classify_resume()

    Returns:
        Deduplicated list of natural-language query strings.
        Order is preserved (higher-confidence archetype queries come first).

    Example:
        top_archetypes = [
            {"name": "AI_ENGINEER", "confidence": 0.91},
            {"name": "BACKEND_DEV", "confidence": 0.84},
        ]
        → ["AI engineer", "LLM engineer", "GenAI developer",
           "backend engineer", "Python backend developer",
           "backend software engineer"]
    """
    seen: set[str] = set()
    queries: list[str] = []

    for arch in top_archetypes:
        name = arch.get("name", "")
        for q in ARCHETYPE_QUERIES.get(name, []):
            q_norm = q.strip()
            if q_norm and q_norm.lower() not in seen:
                seen.add(q_norm.lower())
                queries.append(q_norm)

    if not queries:
        logger.warning("No archetype queries generated; falling back to 'software engineer'")
        queries = ["software engineer"]

    logger.info(f"Generated {len(queries)} queries from archetypes: {queries}")
    return queries
