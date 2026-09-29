import asyncio
import logging
from collections import Counter
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import AsyncSessionLocal
from app.ai_job_search.models import AIJob, CompanyProfileCache, UserResumeProfile, SearchRun, AIJobMatch, UserJobState
from app.ai_job_search.persistence import canonical_job_values, upsert_canonical_jobs
from app.ai_job_search.schemas import ResumeProfileSchema, NormalizedJobSchema
from app.ai_job_search.matching import compute_match_score_llm, compute_match_score_deterministic
from app.ai_job_search.resume_archetype import classify_resume
from app.ai_job_search.query_generator import generate_queries
from app.ai_job_search.job_skill_extractor import (
    extract_job_skills, KNOWN_SKILLS,
    MIN_CONFIDENT_SKILLS, MAX_LLM_FALLBACK_PER_SEARCH,
)
from app.ai_job_search.skill_normalizer import normalize_skill
import app.ai_job_search.providers.adzuna as adzuna_provider
import app.ai_job_search.providers.greenhouse as greenhouse_provider
import app.ai_job_search.providers.lever as lever_provider
from app.ai_job_search.providers.ats_filters import ats_location_matches
from app.company_watch.models import CompanyIntelligence, CompanySource

logger = logging.getLogger(__name__)

from app.company_watch.providers import SUPPORTED_PROVIDERS

DIRECT_ATS_SOURCES = set(SUPPORTED_PROVIDERS)
SURFACED_JOB_LIMIT = 20


# Compatibility aliases retained for existing tests and internal imports.
_canonical_job_values = canonical_job_values
_upsert_canonical_jobs = upsert_canonical_jobs


async def _refresh_company_watch_inventory() -> None:
    """Refresh a bounded DB-selected batch using the worker's shared leases."""
    from app.company_watch.service import ingest_due_sources

    try:
        await ingest_due_sources(limit=25, concurrency=8)
    except Exception:
        logger.exception("Company Watch refresh failed; continuing with stored jobs and Adzuna")


async def _fetch_jobs_from_providers(
    queries: list[str],
    target_locations: list[str],
    greenhouse_boards: list[dict[str, str]] | None = None,
    lever_sites: list[dict[str, str]] | None = None,
) -> list[NormalizedJobSchema]:
    """Fetch all providers concurrently without letting one failure abort the run."""
    provider_names = ("Adzuna", "Greenhouse", "Lever")
    results = await asyncio.gather(
        adzuna_provider.fetch(
            queries=queries,
            locations=target_locations,
            pages=3,
            max_days_old=14,
            concurrency=5,
        ),
        greenhouse_provider.fetch(
            queries=queries,
            target_locations=target_locations,
            concurrency=8,
            boards=greenhouse_boards if greenhouse_boards is not None else [],
        ),
        lever_provider.fetch(
            queries=queries,
            target_locations=target_locations,
            concurrency=8,
            sites=lever_sites if lever_sites is not None else [],
        ),
        return_exceptions=True,
    )

    merged: list[NormalizedJobSchema] = []
    provider_counts: Dict[str, int] = {}
    for provider_name, result in zip(provider_names, results):
        if isinstance(result, BaseException):
            logger.error("%s provider failed; continuing search: %s", provider_name, result)
            provider_counts[provider_name] = 0
            continue
        provider_counts[provider_name] = len(result)
        merged.extend(result)

    logger.info(
        "Provider merge: Adzuna=%d Greenhouse=%d Lever=%d total_before_dedupe=%d",
        provider_counts.get("Adzuna", 0),
        provider_counts.get("Greenhouse", 0),
        provider_counts.get("Lever", 0),
        len(merged),
    )
    return merged


