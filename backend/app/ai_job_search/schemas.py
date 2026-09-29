from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ResumeProfileSchema(BaseModel):
    skills: List[str] = Field(default_factory=list)
    years_experience: float = 0.0
    recent_titles: List[str] = Field(default_factory=list)
    seniority_level: str = "mid" # entry | mid | senior | lead | exec
    preferred_locations: List[str] = Field(default_factory=list)
    remote_preference: str = "any" # remote | hybrid | onsite | any
    industries: List[str] = Field(default_factory=list)
    preferred_industries: List[str] = Field(default_factory=list)
    preferred_company_types: List[str] = Field(default_factory=list)
    salary_expectation_min: Optional[float] = None
    salary_expectation_max: Optional[float] = None
    salary_currency: Optional[str] = "USD"


class UserPreferencesUpdate(BaseModel):
    years_experience: Optional[float] = None
    preferred_industries: Optional[List[str]] = None
    preferred_company_types: Optional[List[str]] = None
    remote_preference: Optional[str] = None
    target_location: Optional[str] = None
    preferred_locations: Optional[List[str]] = None
    target_company_name: Optional[str] = None
    salary_expectation_min: Optional[float] = None
    salary_expectation_max: Optional[float] = None


class NormalizedJobSchema(BaseModel):
    job_hash: str
    source: str
    external_id: str
    title: str
    company: str
    location: str = "Remote"
    remote: bool = False
    description: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = "USD"
    salary_interval: Optional[str] = "annual"
    salary_source: Optional[str] = "provider"
    apply_url: str
    source_url: Optional[str] = None
    posted_date: Optional[datetime] = None
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True


class JobMatchCardResponse(BaseModel):
    id: int
    match_score: float
    match_level: str
    match_reasoning: Optional[str] = None
    callback_likelihood: str = "medium"
    strengths: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    status: str = "new" # new | saved | dismissed | applied
    is_saved: bool = False
    
    # Sub-factor scores
    skills_overlap: float = 0.0
    experience_fit: float = 0.0
    role_similarity: float = 0.0
    location_fit: float = 0.0
    industry_fit: float = 0.0
    company_type_fit: float = 0.0
    posting_freshness: float = 0.0

    # Embedded job info
    job_id: int
    title: str
    company: str
    location: str
    remote: bool
    description: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = "USD"
    salary_interval: Optional[str] = "annual"
    apply_url: str
    source: str
    posted_date: Optional[datetime] = None
    discovery_channel: str = "Live provider"
    last_seen_at: Optional[datetime] = None
    is_active: bool = True
    is_expired: bool = False
    application_id: Optional[int] = None
    first_shown_at: Optional[datetime] = None
    last_shown_at: Optional[datetime] = None
    show_count: int = 0
    industry: str = "Technology"
    company_type: str = "product"

    class Config:
        from_attributes = True


class SearchRunStatusResponse(BaseModel):
    id: int
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    jobs_fetched: int = 0
    jobs_after_dedupe: int = 0
    jobs_after_validity: int = 0
    jobs_after_hard_filters: int = 0
    jobs_scored: int = 0
    jobs_returned: int = 0

    class Config:
        from_attributes = True


class MatchActionRequest(BaseModel):
    action: str # save | unsave | dismiss | apply
