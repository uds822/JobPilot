from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.schemas.application import (
    ApplicationResponse,
    ApplicationURLCreate,
    ApplicationManualCreate,
    ApplicationURLPreview,
    ApplicationURLConfirm,
    ApplicationUpdate,
    ApplicationPaginatedResponse,
    KanbanBoardResponse,
    ApplicationStatus,
)
from app.models.applications import Application
from app.models.users import User
from app.dependencies import get_current_user
from app.services.application import (
    create_application_from_url,
    create_application_manual,
    confirm_application_from_url,
    get_user_applications_paginated,
    get_kanban_board_data,
)
from app.services.job_scraper_service import scrape_job
from app.exceptions import BadRequestError, ConflictError, NotFoundError
from fastapi import Query, Request
from app.middleware.rate_limit import check_rate_limit

router = APIRouter(prefix="/applications", tags=["Applications"])


@router.post("/url/preview", response_model=ApplicationURLPreview)
def preview_application_from_url(
    request: Request,
    data: ApplicationURLCreate,
    current_user: User = Depends(get_current_user),
):
    client_ip = request.client.host
    check_rate_limit(
        key=f"rate_limit:application_url:{client_ip}",
        limit=10,
        window_seconds=60,
    )

    try:
        job_data = scrape_job(data.job_url)

        return ApplicationURLPreview(
            job_url=data.job_url,
            company_name=job_data.get("company"),
            title=job_data.get("title"),
            location=job_data.get("location"),
            description=job_data.get("description"),
        )
    except Exception as e:
        raise BadRequestError(f"Could not scrape job page: {str(e)}")


@router.post("/url/confirm", response_model=ApplicationResponse)
def confirm_application_from_url_endpoint(
    data: ApplicationURLConfirm,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return confirm_application_from_url(
            data=data,
            current_user=current_user,
            db=db,
        )
    except (ValueError, ConflictError, BadRequestError) as e:
        raise ConflictError(str(e)) if isinstance(e, ValueError) else e


@router.post("/manual", response_model=ApplicationResponse)
def add_application_manual(
    data: ApplicationManualCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return create_application_manual(
            data=data,
            current_user=current_user,
            db=db,
        )
    except (ValueError, ConflictError, BadRequestError) as e:
        raise ConflictError(str(e)) if isinstance(e, ValueError) else e


@router.get("/kanban", response_model=KanbanBoardResponse)
def get_kanban_board(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit_per_status: int = Query(default=20, ge=1, le=100),
):
    """
    Fetch initial batch (first 20) + total counts for each Kanban status column.
    """
    return get_kanban_board_data(
        db=db,
        current_user=current_user,
        limit_per_status=limit_per_status,
    )


@router.get("", response_model=ApplicationPaginatedResponse)
def get_my_applications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    status: ApplicationStatus | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    skip: int | None = None,
):
    """
    Fetch paginated applications for current user, optionally filtered by status.
    """
    actual_offset = offset if skip is None else skip
    return get_user_applications_paginated(
        db=db,
        current_user=current_user,
        status=status.value if status else None,
        limit=limit,
        offset=actual_offset,
    )


@router.get("/{application_id}", response_model=ApplicationResponse)
def get_application(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    application = (
        db.query(Application)
        .filter(
            Application.id == application_id,
            Application.user_id == current_user.id,
        )
        .first()
    )

    if application is None:
        raise NotFoundError("Application not found")

    return application


@router.patch("/{application_id}", response_model=ApplicationResponse)
def update_application(
    application_id: int,
    data: ApplicationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    application = (
        db.query(Application)
        .filter(
            Application.id == application_id,
            Application.user_id == current_user.id,
        )
        .first()
    )

    if application is None:
        raise NotFoundError("Application not found")

    if data.status is not None:
        application.status = data.status

    if data.notes is not None:
        application.notes = data.notes

    db.commit()
    db.refresh(application)

    return application


@router.delete("/{application_id}")
def delete_application(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    application = (
        db.query(Application)
        .filter(
            Application.id == application_id,
            Application.user_id == current_user.id,
        )
        .first()
    )

    if application is None:
        raise NotFoundError("Application not found")

    db.delete(application)
    db.commit()

    return {"message": "Application deleted successfully"}
