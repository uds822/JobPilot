from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.applications import Application
from app.models.companies import Company
from app.models.jobs import Job
from app.models.users import User

from app.schemas.application import (
    ApplicationURLCreate,
    ApplicationManualCreate,
    ApplicationURLConfirm,
    ApplicationStatus,
)

from app.services.job_scraper_service import scrape_job


def create_application_from_url(
    data: ApplicationURLCreate,
    current_user: User,
    db: Session,
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

    job_data = scrape_job(data.job_url)

    # Validate scraped data
    company_name = job_data.get("company")
    title = job_data.get("title")

    if not company_name or not company_name.strip():
        raise ValueError("Could not extract company name from URL")

    if not title or not title.strip():
        raise ValueError("Could not extract job title from URL")

    return _create_application(
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


def create_application_manual(
    data: ApplicationManualCreate,
    current_user: User,
    db: Session,
):
    """
    Create an application using manually entered job details.
    """

    return _create_application(
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


def confirm_application_from_url(
    data: ApplicationURLConfirm,
    current_user: User,
    db: Session,
):
    """
    Create an application after the user has reviewed and confirmed
    the scraped job information.
    """

    return _create_application(
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

def _create_application(
    company_name: str,
    title: str,
    location: str | None,
    description: str | None,
    job_url: str | None,
    status: ApplicationStatus,
    notes: str | None,
    current_user: User,
    db: Session,
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
        raise ValueError("Company name is required")

    if not title:
        raise ValueError("Job title is required")

    try:
        # -----------------------------------------------------
        # 2. Find or create company
        # -----------------------------------------------------

        company = (
            db.query(Company)
            .filter(Company.name == company_name)
            .first()
        )

        if company is None:
            company = Company(name=company_name)
            db.add(company)
            db.flush()

        # -----------------------------------------------------
        # 3. Find existing job
        # -----------------------------------------------------

        job = None

        if job_url:
            job = (
                db.query(Job)
                .filter(Job.job_url == job_url)
                .first()
            )

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
                # Savepoint protects us from a race condition
                # where another request creates the same job URL.
                with db.begin_nested():
                    db.add(new_job)
                    db.flush()

                job = new_job

            except IntegrityError:
                # Another request may have created this URL
                # between our SELECT and INSERT.
                if job_url:
                    job = (
                        db.query(Job)
                        .filter(Job.job_url == job_url)
                        .first()
                    )

                if job is None:
                    raise ValueError(
                        "Could not create or find the job."
                    )

        # -----------------------------------------------------
        # 5. Check duplicate application
        # -----------------------------------------------------

        existing_application = (
            db.query(Application)
            .filter(
                Application.user_id == current_user.id,
                Application.job_id == job.id,
            )
            .first()
        )

        if existing_application:
            raise ValueError(
                "You have already applied to this job."
            )

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
            with db.begin_nested():
                db.add(application)
                db.flush()

        except IntegrityError:
            raise ValueError(
                "You have already applied to this job."
            )

        # -----------------------------------------------------
        # 7. Commit transaction
        # -----------------------------------------------------

        db.commit()
        db.refresh(application)

        return application

    except ValueError:
        db.rollback()
        raise
