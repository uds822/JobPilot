from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.database.database import get_db
from app.schemas.company import CompanyCreate, CompanyResponse, CompanyUpdate
from app.models.companies import Company
from app.schemas.job import JobResponse
from app.models.applications import Application
from app.models.jobs import Job
from app.models.users import User
from app.dependencies import get_current_user
from app.exceptions import NotFoundError, ConflictError

router = APIRouter(prefix="/companies", tags=["Companies"])


@router.get("/", response_model=list[CompanyResponse])
def get_companies(
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
):
    return (
        db.query(Company)
        .order_by(Company.name, Company.id)
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/my", response_model=list[CompanyResponse])
def get_my_companies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
):
    result = db.execute(
        select(Company)
        .join(Job, Job.company_id == Company.id)
        .join(Application, Application.job_id == Job.id)
        .where(Application.user_id == current_user.id)
        .distinct()
        .order_by(Company.name, Company.id)
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/{company_id}", response_model=CompanyResponse)
def get_company(company_id: int, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)

    if not company:
        raise NotFoundError("Company not found")

    return company


# @router.patch("/{company_id}", response_model=CompanyResponse)
# def update_company(
#     company_id: int, company_data: CompanyUpdate, db: Session = Depends(get_db)
# ):
#     company = db.get(Company, company_id)

#     if not company:
#         raise HTTPException(status_code=404, detail="Company not found")

#     update_data = company_data.model_dump(exclude_unset=True)

#     if "name" in update_data:
#         existing_company = (
#             db.query(Company)
#             .filter(Company.name == update_data["name"], Company.id != company_id)
#             .first()
#         )
#         if existing_company:
#             raise HTTPException(status_code=400, detail="Company already exists")

#     for key, value in update_data.items():
#         setattr(company, key, value)

#     try:
#         db.commit()
#     except IntegrityError:
#         db.rollback()
#         raise HTTPException(status_code=400, detail="Company already exists")
#     db.refresh(company)

#     return company


# @router.delete("/{company_id}")
# def delete_company(company_id: int, db: Session = Depends(get_db)):
#     company = db.get(Company, company_id)

#     if not company:
#         raise HTTPException(status_code=404, detail="Company not found")

#     if company.jobs:
#         raise HTTPException(
#             status_code=409, detail="Cannot delete a company with associated jobs"
#         )

#     db.delete(company)
#     db.commit()

#     return {"message": "Company deleted successfully"}


# @router.get("/{company_id}/jobs", response_model=list[JobResponse])
# def get_company_jobs(company_id: int, db: Session = Depends(get_db)):
#     company = db.get(Company, company_id)

#     if not company:
#         raise HTTPException(status_code=404, detail="Company not found")

#     return company.jobs
