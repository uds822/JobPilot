from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from enum import Enum


class ApplicationStatus(str, Enum):
    APPLIED = "APPLIED"
    INTERVIEWING = "INTERVIEWING"
    OFFERED = "OFFERED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


class ApplicationURLCreate(BaseModel):
    job_url: str = Field(min_length=1)
    status: ApplicationStatus = ApplicationStatus.APPLIED
    notes: str | None = Field(default=None, min_length=1, max_length=10000)


class ApplicationManualCreate(BaseModel):
    company_name: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    location: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=10000)
    job_url: str | None = Field(default=None, min_length=1)
    notes: str | None = Field(default=None, min_length=1, max_length=10000)
    status: ApplicationStatus = ApplicationStatus.APPLIED


class ApplicationURLConfirm(BaseModel):
    job_url: str = Field(min_length=1)
    company_name: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    location: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=10000)
    notes: str | None = Field(default=None, min_length=1, max_length=10000)
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
    job_id: int = Field(gt=0)
    notes: str | None = Field(default=None, min_length=1, max_length=10000)


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
    notes: str | None = Field(default=None, min_length=1, max_length=10000)


class ApplicationPaginatedResponse(BaseModel):
    items: list[ApplicationResponse]
    total: int
    limit: int
    offset: int
    has_more: bool


class KanbanColumnData(BaseModel):
    items: list[ApplicationResponse]
    total: int
    limit: int
    offset: int
    has_more: bool


class KanbanBoardResponse(BaseModel):
    applied: KanbanColumnData
    interviewing: KanbanColumnData
    offered: KanbanColumnData
    rejected: KanbanColumnData
    withdrawn: KanbanColumnData

