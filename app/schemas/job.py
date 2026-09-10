from pydantic import BaseModel, ConfigDict

from enum import Enum


class JobStatus(str, Enum):
    SAVED = "SAVED"
    APPLIED = "APPLIED"
    INTERVIEWING = "INTERVIEWING"
    OFFERED = "OFFERED"
    REJECTED = "REJECTED"


class JobCreate(BaseModel):
    title: str
    company_id: int
    location: str | None = None
    job_url: str | None = None
    description: str | None = None
    employment_type: str | None = None


class JobResponse(BaseModel):
    id: int
    title: str
    company_id: int
    location: str | None
    job_url: str | None
    description: str | None
    employment_type: str | None
    status: JobStatus

    model_config = ConfigDict(from_attributes=True)


class JobUpdate(BaseModel):
    title: str | None = None
    company_id: int | None = None
    location: str | None = None
    job_url: str | None = None
    description: str | None = None
    employment_type: str | None = None
    status: JobStatus | None = None
