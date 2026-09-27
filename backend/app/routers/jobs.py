from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import get_db
from app.dependencies import get_current_user
from app.exceptions import NotFoundError
from app.models.applications import Application
from app.models.companies import Company
from app.models.jobs import Job
from app.models.users import User
from app.schemas.job import JobCreate, JobResponse, JobUpdate

router = APIRouter(tags=["Jobs"])


# ── Scalability Rationale (5k-10k Users): ──────────────────────────────────────
# 1. async def + AsyncSession: Prevents blocking Uvicorn workers on DB read operations.
# 2. Enforced limit/offset pagination: Protects application & database memory from payload blowup.
@router.get("/jobs", response_model=list[JobResponse])
async def get_jobs(
    db: AsyncSession = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
):
    result = await db.execute(
        select(Job).order_by(Job.id).offset(skip).limit(limit)
    )
    jobs = result.scalars().all()
    return jobs


@router.get("/jobs/my", response_model=list[JobResponse])
async def get_my_jobs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
):
    # Joining with Application filtered by current_user.id guarantees index hit on application.user_id
    stmt = (
        select(Job)
        .join(Application, Application.job_id == Job.id)
        .where(Application.user_id == current_user.id)
        .order_by(Job.id)
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: int, db: AsyncSession = Depends(get_db)):
    # Non-blocking primary key lookup
    job = await db.get(Job, job_id)

    if job is None:
        raise NotFoundError("Job not found")
    return job
