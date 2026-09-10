from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.schemas.application import  ApplicationResponse, ApplicationURLCreate, ApplicationManualCreate,ApplicationURLPreview, ApplicationURLConfirm, ApplicationUpdate
from app.models.applications import Application
from app.models.companies import Company
from app.models.users import User
from app.dependencies import get_current_user
from app.services.application import create_application_from_url, create_application_manual
# from app.services.application import _create_application
from app.services.job_scraper_service import scrape_job
from app.services.application import confirm_application_from_url

router = APIRouter(prefix="/applications", tags=["Applications"])

@router.post("/url/preview", response_model=ApplicationURLPreview)
def preview_application_from_url(
    data: ApplicationURLCreate,
    current_user: User = Depends(get_current_user),
):
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
        raise HTTPException(
            status_code=400,
            detail=f"Could not scrape job page: {str(e)}"
        )
    
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

    except ValueError as e:
        raise HTTPException(
            status_code=409,
            detail=str(e)
        )
    
# @router.post("", response_model=ApplicationResponse)
# def create_application_endpoint(
#     application_data: ApplicationCreate,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db),
# ):
#     return _create_application(application_data, current_user, db)


# @router.post("/url", response_model=ApplicationResponse)
# def add_application_from_url(
#     data: ApplicationURLCreate,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user)
# ):
#     return create_application_from_url(
#         data=data,
#         current_user=current_user,
#         db=db,
#     )


@router.post("/manual", response_model=ApplicationResponse)
def add_application_manual(
    data: ApplicationManualCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        return create_application_manual(
            data=data,
            current_user=current_user,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=409,
            detail=str(e)
        )

@router.get("", response_model=list[ApplicationResponse])
def get_my_applications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    
    return (
        db.query(Application)
        .filter(Application.user_id == current_user.id)
        .all()
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
        raise HTTPException(
            status_code=404,
            detail="Application not found"
        )

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
        raise HTTPException(
            status_code=404,
            detail="Application not found"
        )

    if data.status is not None:
        application.status = data.status

    if data.notes is not None:
        application.notes = data.notes

    db.commit()
    db.refresh(application)

    return application

#delete application

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
        raise HTTPException(
            status_code=404,
            detail="Application not found"
        )

    db.delete(application)
    db.commit()

    return {
        "message": "Application deleted successfully"
    }