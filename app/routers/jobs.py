from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.schemas.job import JobCreate, JobResponse, JobUpdate
from app.models.jobs import Job
from app.models.companies import Company
from sqlalchemy import select
from fastapi import HTTPException
from fastapi import APIRouter, Depends, HTTPException
from app.models.applications import Application
from app.models.users import User
from app.dependencies import get_current_user

router = APIRouter(tags=["Jobs"])


# @router.post("/jobs", response_model=JobResponse)
# def create_job(job_data: JobCreate, db: Session = Depends(get_db)):

#     company = db.get(Company, job_data.company_id)

#     if company is None:
#         raise HTTPException(status_code=404, detail="Company not found")

#     new_job = Job(**job_data.model_dump())

#     db.add(new_job)
#     db.commit()
#     db.refresh(new_job)
#     return new_job


@router.get("/jobs", response_model=list[JobResponse])
def get_jobs(db: Session = Depends(get_db)):
    result = db.execute(select(Job))
    jobs = result.scalars().all()

    return jobs

@router.get("/jobs/my", response_model=list[JobResponse])
def get_my_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = db.execute(
        select(Job)
        .join(Application, Application.job_id == Job.id)
        .where(Application.user_id == current_user.id)
    )

    return result.scalars().all()


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
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
