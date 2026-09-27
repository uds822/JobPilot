from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import get_db
from app.dependencies import get_current_user
from app.exceptions import ConflictError, NotFoundError
from app.models.applications import Application
from app.models.companies import Company
from app.models.jobs import Job
from app.models.users import User
from app.schemas.company import CompanyCreate, CompanyResponse, CompanyUpdate
from app.schemas.job import JobResponse

router = APIRouter(prefix="/companies", tags=["Companies"])


# ── Scalability Rationale (5k-10k Users): ──────────────────────────────────────
# 1. Non-blocking AsyncSession query execution allows event loop to serve concurrent requests.
# 2. Limit/Offset pagination prevents high-memory query buffers during company browsing.
@router.get("/", response_model=list[CompanyResponse])
async def get_companies(
    db: AsyncSession = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
):
    stmt = (
        select(Company)
        .order_by(Company.name, Company.id)
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/my", response_model=list[CompanyResponse])
async def get_my_companies(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
):
    stmt = (
        select(Company)
        .join(Job, Job.company_id == Company.id)
        .join(Application, Application.job_id == Job.id)
        .where(Application.user_id == current_user.id)
        .distinct()
        .order_by(Company.name, Company.id)
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(company_id: int, db: AsyncSession = Depends(get_db)):
    company = await db.get(Company, company_id)

    if not company:
        raise NotFoundError("Company not found")

    return company
