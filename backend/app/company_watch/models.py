from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base


class CompanyIntelligence(Base):
    __tablename__ = "company_intelligence"

    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True
    )
    company_type: Mapped[str | None] = mapped_column(String(40))
    sub_industry: Mapped[str | None] = mapped_column(String(100))
    size_bucket: Mapped[str | None] = mapped_column(String(30))
    careers_url: Mapped[str | None] = mapped_column(Text)
    discovery_status: Mapped[str] = mapped_column(String(30), default="discovery_pending", nullable=False)
    discovery_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_discovery_at: Mapped[datetime | None] = mapped_column(DateTime)
    next_discovery_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    discovery_error: Mapped[str | None] = mapped_column(Text)
    discovery_claim_token: Mapped[str | None] = mapped_column(String(36))
    discovery_claimed_until: Mapped[datetime | None] = mapped_column(DateTime)
    priority_tier: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    india_hiring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    remote_india: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    engineering_relevance: Mapped[float] = mapped_column(
        Float, default=1.0, nullable=False
    )
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint("priority_tier BETWEEN 1 AND 3", name="ck_company_intelligence_priority"),
        CheckConstraint(
            "engineering_relevance BETWEEN 0 AND 1",
            name="ck_company_intelligence_relevance",
        ),
        Index("ix_company_discovery_due", "is_active", "next_discovery_at", "discovery_claimed_until"),
    )


class CompanyAlias(Base):
    __tablename__ = "company_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alias: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    source: Mapped[str | None] = mapped_column(String(50))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )


class CompanyLocation(Base):
    __tablename__ = "company_locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    country: Mapped[str] = mapped_column(String(80), nullable=False)
    region: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(100))
    location_type: Mapped[str] = mapped_column(String(30), default="office", nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "company_id", "country", "region", "city", "location_type",
            name="uq_company_locations_identity",
        ),
    )


class CompanySource(Base):
    __tablename__ = "company_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    identifier: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_url: Mapped[str | None] = mapped_column(Text)
    canonical_identity: Mapped[str | None] = mapped_column(String(300))
    ownership_status: Mapped[str] = mapped_column(String(30), default="registry_trusted", nullable=False)
    discovery_evidence: Mapped[dict | None] = mapped_column(JSON)
    last_observed_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_complete_scope: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default="unverified", nullable=False)
    managed_by_existing_provider: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_job_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_ingested_at: Mapped[datetime | None] = mapped_column(DateTime)
    next_check_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    next_verify_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    poll_interval_minutes: Mapped[int] = mapped_column(Integer, default=360, nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_http_status: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)
    claim_token: Mapped[str | None] = mapped_column(String(36))
    claimed_until: Mapped[datetime | None] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("provider", "identifier", name="uq_company_sources_provider_identifier"),
        UniqueConstraint("canonical_identity", name="uq_company_sources_canonical_identity"),
        CheckConstraint("poll_interval_minutes > 0", name="ck_company_sources_poll_interval"),
        Index("ix_company_sources_due", "is_active", "next_check_at", "claimed_until"),
        Index("ix_company_sources_verify_due", "is_active", "next_verify_at", "claimed_until"),
    )


class CompanyWatchRun(Base):
    __tablename__ = "company_watch_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    sources_claimed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sources_successful: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sources_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    raw_jobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    india_jobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_inserted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    persistence_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)


class CompanySourceCheck(Base):
    __tablename__ = "company_source_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_source_id: Mapped[int] = mapped_column(
        ForeignKey("company_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("company_watch_runs.id", ondelete="SET NULL"), index=True
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    jobs_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    india_jobs_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)


class CompanyDiscoveryAttempt(Base):
    __tablename__ = "company_discovery_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    evidence: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
