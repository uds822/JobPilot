from datetime import datetime
from typing import Optional, Any, Dict, List
from sqlalchemy import CheckConstraint, String, Text, Boolean, Float, Integer, DateTime, ForeignKey, Index, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.database import Base


class AIJob(Base):
    """Canonical external job listing collected across providers."""
    __tablename__ = "ai_canonical_jobs"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_ai_jobs_source_external_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_hash: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(50), index=True) # adzuna, greenhouse, lever, etc.
    external_id: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(255), index=True)
    company: Mapped[str] = mapped_column(String(255), index=True)
    location: Mapped[str] = mapped_column(String(255), default="Remote")
    remote: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    salary_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    salary_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    salary_currency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, default="USD")
    salary_interval: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default="annual")
    salary_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default="provider")
    
    apply_url: Mapped[str] = mapped_column(Text)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    posted_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    verification_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    missing_poll_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    inventory_scope: Mapped[str] = mapped_column(String(80), default="india_technical_v1", nullable=False)
    ingestion_source_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("company_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    matches = relationship("AIJobMatch", back_populates="job", cascade="all, delete-orphan")


class CompanyProfileCache(Base):
    """Cached company classification and salary estimate data."""
    __tablename__ = "company_profiles_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    industry: Mapped[str] = mapped_column(String(100), default="Technology")
    company_type: Mapped[str] = mapped_column(String(50), default="other") # startup | product | services | consulting | enterprise | other
    confidence: Mapped[float] = mapped_column(Float, default=0.8)
    salary_estimates: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserResumeProfile(Base):
    """Parsed user resume profile & preferences."""
    __tablename__ = "user_resume_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    raw_resume_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parsed_profile: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    user_preferences: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    matches = relationship("AIJobMatch", back_populates="profile", cascade="all, delete-orphan")
    runs = relationship("SearchRun", back_populates="profile", cascade="all, delete-orphan")


class SearchRun(Base):
    """Metadata tracking a single AI job discovery execution."""
    __tablename__ = "search_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    profile_version_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("user_resume_profiles.id"), nullable=True)
    
    status: Mapped[str] = mapped_column(String(20), default="queued") # queued | running | completed | failed
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    jobs_fetched: Mapped[int] = mapped_column(Integer, default=0)
    jobs_after_dedupe: Mapped[int] = mapped_column(Integer, default=0)
    jobs_after_validity: Mapped[int] = mapped_column(Integer, default=0)
    jobs_after_hard_filters: Mapped[int] = mapped_column(Integer, default=0)
    jobs_scored: Mapped[int] = mapped_column(Integer, default=0)
    jobs_returned: Mapped[int] = mapped_column(Integer, default=0)

    profile = relationship("UserResumeProfile", back_populates="runs")
    matches = relationship("AIJobMatch", back_populates="search_run", cascade="all, delete-orphan")


class AIJobMatch(Base):
    """Scored match between a user's resume profile and a canonical AI job."""
    __tablename__ = "ai_job_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    search_run_id: Mapped[int] = mapped_column(Integer, ForeignKey("search_runs.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    profile_version_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("user_resume_profiles.id"), nullable=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_canonical_jobs.id"), index=True)

    match_score: Mapped[float] = mapped_column(Float) # 0 to 100
    match_level: Mapped[str] = mapped_column(String(30), default="Good match") # Strong match | Good match
    callback_likelihood: Mapped[str] = mapped_column(String(20), default="medium") # high | medium | low
    match_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    strengths: Mapped[List[str]] = mapped_column(JSON, default=list)
    gaps: Mapped[List[str]] = mapped_column(JSON, default=list)
    
    # Sub-factor breakdown
    skills_overlap: Mapped[float] = mapped_column(Float, default=0.0)
    experience_fit: Mapped[float] = mapped_column(Float, default=0.0)
    role_similarity: Mapped[float] = mapped_column(Float, default=0.0)
    location_fit: Mapped[float] = mapped_column(Float, default=0.0)
    industry_fit: Mapped[float] = mapped_column(Float, default=0.0)
    company_type_fit: Mapped[float] = mapped_column(Float, default=0.0)
    posting_freshness: Mapped[float] = mapped_column(Float, default=0.0)

    status: Mapped[str] = mapped_column(String(20), default="new") # new | saved | dismissed | applied
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job = relationship("AIJob", back_populates="matches")
    profile = relationship("UserResumeProfile", back_populates="matches")
    search_run = relationship("SearchRun", back_populates="matches")


class UserJobState(Base):
    """Durable per-user state for a canonical external posting."""

    __tablename__ = "ai_user_job_states"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_ai_user_job_state_user_job"),
        CheckConstraint(
            "status IN ('viewed', 'saved', 'dismissed', 'applied')",
            name="ck_ai_user_job_state_status",
        ),
        Index("ix_ai_user_job_states_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("ai_canonical_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), default="viewed", nullable=False)
    first_shown_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    last_shown_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    show_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    saved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    dismissed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    application_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("applications.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
