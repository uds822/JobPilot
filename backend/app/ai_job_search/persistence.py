from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import case, literal_column
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_job_search.models import AIJob
from app.ai_job_search.schemas import NormalizedJobSchema
from app.ai_job_search.experience import extract_experience_facts


CANONICAL_JOB_CONSTRAINT = "uq_ai_jobs_source_external_id"
DEFAULT_UPSERT_BATCH_SIZE = 500


def canonical_job_values(
    job: NormalizedJobSchema,
    observed_at: datetime,
) -> dict[str, Any]:
    """Return provider-owned fields that are safe to insert or refresh."""
    completeness = "snippet" if job.source == "adzuna" else job.description_completeness
    facts = extract_experience_facts(
        job.title, job.description, completeness=completeness
    )
    return {
        "job_hash": job.job_hash,
        "source": job.source,
        "external_id": job.external_id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "remote": job.remote,
        "description": job.description,
        "description_excerpt": job.description if completeness == "snippet" else None,
        "description_completeness": completeness,
        "required_experience_min": facts.required_min,
        "required_experience_max": facts.required_max,
        "experience_source": facts.source,
        "experience_confidence": facts.confidence,
        "experience_evidence": facts.evidence,
        "seniority_level": facts.seniority_level,
        "seniority_confidence": facts.seniority_confidence,
        "experience_parse_version": 1,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "salary_currency": job.salary_currency,
        "salary_interval": job.salary_interval,
        "salary_source": job.salary_source,
        "apply_url": job.apply_url,
        "source_url": job.source_url,
        "posted_date": job.posted_date,
        "fetched_at": observed_at,
        "is_active": True,
        "last_seen_at": observed_at,
        "missing_poll_count": 0,
    }


async def upsert_canonical_jobs(
    db: AsyncSession,
    jobs: list[NormalizedJobSchema],
    ingestion_source_id: int | None = None,
    *,
    observed_at: datetime | None = None,
    verification_method: str | None = None,
    inventory_scope: str | None = None,
    batch_size: int = DEFAULT_UPSERT_BATCH_SIZE,
) -> tuple[dict[tuple[str, str], int], int, int, int]:
    """Bulk UPSERT provider postings and return their canonical IDs.

    The unique constraint is the concurrency boundary. Input duplicates are
    removed before batching because PostgreSQL cannot update one conflict target
    twice in a single INSERT statement.
    """
    unique_jobs: dict[tuple[str, str], NormalizedJobSchema] = {}
    for job in jobs:
        unique_jobs.setdefault((job.source, job.external_id), job)

    skipped_count = len(jobs) - len(unique_jobs)
    if not unique_jobs:
        return {}, 0, 0, skipped_count

    observation_time = observed_at or datetime.utcnow()
    safe_batch_size = max(1, min(batch_size, DEFAULT_UPSERT_BATCH_SIZE))
    unique_values = list(unique_jobs.values())
    ids_by_key: dict[tuple[str, str], int] = {}
    inserted_count = 0
    updated_count = 0

    for offset in range(0, len(unique_values), safe_batch_size):
        chunk = unique_values[offset : offset + safe_batch_size]
        values = [canonical_job_values(job, observation_time) for job in chunk]
        for value in values:
            if inventory_scope is not None:
                value["inventory_scope"] = inventory_scope
            if ingestion_source_id is not None:
                value["ingestion_source_id"] = ingestion_source_id
            if verification_method is not None:
                value["last_verified_at"] = observation_time
                value["verification_method"] = verification_method

        insert_stmt = pg_insert(AIJob).values(values)
        keep_full = (
            (AIJob.description_completeness == "full")
            & (insert_stmt.excluded.description_completeness != "full")
        )
        update_values = {
            "job_hash": insert_stmt.excluded.job_hash,
            "title": insert_stmt.excluded.title,
            "company": insert_stmt.excluded.company,
            "location": insert_stmt.excluded.location,
            "remote": insert_stmt.excluded.remote,
            "description": case((keep_full, AIJob.description), else_=insert_stmt.excluded.description),
            "description_excerpt": case(
                (insert_stmt.excluded.description_completeness == "snippet", insert_stmt.excluded.description),
                else_=AIJob.description_excerpt,
            ),
            "description_completeness": case(
                (keep_full, AIJob.description_completeness),
                else_=insert_stmt.excluded.description_completeness,
            ),
            "required_experience_min": case((keep_full, AIJob.required_experience_min), else_=insert_stmt.excluded.required_experience_min),
            "required_experience_max": case((keep_full, AIJob.required_experience_max), else_=insert_stmt.excluded.required_experience_max),
            "experience_source": case((keep_full, AIJob.experience_source), else_=insert_stmt.excluded.experience_source),
            "experience_confidence": case((keep_full, AIJob.experience_confidence), else_=insert_stmt.excluded.experience_confidence),
            "experience_evidence": case((keep_full, AIJob.experience_evidence), else_=insert_stmt.excluded.experience_evidence),
            "seniority_level": insert_stmt.excluded.seniority_level,
            "seniority_confidence": insert_stmt.excluded.seniority_confidence,
            "experience_parse_version": case((keep_full, AIJob.experience_parse_version), else_=insert_stmt.excluded.experience_parse_version),
            "salary_min": insert_stmt.excluded.salary_min,
            "salary_max": insert_stmt.excluded.salary_max,
            "salary_currency": insert_stmt.excluded.salary_currency,
            "salary_interval": insert_stmt.excluded.salary_interval,
            "salary_source": insert_stmt.excluded.salary_source,
            "apply_url": insert_stmt.excluded.apply_url,
            "source_url": insert_stmt.excluded.source_url,
            "posted_date": insert_stmt.excluded.posted_date,
            "fetched_at": insert_stmt.excluded.fetched_at,
            "is_active": True,
            "last_seen_at": insert_stmt.excluded.last_seen_at,
            "missing_poll_count": 0,
        }
        if ingestion_source_id is not None:
            update_values["ingestion_source_id"] = insert_stmt.excluded.ingestion_source_id
        if inventory_scope is not None:
            update_values["inventory_scope"] = insert_stmt.excluded.inventory_scope
        if verification_method is not None:
            update_values["last_verified_at"] = insert_stmt.excluded.last_verified_at
            update_values["verification_method"] = insert_stmt.excluded.verification_method

        statement = insert_stmt.on_conflict_do_update(
            constraint=CANONICAL_JOB_CONSTRAINT,
            set_=update_values,
        ).returning(
            AIJob.id,
            AIJob.source,
            AIJob.external_id,
            literal_column("xmax = 0").label("was_inserted"),
        )
        rows = (await db.execute(statement)).mappings().all()
        ids_by_key.update(
            {
                (row["source"], row["external_id"]): row["id"]
                for row in rows
            }
        )
        inserted_count += sum(1 for row in rows if row["was_inserted"])
        updated_count += sum(1 for row in rows if not row["was_inserted"])

    return ids_by_key, inserted_count, updated_count, skipped_count