async def _fetch_stored_company_watch_jobs(
    db: AsyncSession,
    freshness_days: int = 14,
) -> tuple[list[NormalizedJobSchema], dict[tuple[str, str], int]]:
    """Read recently verified Company Watch postings without calling ATS sources."""
    cutoff = datetime.utcnow() - timedelta(days=freshness_days)
    rows = await db.execute(
        select(AIJob).join(CompanySource, CompanySource.id == AIJob.ingestion_source_id).where(
            AIJob.ingestion_source_id.is_not(None),
            AIJob.is_active.is_(True),
            AIJob.last_seen_at >= cutoff,
            CompanySource.is_active.is_(True),
            ~select(CompanyIntelligence.company_id).where(
                CompanyIntelligence.company_id == CompanySource.company_id,
                CompanyIntelligence.is_active.is_(False),
            ).exists(),
        )
    )
    jobs = []
    ids_by_key: dict[tuple[str, str], int] = {}
    for job in rows.scalars().all():
        ids_by_key[(job.source, job.external_id)] = job.id
        jobs.append(
            NormalizedJobSchema(
                job_hash=job.job_hash,
                source=job.source,
                external_id=job.external_id,
                title=job.title,
                company=job.company,
                location=job.location,
                remote=job.remote,
                description=job.description,
                salary_min=job.salary_min,
                salary_max=job.salary_max,
                salary_currency=job.salary_currency,
                salary_interval=job.salary_interval,
                salary_source=job.salary_source,
                apply_url=job.apply_url,
                source_url=job.source_url,
                posted_date=job.posted_date,
                fetched_at=job.fetched_at,
                is_active=job.is_active,
            )
        )
    logger.info("Company Watch search corpus: fresh_active=%d", len(jobs))
    return jobs, ids_by_key


def _matches_target_locations(
    job: NormalizedJobSchema,
    target_locations: list[str],
) -> bool:
    if job.source in DIRECT_ATS_SOURCES:
        return ats_location_matches(job.location, job.description, target_locations)
    return adzuna_provider.matches_selected_locations(job.location, target_locations)


def _candidate_sort_key(
    candidate: tuple[NormalizedJobSchema, Dict[str, Any]],
) -> tuple[float, int]:
    """Prefer direct ATS links only when candidate match scores are tied."""
    job, score = candidate
    return (
        float(score["match_score"]),
        int(job.source in DIRECT_ATS_SOURCES),
    )


