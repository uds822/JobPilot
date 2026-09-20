from pydantic import BaseModel, ConfigDict, Field

from enum import Enum


class JobStatus(str, Enum):
    SAVED = "SAVED"
    APPLIED = "APPLIED"
    INTERVIEWING = "INTERVIEWING"
    OFFERED = "OFFERED"
    REJECTED = "REJECTED"


class JobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    company_id: int = Field(gt=0)
    location: str | None = Field(default=None, max_length=200)
    job_url: str | None = None
    description: str | None = Field(default=None, max_length=10000)
    employment_type: str | None = Field(default=None, max_length=50)


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
    title: str | None = Field(default=None, min_length=1, max_length=200)
    company_id: int | None = Field(default=None, gt=0)
    location: str | None = Field(default=None, max_length=200)
    job_url: str | None = None
    description: str | None = Field(default=None, max_length=10000)
    employment_type: str | None = Field(default=None, max_length=50)
    status: JobStatus | None = None
