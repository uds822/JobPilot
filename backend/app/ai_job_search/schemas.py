from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, model_validator


class ResumeSkillGroups(BaseModel):
    primary: List[str] = Field(default_factory=list)
    supporting: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    domain: List[str] = Field(default_factory=list)


class ResumeProfileSchema(BaseModel):
    skills: List[str] = Field(default_factory=list)
    skill_groups: ResumeSkillGroups = Field(default_factory=ResumeSkillGroups)
    years_experience: float = 0.0
    recent_titles: List[str] = Field(default_factory=list)
    target_roles: List[str] = Field(default_factory=list)
    seniority_level: str = "mid" # entry | mid | senior | lead | exec
    preferred_locations: List[str] = Field(default_factory=list)
    remote_preference: str = "any" # remote | hybrid | onsite | any
    industries: List[str] = Field(default_factory=list)
    preferred_industries: List[str] = Field(default_factory=list)
    preferred_company_types: List[str] = Field(default_factory=list)
    salary_expectation_min: Optional[float] = None
    salary_expectation_max: Optional[float] = None
    salary_currency: Optional[str] = "USD"
    parse_method: str = "unknown"

    @model_validator(mode="after")
    def reconcile_resume_skills(self):
        group_values = self.skill_groups.model_dump()
        grouped_skills = list(dict.fromkeys(
            skill.strip()
            for values in group_values.values()
            for skill in values
            if skill.strip()
        ))
        if not self.skills and grouped_skills:
            self.skills = grouped_skills
        if not any(group_values.values()) and self.skills:
            tool_names = {
                "aws", "azure", "microsoft azure", "google cloud", "docker",
                "kubernetes", "terraform", "jenkins", "git", "linux",
                "postgresql", "mysql", "mongodb", "redis", "jira",
            }
            tools = [skill for skill in self.skills if skill.lower() in tool_names]
            primary = [skill for skill in self.skills if skill not in tools]
            self.skill_groups = ResumeSkillGroups(primary=primary, tools=tools)
        if not self.target_roles and self.recent_titles:
            self.target_roles = list(dict.fromkeys(self.recent_titles))
        return self


class UserPreferencesUpdate(BaseModel):
    years_experience: Optional[float] = None
    experience_min_years: Optional[float] = Field(default=None, ge=0, le=40)
    experience_max_years: Optional[float] = Field(default=None, ge=0, le=40)
    preferred_industries: Optional[List[str]] = None
    preferred_company_types: Optional[List[str]] = None
    remote_preference: Optional[str] = None
    target_location: Optional[str] = None
    preferred_locations: Optional[List[str]] = None
    target_company_name: Optional[str] = None
    salary_expectation_min: Optional[float] = None
    salary_expectation_max: Optional[float] = None
    new_jobs_limit: Optional[int] = Field(default=None, ge=5, le=50)
    top_matches_limit: Optional[int] = Field(default=None, ge=5, le=50)

    @model_validator(mode="after")
    def validate_job_result_limits(self):
        allowed = {5, 10, 20, 50}
        for value in (self.new_jobs_limit, self.top_matches_limit):
            if value is not None and value not in allowed:
                raise ValueError("Job result limits must be 5, 10, 20 or 50")
        if (
            self.experience_min_years is not None
            and self.experience_max_years is not None
            and self.experience_min_years > self.experience_max_years
        ):
            raise ValueError("Minimum experience cannot exceed maximum experience")
        return self


class NormalizedJobSchema(BaseModel):
    job_hash: str
    source: str
    external_id: str
    title: str
    company: str
    location: str = "Remote"
    remote: bool = False
    description: Optional[str] = None
    description_completeness: str = "unknown"
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
    experience_status: str = "unknown"
    experience_reason: Optional[str] = None
    required_experience_min: Optional[float] = None
    required_experience_max: Optional[float] = None
    experience_source: str = "unknown"
    experience_confidence: float = 0.0
    experience_evidence: Optional[str] = None
    description_completeness: str = "unknown"
    seniority_level: Optional[str] = None
    seniority_conflict: bool = False
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
    search_scope: str = "general"
    company_id: Optional[int] = None
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


class CompanySearchRequest(BaseModel):
    company_id: int = Field(ge=1)


class MatchActionRequest(BaseModel):
    action: str # save | unsave | dismiss | apply


class DeleteAIJobsRequest(BaseModel):
    job_ids: List[int] = Field(default_factory=list, max_length=500)
    delete_all: bool = False

    @model_validator(mode="after")
    def validate_delete_scope(self):
        if self.delete_all == bool(self.job_ids):
            raise ValueError("Provide job_ids or set delete_all, but not both")
        if len(set(self.job_ids)) != len(self.job_ids) or any(job_id <= 0 for job_id in self.job_ids):
            raise ValueError("job_ids must be unique positive integers")
        return self