async def run_ai_job_search_task(user_id: int, search_run_id: int):
    """
    Background worker task triggered on demand by user.
    Executes fetch -> dedupe -> validity -> hard_filters -> scoring -> DB persistence.
    """
    async with AsyncSessionLocal() as db:
        run = await db.get(SearchRun, search_run_id)
        if not run:
            logger.error(f"SearchRun {search_run_id} not found")
            return

        run.status = "running"
        run.started_at = datetime.utcnow()
        await db.commit()

        try:
            # 1. Fetch user resume profile
            res_profile_query = await db.execute(
                select(UserResumeProfile).where(UserResumeProfile.user_id == user_id).order_by(UserResumeProfile.id.desc())
            )
            resume_profile_model = res_profile_query.scalars().first()
            if not resume_profile_model:
                raise ValueError("No resume profile found for user. Please upload a resume first.")

            parsed_data = resume_profile_model.parsed_profile or {}
            profile_schema = ResumeProfileSchema(**parsed_data)
            user_prefs = resume_profile_model.user_preferences or {}

            # 2. Archetype classification → understand what kind of engineer this person is
            cand_exp = float(user_prefs.get("years_experience") or profile_schema.years_experience or 1.0)
            archetype_result = classify_resume(profile_schema)
            top_archetypes = archetype_result["top_archetypes"]
            logger.info(f"Resume archetypes: {top_archetypes}")

            # 3. Query generation → 2-3 role-specific queries per top archetype
            queries = generate_queries(top_archetypes)

            # 4. Determine target locations
            if "preferred_locations" in user_prefs:
                requested_locations = user_prefs.get("preferred_locations") or []
            else:
                requested_locations = profile_schema.preferred_locations or []
            target_locs = adzuna_provider.normalize_india_search_locations(
                requested_locations
            )

            # ATS refreshes persist complete snapshots through shared worker claims.
            # The existing provider APIs remain available; this path reads ATS inventory.
            live_jobs, _ = await asyncio.gather(
                _fetch_jobs_from_providers(
                    queries, target_locs, greenhouse_boards=[], lever_sites=[],
                ),
                _refresh_company_watch_inventory(),
            )
            stored_company_jobs, stored_ids = await _fetch_stored_company_watch_jobs(db)
            all_fetched = list(live_jobs)
            all_fetched.extend(stored_company_jobs)
            logger.info(
                "Search source merge: live=%d company_watch=%d total=%d",
                len(live_jobs),
                len(stored_company_jobs),
                len(all_fetched),
            )
            run.jobs_fetched = len(all_fetched)
            await db.commit()

            # 4. Cross-source Deduplication
            unique_jobs_map: Dict[str, NormalizedJobSchema] = {}
            for job in all_fetched:
                if job.job_hash not in unique_jobs_map:
                    unique_jobs_map[job.job_hash] = job
            
            jobs_after_dedupe = list(unique_jobs_map.values())
            run.jobs_after_dedupe = len(jobs_after_dedupe)

            # 5. Validity and selected-location check. Adzuna's `where` parameter is
            # discovery input, so validate the actual location before scoring.
            jobs_valid = [
                j for j in jobs_after_dedupe
                if j.is_active
                and _matches_target_locations(j, target_locs)
            ]
            run.jobs_after_validity = len(jobs_valid)
            logger.info(
                "Location filtering: selected=%s accepted=%d rejected=%d",
                target_locs,
                len(jobs_valid),
                len(jobs_after_dedupe) - len(jobs_valid),
            )

            # 6. Keep all valid jobs; recommendation views apply the score cutoff.
            jobs_after_hard = jobs_valid
            run.jobs_after_hard_filters = len(jobs_after_hard)

            # Persist every valid live candidate before ranking. Stored Company
            # Watch candidates already have canonical IDs and are deliberately
            # not refreshed by a database read.
            live_keys = {(job.source, job.external_id) for job in live_jobs}
            valid_live_jobs = [
                job
                for job in jobs_after_hard
                if (job.source, job.external_id) in live_keys
            ]
            live_ids, inserted_count, updated_count, skipped_count = (
                await _upsert_canonical_jobs(db, valid_live_jobs)
            )
            canonical_ids = {**stored_ids, **live_ids}
            logger.info(
                "Canonical live inventory: new=%d existing_updated=%d "
                "batch_duplicates_skipped=%d failures=0",
                inserted_count,
                updated_count,
                skipped_count,
            )

            user_states: dict[int, UserJobState] = {}
            if canonical_ids:
                state_rows = (
                    await db.execute(
                        select(UserJobState).where(
                            UserJobState.user_id == user_id,
                            UserJobState.job_id.in_(set(canonical_ids.values())),
                        )
                    )
                ).scalars().all()
                user_states = {state.job_id: state for state in state_rows}

            eligible_jobs = []
            for job in jobs_after_hard:
                job_id = canonical_ids.get((job.source, job.external_id))
                state = user_states.get(job_id) if job_id is not None else None
                if state is None or state.status not in {"applied", "dismissed"}:
                    eligible_jobs.append(job)
            jobs_after_hard = eligible_jobs

            # 7. Deterministic skill extraction + capped LLM fallback
            # -----------------------------------------------------------------
            # Phase 1: deterministic extraction for ALL jobs (no network calls)
            confident_jobs: list = []    # (job, job_skills) — scored immediately
            low_conf_jobs: list = []     # (job, job_skills) — may use LLM fallback

            for j in jobs_after_hard:
                job_skills = extract_job_skills(
                    j.description or "", KNOWN_SKILLS, normalize_skill
                )
                if len(job_skills) >= MIN_CONFIDENT_SKILLS:
                    confident_jobs.append((j, job_skills))
                else:
                    low_conf_jobs.append((j, job_skills))

            logger.info(
                f"Skill extraction: {len(confident_jobs)} confident, "
                f"{len(low_conf_jobs)} low-confidence (cap={MAX_LLM_FALLBACK_PER_SEARCH})"
            )

            # Phase 2: score confident jobs deterministically (instant, no LLM)
            scored_candidates: list = []
            for j, job_skills in confident_jobs:
                try:
                    score_data = compute_match_score_deterministic(
                        j, profile_schema, job_skills, user_prefs
                    )
                    scored_candidates.append((j, score_data))
                except Exception as e:
                    logger.error(f"Deterministic scoring failed for '{j.title}': {e}")

            # Phase 3: capped LLM fallback for low-confidence jobs only
            llm_cap = min(len(low_conf_jobs), MAX_LLM_FALLBACK_PER_SEARCH)
            if llm_cap > 0:
                logger.info(
                    f"LLM fallback: scoring {llm_cap}/{len(low_conf_jobs)} low-confidence jobs"
                )
                sem = asyncio.Semaphore(3)

                async def _score_low_conf(j, job_skills):
                    async with sem:
                        try:
                            score_data = await compute_match_score_llm(
                                j, profile_schema, user_prefs
                            )
                            return (j, score_data)
                        except Exception as e:
                            logger.warning(
                                f"LLM fallback failed for '{j.title}': {e} — using deterministic"
                            )
                            try:
                                score_data = compute_match_score_deterministic(
                                    j, profile_schema, job_skills, user_prefs
                                )
                                return (j, score_data)
                            except Exception:
                                pass
                        return None

                llm_tasks = [
                    _score_low_conf(j, js) for j, js in low_conf_jobs[:llm_cap]
                ]
                llm_results = await asyncio.gather(*llm_tasks)
                scored_candidates.extend(r for r in llm_results if r is not None)

            # Jobs beyond the LLM cap: score deterministically with sparse result
            for j, job_skills in low_conf_jobs[llm_cap:]:
                try:
                    score_data = compute_match_score_deterministic(
                        j, profile_schema, job_skills, user_prefs
                    )
                    scored_candidates.append((j, score_data))
                except Exception as e:
                    logger.error(f"Scoring failed for '{j.title}': {e}")

            run.jobs_scored = len(scored_candidates)
            logger.info(
                "Scored jobs by provider: %s",
                dict(Counter(job.source for job, _ in scored_candidates)),
            )

            # Deduplicate provider postings before saving match history. Unseen
            # jobs receive a small ordering preference; displayed match scores
            # remain authoritative and unchanged.
            unique_scored: list[tuple[NormalizedJobSchema, Dict[str, Any]]] = []
            scored_keys: set[tuple[str, str]] = set()
            for candidate in scored_candidates:
                key = (candidate[0].source, candidate[0].external_id)
                if key not in scored_keys and key in canonical_ids:
                    scored_keys.add(key)
                    unique_scored.append(candidate)

            def resurfacing_key(
                candidate: tuple[NormalizedJobSchema, Dict[str, Any]],
            ) -> tuple[int, float, int]:
                key = (candidate[0].source, candidate[0].external_id)
                state = user_states.get(canonical_ids[key])
                return (
                    int(state is None),
                    *_candidate_sort_key(candidate),
                )

            unique_scored.sort(key=resurfacing_key, reverse=True)
            match_candidates = unique_scored
            top_candidates = match_candidates[:SURFACED_JOB_LIMIT]
            logger.info(
                "Returned candidates by provider: %s",
                dict(Counter(job.source for job, _ in top_candidates)),
            )

            # 8. Save every scored posting for the user's discovery history.
            for canonical_job, score_info in match_candidates:
                canonical_key = (canonical_job.source, canonical_job.external_id)
                job_id = canonical_ids[canonical_key]
                state = user_states.get(job_id)
                match_record = AIJobMatch(
                    search_run_id=search_run_id,
                    user_id=user_id,
                    profile_version_id=resume_profile_model.id,
                    job_id=job_id,
                    match_score=score_info["match_score"],
                    match_level=score_info["match_level"],
                    callback_likelihood=score_info["callback_likelihood"],
                    match_reasoning=score_info["match_reasoning"],
                    strengths=score_info["strengths"],
                    gaps=score_info["gaps"],
                    skills_overlap=score_info["skills_overlap"],
                    experience_fit=score_info["experience_fit"],
                    role_similarity=score_info["role_similarity"],
                    location_fit=score_info["location_fit"],
                    industry_fit=score_info["industry_fit"],
                    company_type_fit=score_info["company_type_fit"],
                    posting_freshness=score_info["posting_freshness"],
                    status="saved" if state and state.status == "saved" else "new",
                )
                db.add(match_record)

            # Record only the surfaced first page. ON CONFLICT preserves explicit
            # saved/applied/dismissed state while updating exposure metadata.
            surfaced_at = datetime.utcnow()
            if top_candidates:
                exposure_values = [
                    {
                        "user_id": user_id,
                        "job_id": canonical_ids[(job.source, job.external_id)],
                        "status": "viewed",
                        "first_shown_at": surfaced_at,
                        "last_shown_at": surfaced_at,
                        "show_count": 1,
                        "created_at": surfaced_at,
                        "updated_at": surfaced_at,
                    }
                    for job, _ in top_candidates
                ]
                exposure_insert = pg_insert(UserJobState).values(exposure_values)
                await db.execute(
                    exposure_insert.on_conflict_do_update(
                        constraint="uq_ai_user_job_state_user_job",
                        set_={
                            "last_shown_at": surfaced_at,
                            "show_count": UserJobState.show_count + 1,
                            "updated_at": surfaced_at,
                        },
                    )
                )

            run.status = "completed"
            run.completed_at = datetime.utcnow()
            run.jobs_returned = len(top_candidates)
            await db.commit()
            logger.info(
                f"SearchRun {search_run_id} completed successfully with "
                f"{len(match_candidates)} active matches and {len(top_candidates)} surfaced."
            )

        except Exception as err:
            await db.rollback()
            run.status = "failed"
            run.completed_at = datetime.utcnow()
            run.error_message = str(err)
            await db.commit()
            logger.exception(f"SearchRun {search_run_id} failed: {err}")
