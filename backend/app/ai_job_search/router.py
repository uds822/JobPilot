import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks, Query, HTTPException
from sqlalchemy import and_, func, or_, select, update, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.database import get_db
from app.dependencies import get_current_user
from app.models.users import User
from app.ai_job_search.models import UserResumeProfile, SearchRun, AIJobMatch, AIJob, CompanyProfileCache, UserJobState
from app.ai_job_search.schemas import (
    ResumeProfileSchema,
    UserPreferencesUpdate,
    JobMatchCardResponse,
    SearchRunStatusResponse,
    MatchActionRequest
)
from app.ai_job_search.parser import parse_resume_content
from app.ai_job_search.services import run_ai_job_search_task
from app.ai_job_search.matching import classify_company
from app.services.application import create_application_from_ai_job
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai-jobs", tags=["AI Job Search"])


@router.get("/debug")
async def debug_ai_job_search(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Diagnostic endpoint: tests Groq & OpenRouter connectivity,
    reports user profile state and latest search run.
    """
    import httpx
    results = {}

    # 1. Test Groq
    groq_key = settings.GROQ_API_KEY
    groq_model = settings.GROQ_MODEL
    groq_status = "no_key"
    if groq_key:
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                resp = await c.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                    json={"model": groq_model, "messages": [{"role": "user", "content": "Reply: OK"}], "max_tokens": 5},
                )
                groq_status = f"ok (model={groq_model})" if resp.status_code == 200 else f"http_{resp.status_code}: {resp.text[:150]}"
        except httpx.TimeoutException:
            groq_status = "timeout"
        except Exception as e:
            groq_status = f"error: {e}"
    results["groq"] = groq_status

    # 2. Test OpenRouter
    or_key = settings.OPENROUTER_API_KEY
    or_model = settings.OPENROUTER_MODEL
    or_status = "no_key"
    if or_key:
        try:
            async with httpx.AsyncClient(timeout=15.0) as c:
                resp = await c.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {or_key}", "Content-Type": "application/json",
                             "HTTP-Referer": "https://jobpilot.app", "X-Title": "JobPilot"},
                    json={"model": or_model, "messages": [{"role": "user", "content": "Reply: OK"}], "max_tokens": 5},
                )
                or_status = f"ok (model={or_model})" if resp.status_code == 200 else f"http_{resp.status_code}: {resp.text[:150]}"
        except httpx.TimeoutException:
            or_status = "timeout"
        except Exception as e:
            or_status = f"error: {e}"
    results["openrouter"] = or_status

    # 3. Test Adzuna
    adzuna_status = "no_credentials"
    if settings.ADZUNA_APP_ID and settings.ADZUNA_APP_KEY:
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                resp = await c.get(
                    "https://api.adzuna.com/v1/api/jobs/in/search/1",
                    params={"app_id": settings.ADZUNA_APP_ID, "app_key": settings.ADZUNA_APP_KEY,
                            "what": "python developer", "results_per_page": 1},
                )
                if resp.status_code == 200:
                    adzuna_status = f"ok (total_results={resp.json().get('count', 0)})"
                else:
                    adzuna_status = f"http_{resp.status_code}: {resp.text[:150]}"
        except Exception as e:
            adzuna_status = f"error: {e}"
    results["adzuna"] = adzuna_status

    # 4. User resume profile
    stmt = select(UserResumeProfile).where(UserResumeProfile.user_id == current_user.id).order_by(UserResumeProfile.id.desc())
    res = await db.execute(stmt)
    profile = res.scalars().first()
    if profile and profile.parsed_profile:
        p = profile.parsed_profile
        results["resume_profile"] = {
            "has_profile": True,
            "skills_count": len(p.get("skills", [])),
            "skills_sample": p.get("skills", [])[:5],
            "years_experience": p.get("years_experience"),
            "preferred_locations": p.get("preferred_locations", []),
            "user_preferences": profile.user_preferences or {},
        }
    else:
        results["resume_profile"] = {"has_profile": False}

    # 5. Latest search run
    run_res = await db.execute(
        select(SearchRun).where(SearchRun.user_id == current_user.id).order_by(SearchRun.id.desc())
    )
    run = run_res.scalars().first()
    results["latest_search_run"] = {
        "id": run.id, "status": run.status,
        "jobs_fetched": run.jobs_fetched, "jobs_scored": run.jobs_scored,
        "jobs_returned": run.jobs_returned, "error_message": run.error_message,
    } if run else None

    # 6. Active scoring mode
    if groq_status.startswith("ok"):
        results["scoring_mode"] = f"LLM — Groq ({groq_model})"
    elif or_status.startswith("ok"):
        results["scoring_mode"] = f"LLM — OpenRouter ({or_model})"
    else:
        results["scoring_mode"] = "Heuristic fallback (no LLM reachable)"

    return results


@router.post("/upload-resume", response_model=ResumeProfileSchema)
async def upload_resume(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload PDF/DOCX resume, parse candidate profile, and store profile version."""
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    profile_schema = await parse_resume_content(contents, file.filename or "resume.pdf")

    stmt = select(UserResumeProfile).where(UserResumeProfile.user_id == current_user.id).order_by(UserResumeProfile.id.desc())
    res = await db.execute(stmt)
    existing_profile = res.scalars().first()

    parsed_dict = profile_schema.model_dump()

    if existing_profile:
        existing_profile.raw_resume_text = f"File: {file.filename}"
        existing_profile.parsed_profile = parsed_dict
        existing_profile.updated_at = datetime.utcnow()
    else:
        new_profile = UserResumeProfile(
            user_id=current_user.id,
            raw_resume_text=f"File: {file.filename}",
            parsed_profile=parsed_dict,
            user_preferences={}
        )
        db.add(new_profile)

    await db.commit()
    return profile_schema


@router.get("/profile")
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's parsed resume profile and active filter preferences."""
    stmt = select(UserResumeProfile).where(UserResumeProfile.user_id == current_user.id).order_by(UserResumeProfile.id.desc())
    res = await db.execute(stmt)
    profile = res.scalars().first()

    if not profile:
        return {
            "has_profile": False,
            "parsed_profile": None,
            "user_preferences": {}
        }

    return {
        "has_profile": True,
        "parsed_profile": profile.parsed_profile,
        "user_preferences": profile.user_preferences
    }


@router.put("/preferences")
async def update_preferences(
    prefs: UserPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update user filter preferences (years experience, target locations, salary expectation, preferred industries, company types, remote pref)."""
    stmt = select(UserResumeProfile).where(UserResumeProfile.user_id == current_user.id).order_by(UserResumeProfile.id.desc())
    res = await db.execute(stmt)
    profile = res.scalars().first()

    if not profile:
        raise HTTPException(status_code=404, detail="Please upload a resume before updating preferences.")

    # Assign a new dictionary so SQLAlchemy detects changes to the JSON column.
    curr_prefs = dict(profile.user_preferences or {})
    update_data = prefs.model_dump(exclude_unset=True)

    for k, v in update_data.items():
        if v is not None:
            curr_prefs[k] = v

    # Also update parsed_profile if years_experience was explicitly updated
    if prefs.years_experience is not None and profile.parsed_profile:
        p_dict = dict(profile.parsed_profile)
        p_dict["years_experience"] = prefs.years_experience
        profile.parsed_profile = p_dict

    profile.user_preferences = curr_prefs
    profile.updated_at = datetime.utcnow()
    await db.commit()
    return {"message": "Preferences updated successfully", "user_preferences": curr_prefs}


@router.post("/search", response_model=SearchRunStatusResponse)
async def trigger_job_search(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Trigger on-demand AI Job Search.
    """
    stmt = select(UserResumeProfile).where(UserResumeProfile.user_id == current_user.id).order_by(UserResumeProfile.id.desc())
    res = await db.execute(stmt)
    profile = res.scalars().first()
    if not profile:
        raise HTTPException(status_code=400, detail="Resume required. Please upload your resume first.")

    run_stmt = select(SearchRun).where(SearchRun.user_id == current_user.id).order_by(SearchRun.id.desc())
    run_res = await db.execute(run_stmt)
    latest_run = run_res.scalars().first()

    if latest_run and latest_run.started_at:
        time_since = (datetime.utcnow() - latest_run.started_at).total_seconds()
        if time_since < 30 and latest_run.status in ["queued", "running"]:
            return latest_run

    new_run = SearchRun(
        user_id=current_user.id,
        profile_version_id=profile.id,
        status="queued",
        started_at=datetime.utcnow()
    )
    db.add(new_run)
    await db.commit()
    await db.refresh(new_run)

    background_tasks.add_task(run_ai_job_search_task, current_user.id, new_run.id)
    return new_run


@router.get("/runs/{run_id}", response_model=SearchRunStatusResponse)
async def get_search_run_status(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Query progress and metrics of a search run execution."""
    run = await db.get(SearchRun, run_id)
    if not run or run.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Search run not found")
    return run


@router.get("", response_model=List[JobMatchCardResponse])
async def get_ai_matched_jobs(
    view: str = Query("new", pattern="^(for_you|top_matches|new|all_active|all_unapplied|saved|applied)$"),
    industry: Optional[str] = Query(None),
    company_type: Optional[str] = Query(None),
    company_name: Optional[str] = Query(None),
    min_score: float = Query(60.0),
    min_salary: Optional[float] = Query(None),
    remote_only: bool = Query(False),
    sort_by: str = Query("relevance"), # "relevance" | "salary_high" | "salary_low" | "freshness"
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Fetch user's scored 'AI Found Jobs' dashboard cards with company search, salary filters, and sorting."""
    latest_completed_run = (
        select(SearchRun.id)
        .where(SearchRun.user_id == current_user.id, SearchRun.status == "completed")
        .order_by(SearchRun.started_at.desc(), SearchRun.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    ranked_matches = (
        select(
            AIJobMatch.id.label("match_id"),
            func.min(AIJobMatch.search_run_id)
            .over(partition_by=AIJobMatch.job_id)
            .label("first_run_id"),
            func.row_number()
            .over(
                partition_by=AIJobMatch.job_id,
                order_by=(AIJobMatch.created_at.desc(), AIJobMatch.id.desc()),
            )
            .label("match_rank"),
        )
        .where(AIJobMatch.user_id == current_user.id)
        .subquery()
    )
    stmt = (
        select(AIJobMatch, AIJob, UserJobState)
        .join(
            ranked_matches,
            and_(
                ranked_matches.c.match_id == AIJobMatch.id,
                ranked_matches.c.match_rank == 1,
            ),
        )
        .join(AIJob, AIJob.id == AIJobMatch.job_id)
        .outerjoin(
            UserJobState,
            and_(
                UserJobState.user_id == current_user.id,
                UserJobState.job_id == AIJob.id,
            ),
        )
    )

    if view == "saved":
        stmt = stmt.where(
            UserJobState.status == "saved",
            UserJobState.applied_at.is_(None),
        )
    elif view == "applied":
        stmt = stmt.where(UserJobState.status == "applied")
    else:
        stmt = stmt.where(
            or_(
                UserJobState.id.is_(None),
                UserJobState.status.in_(("viewed", "saved")),
            ),
            UserJobState.applied_at.is_(None),
        )
        if view != "all_unapplied":
            stmt = stmt.where(AIJob.is_active.is_(True))
        if view == "new":
            stmt = stmt.where(
                ranked_matches.c.first_run_id == latest_completed_run
            )
        elif view in ("for_you", "top_matches"):
            stmt = stmt.where(
                ranked_matches.c.first_run_id != latest_completed_run,
                AIJobMatch.match_score >= min_score,
            )

    if remote_only:
        stmt = stmt.where(AIJob.remote.is_(True))
    if company_name and company_name.strip():
        stmt = stmt.where(AIJob.company.ilike(f"%{company_name.strip()}%"))

    rows = (await db.execute(stmt)).all()

    output: List[JobMatchCardResponse] = []
    for m, job, user_state in rows:

        if min_salary and min_salary > 0:
            sal = job.salary_max or job.salary_min or 0
            if sal > 0:
                sal_usd = sal
                if job.salary_currency == "INR":
                    if sal > 1000:
                        sal_usd = sal / 85.0
                    else:
                        sal_usd = (sal * 100000) / 85.0
                if sal_usd < min_salary:
                    continue

        ind, ctype, _ = classify_company(job.company, job.title, job.description or "")

        if industry and industry.lower() != "any" and industry.lower() not in ind.lower():
            continue
        if company_type and company_type.lower() != "any" and company_type.lower() != ctype.lower():
            continue

        card = JobMatchCardResponse(
            id=m.id,
            match_score=m.match_score,
            match_level=m.match_level,
            match_reasoning=m.match_reasoning,
            callback_likelihood=m.callback_likelihood,
            strengths=m.strengths or [],
            gaps=m.gaps or [],
            status=user_state.status if user_state else "new",
            is_saved=bool(user_state and (user_state.saved_at or user_state.status == "saved")),
            skills_overlap=m.skills_overlap,
            experience_fit=m.experience_fit,
            role_similarity=m.role_similarity,
            location_fit=m.location_fit,
            industry_fit=m.industry_fit,
            company_type_fit=m.company_type_fit,
            posting_freshness=m.posting_freshness,
            job_id=job.id,
            title=job.title,
            company=job.company,
            location=job.location,
            remote=job.remote,
            description=job.description,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            salary_currency=job.salary_currency,
            salary_interval=job.salary_interval,
            apply_url=job.apply_url,
            source=job.source,
            posted_date=job.posted_date,
            discovery_channel=("Company Watch" if job.ingestion_source_id else "Live provider"),
            last_seen_at=job.last_seen_at,
            is_active=job.is_active,
            is_expired=not job.is_active,
            application_id=user_state.application_id if user_state else None,
            first_shown_at=user_state.first_shown_at if user_state else None,
            last_shown_at=user_state.last_shown_at if user_state else None,
            show_count=user_state.show_count if user_state else 0,
            industry=ind,
            company_type=ctype
        )
        output.append(card)

    # Sorting
    if sort_by == "salary_high":
        output.sort(key=lambda c: c.salary_max or c.salary_min or 0, reverse=True)
    elif sort_by == "salary_low":
        output.sort(key=lambda c: c.salary_min or c.salary_max or 9999999)
    elif sort_by == "freshness":
        output.sort(key=lambda c: c.posted_date or datetime.min, reverse=True)
    else: # relevance
        output.sort(key=lambda c: c.match_score, reverse=True)

    return output[offset : offset + limit]


@router.post("/matches/{match_id}/action")
async def update_match_action(
    match_id: int,
    req: MatchActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update durable state for the canonical job represented by a match."""
    match = await db.scalar(
        select(AIJobMatch)
        .where(AIJobMatch.id == match_id)
        .with_for_update()
    )
    if not match or match.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Job match not found")

    if req.action not in ["save", "unsave", "dismiss", "apply"]:
        raise HTTPException(status_code=400, detail="Invalid action type")

    now = datetime.utcnow()
    state_insert = pg_insert(UserJobState).values(
        user_id=current_user.id,
        job_id=match.job_id,
        status="viewed",
        first_shown_at=now,
        last_shown_at=now,
        show_count=1,
        created_at=now,
        updated_at=now,
    ).on_conflict_do_nothing(
        constraint="uq_ai_user_job_state_user_job"
    )
    await db.execute(state_insert)
    state = await db.scalar(
        select(UserJobState)
        .where(
            UserJobState.user_id == current_user.id,
            UserJobState.job_id == match.job_id,
        )
        .with_for_update()
    )
    if state is None:
        raise HTTPException(status_code=500, detail="Could not create job state")

    application_id = state.application_id
    if state.status == "applied" or state.applied_at is not None:
        if req.action != "apply":
            raise HTTPException(status_code=409, detail="This job is already applied and tracked on your Board")

    if req.action == "save":
        state.status = "saved"
        state.saved_at = now
        state.dismissed_at = None
    elif req.action == "unsave":
        state.status = "viewed"
        state.saved_at = None
    elif req.action == "dismiss":
        state.status = "dismissed"
        state.dismissed_at = now
        state.saved_at = None
    else:
        job = await db.get(AIJob, match.job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Canonical job not found")
        application = await create_application_from_ai_job(job, current_user, db)
        state.status = "applied"
        state.applied_at = state.applied_at or now
        state.dismissed_at = None
        state.application_id = application.id
        application_id = application.id

    state.updated_at = now
    await db.execute(
        update(AIJobMatch)
        .where(
            AIJobMatch.user_id == current_user.id,
            AIJobMatch.job_id == match.job_id,
        )
        .values(status=state.status)
    )
    await db.commit()
    return {
        "message": f"Job status updated to {state.status}",
        "match_id": match_id,
        "job_id": match.job_id,
        "status": state.status,
        "is_saved": state.saved_at is not None,
        "application_id": application_id,
    }
