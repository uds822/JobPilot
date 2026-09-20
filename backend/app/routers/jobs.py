from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.database.database import get_db
from app.schemas.job import JobCreate, JobResponse, JobUpdate
from app.models.jobs import Job
from app.models.companies import Company
from app.models.applications import Application
from app.models.users import User
from app.dependencies import get_current_user
from app.exceptions import NotFoundError

router = APIRouter(tags=["Jobs"])


@router.get("/jobs", response_model=list[JobResponse])
def get_jobs(
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
):
    result = db.execute(select(Job).order_by(Job.id).offset(skip).limit(limit))
    jobs = result.scalars().all()

    return jobs


@router.get("/jobs/my", response_model=list[JobResponse])
def get_my_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
):
    result = db.execute(
        select(Job)
        .join(Application, Application.job_id == Job.id)
        .where(Application.user_id == current_user.id)
        .order_by(Job.id)
        .offset(skip)
        .limit(limit)
    )

    return result.scalars().all()


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)

    if job is None:
        raise NotFoundError("Job not found")
    return job


# @router.delete("/jobs/{job_id}")
# def delete_job(job_id: int, db: Session = Depends(get_db)):
#     job = db.get(Job, job_id)

#     if job is None:
#         raise HTTPException(status_code=404, detail="Job not found")

#     db.delete(job)
#     db.commit()
#     return {"message": "Job deleted successfully"}


# @router.patch("/jobs/{job_id}", response_model=JobResponse)
# def update_job(job_id: int, job_data: JobUpdate, db: Session = Depends(get_db)):

#     job = db.get(Job, job_id)

#     if job is None:
#         raise HTTPException(status_code=404, detail="Job not found")

#     update_data = job_data.model_dump(exclude_unset=True)

#     if "company_id" in update_data:
#         company = db.get(Company, update_data["company_id"])
#         if company is None:
#             raise HTTPException(status_code=404, detail="Company not found")

#     for key, value in update_data.items():
#         setattr(job, key, value)

#     db.commit()
#     db.refresh(job)
#     return job
