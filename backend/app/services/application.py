from sqlalchemy import delete, select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.applications import Application
from app.models.companies import Company
from app.models.jobs import Job
from app.models.users import User

from app.schemas.application import (
    ApplicationURLCreate,
    ApplicationManualCreate,
    ApplicationURLConfirm,
    ApplicationStatus,
    BulkDeleteRequest,
)

from app.services.job_scraper_service import scrape_job
from app.exceptions import (
    BadRequestError,
    ConflictError,
)
from app.core.request_context import request_id_context

import logging

# Python automatically fills in __name__ with the file's name (e.g., "application_service"). This tells Python: "Whenever this file emits a message, tag it with this file's name so we know where it came from."
logger = logging.getLogger(__name__)
request_id=request_id_context.get()

async def create_application_from_url(
    data: ApplicationURLCreate,
    current_user: User,
    db: AsyncSession,
):
    """
    Create an application from a job URL.

    The URL is scraped first to extract:
    - company
    - title
    - location
    - description

    Then the company/job/application are created or reused.
    """

    job_data = await scrape_job(data.job_url)  # await: async HTTP → non-blocking

    # Validate scraped data
    company_name = job_data.get("company")
    title = job_data.get("title")

    if not company_name or not company_name.strip():
        raise BadRequestError("Could not extract company name from URL")

    if not title or not title.strip():
        raise BadRequestError("Could not extract job title from URL")

    return await _create_application(
        company_name=company_name,
        title=title,
        location=job_data.get("location"),
        description=job_data.get("description"),
        job_url=data.job_url,
        status=data.status,
        notes=data.notes,
        current_user=current_user,
        db=db,
    )


async def create_application_manual(
    data: ApplicationManualCreate,
    current_user: User,
    db: AsyncSession,
):
    """
    Create an application using manually entered job details.
    """

    return await _create_application(
        company_name=data.company_name,
        title=data.title,
        location=data.location,
        description=data.description,
        job_url=data.job_url,
        status=data.status,
        notes=data.notes,
        current_user=current_user,
        db=db,
    )


async def confirm_application_from_url(
    data: ApplicationURLConfirm,
    current_user: User,
    db: AsyncSession,
):
    """
    Create an application after the user has reviewed and confirmed
    the scraped job information.
    """

    return await _create_application(
        company_name=data.company_name,
        title=data.title,
        location=data.location,
        description=data.description,
        job_url=data.job_url,
        status=data.status,
        notes=data.notes,
        current_user=current_user,
        db=db,
    )


async def create_application_from_ai_job(
    ai_job,
    current_user: User,
    db: AsyncSession,
):
    """Idempotently add a canonical AI job to the existing tracking board."""
    existing = await db.scalar(
        select(Application)
        .join(Job, Job.id == Application.job_id)
        .where(
            Application.user_id == current_user.id,
            Job.job_url == ai_job.apply_url,
        )
        .limit(1)
    )
    if existing is not None:
        return existing

    return await _create_application(
        company_name=ai_job.company,
        title=ai_job.title,
        location=ai_job.location,
        description=ai_job.description,
        job_url=ai_job.apply_url,
        status=ApplicationStatus.APPLIED,
        notes="Added from AI Job Search",
        current_user=current_user,
        db=db,
        commit=False,
    )


