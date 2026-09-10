from pydantic import BaseModel, ConfigDict
from datetime import datetime
from enum import Enum

class ApplicationStatus(str, Enum):
    APPLIED = "APPLIED"
    INTERVIEWING = "INTERVIEWING"
    OFFERED = "OFFERED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"

class ApplicationURLCreate(BaseModel):
    job_url: str
    status: ApplicationStatus = ApplicationStatus.APPLIED
    notes: str | None = None

class ApplicationManualCreate(BaseModel):
    company_name: str
    title: str
    location: str | None = None
    description: str | None = None
    job_url: str | None = None
    notes: str | None = None
    status: ApplicationStatus = ApplicationStatus.APPLIED

class ApplicationURLConfirm(BaseModel):
    job_url: str
    company_name: str
    title: str
    location: str | None = None
    description: str | None = None
    notes: str | None = None
    status: ApplicationStatus = ApplicationStatus.APPLIED

# class ApplicationCreate(BaseModel):
#     job_id: int
#     status: ApplicationStatus = ApplicationStatus.APPLIED
#     notes: str | None = None
#     company_name: str | None = None
#     title: str 
#     description: str | None = None
#     location: str | None = None
#     job_url: str | None = None

class ApplicationURLPreview(BaseModel):
    job_url: str
    company_name: str | None = None
    title: str | None = None
    location: str | None = None
    description: str | None = None
    notes: str | None = None
    status: ApplicationStatus = ApplicationStatus.APPLIED

class ApplicationSchema(BaseModel):
    job_id: int
    notes: str | None = None

class ApplicationResponse(BaseModel):
    id: int
    user_id: int
    job_id: int
    status: ApplicationStatus
    applied_at: datetime
    notes: str | None

    model_config = ConfigDict(from_attributes=True)

class ApplicationUpdate(BaseModel):
    status: ApplicationStatus | None = None
    notes: str | None = None