async def _create_application(
    company_name: str,
    title: str,
    location: str | None,
    description: str | None,
    job_url: str | None,
    status: ApplicationStatus,
    notes: str | None,
    current_user: User,
    db: AsyncSession,
    commit: bool = True,
):
    """
    Shared application creation logic.

    Flow:

        Validate input
            ↓
        Find/Create Company
            ↓
        Find/Create Job
            ↓
        Check duplicate Application
            ↓
        Create Application
            ↓
        Commit transaction
    """

    # ---------------------------------------------------------
    # 1. Validate required fields
    # ---------------------------------------------------------

    company_name = company_name.strip()
    title = title.strip()

    if not company_name:
        raise BadRequestError("Company name is required")

    if not title:
        raise BadRequestError("Job title is required")

    try:
        # -----------------------------------------------------
        # 2. Find or create company
        # -----------------------------------------------------

        result = await db.execute(
            select(Company).where(Company.name == company_name)
        )
        company = result.scalar_one_or_none()

        if company is None:
            company = Company(name=company_name)
            db.add(company)       # db.add is sync — just registers in session memory
            await db.flush()      # flush sends INSERT to DB so company.id is populated

        # -----------------------------------------------------
        # 3. Find existing job
        # -----------------------------------------------------

        job = None

        if job_url:
            result = await db.execute(
                select(Job).where(Job.job_url == job_url)
            )
            job = result.scalar_one_or_none()

        # -----------------------------------------------------
        # 4. Create job if it doesn't exist
        # -----------------------------------------------------

        if job is None:
            new_job = Job(
                title=title,
                company_id=company.id,
                location=location,
                description=description,
                job_url=job_url,
            )

            try:
                # async with: begin_nested creates a DB savepoint (network I/O)
                # Savepoint protects us from a race condition
                # where another request creates the same job URL.
                async with db.begin_nested():
                    db.add(new_job)
                    await db.flush()

                job = new_job

            except IntegrityError:
                # Another request may have created this URL
                # between our SELECT and INSERT.
                if job_url:
                    result = await db.execute(
                        select(Job).where(Job.job_url == job_url)
                    )
                    job = result.scalar_one_or_none()

                if job is None:
                    raise BadRequestError("Could not create or find the job.")

        # -----------------------------------------------------
        # 5. Check duplicate application
        # -----------------------------------------------------

        result = await db.execute(
            select(Application).where(
                Application.user_id == current_user.id,
                Application.job_id == job.id,
            )
        )
        existing_application = result.scalar_one_or_none()

        if existing_application:
            raise ConflictError("You have already applied to this job.")

        # -----------------------------------------------------
        # 6. Create application
        # -----------------------------------------------------

        application = Application(
            user_id=current_user.id,
            job_id=job.id,
            status=status,
            notes=notes,
        )

        try:
            # Database constraint:
            # uq_user_job_application
            async with db.begin_nested():
                db.add(application)
                await db.flush()

        except IntegrityError:
            raise ConflictError("You have already applied to this job.")

        # -----------------------------------------------------
        # 7. Commit transaction
        # -----------------------------------------------------

        if commit:
            await db.commit()
            await db.refresh(application)
        else:
            await db.flush()
        logger.info(
            "Application created successfully | user_id=%s | job_id=%s | application_id=%s",
            current_user.id,
            job.id,
            application.id,
        )
        return application

    except (BadRequestError, ConflictError):
        await db.rollback()
        raise


async def get_user_applications_paginated(
    db: AsyncSession,
    current_user: User,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """
    Fetch paginated applications for the authenticated user, optionally filtered by status.
    Enforces a strict server-side maximum limit of 100.
    """
    safe_limit = min(max(1, limit), 100)
    safe_offset = max(0, offset)

    # Build the base statement — not executed yet, just a query object
    base_stmt = select(Application).where(Application.user_id == current_user.id)

    if status:
        base_stmt = base_stmt.where(Application.status == status)

    # COUNT: wrap the base query as a subquery and count its rows
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total = await db.scalar(count_stmt)   # scalar() = one single value

    # FETCH: add ordering + pagination then execute
    items_stmt = (
        base_stmt
        .order_by(Application.applied_at.desc(), Application.id.desc())
        .offset(safe_offset)
        .limit(safe_limit)
    )
    result = await db.execute(items_stmt)
    items = result.scalars().all()        # scalars() unwraps rows → list of objects

    has_more = (safe_offset + len(items)) < total

    return {
        "items": items,
        "total": total,
        "limit": safe_limit,
        "offset": safe_offset,
        "has_more": has_more,
    }


async def get_kanban_board_data(
    db: AsyncSession,
    current_user: User,
    limit_per_status: int = 20,
) -> dict:
    """Fetch each Board column using the request's database session."""
    statuses = ["APPLIED", "INTERVIEWING", "OFFERED", "REJECTED", "WITHDRAWN"]

    # An AsyncSession cannot execute concurrent queries.
    results = [
        await get_user_applications_paginated(
            db=db,
            current_user=current_user,
            status=s,
            limit=limit_per_status,
            offset=0,
        )
        for s in statuses
    ]

    return {
        status.lower(): data
        for status, data in zip(statuses, results)
    }

async def delete_applications_bulk(
    db: AsyncSession,
    current_user: User,
    application_ids: list[int],
) -> int:
    result = await db.execute(
        delete(Application).where(
            Application.user_id == current_user.id,
            Application.id.in_(application_ids)
        )
    )
    await db.commit()
    return result.rowcount
