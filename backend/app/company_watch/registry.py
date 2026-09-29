"""Validated bootstrap import into the existing employer and source tables."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_job_search.providers.ats_registry import SOURCE_DISCOVERY_COMPANIES, VERIFIED_ATS_SOURCES
from app.company_watch.models import CompanyAlias, CompanyIntelligence, CompanyLocation, CompanySource
from app.company_watch.providers import SUPPORTED_PROVIDERS, source_url
from app.company_watch.detection import canonical_identity
from app.models.companies import Company

DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[3] / "company_registry.json"


def normalized_alias(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def validate_url(value: str | None) -> str | None:
    if value is not None:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Registry links must be absolute HTTPS URLs without credentials")
    return value


class RegistryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SourceSeed(RegistryModel):
    provider: str = Field(min_length=1, max_length=40)
    identifier: str = Field(min_length=1, max_length=200)
    source_url: str | None = None
    evidence_url: str | None = None

    _urls = field_validator("source_url", "evidence_url")(validate_url)

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        return value.lower()


class OfficeSeed(RegistryModel):
    country: str = Field(min_length=1, max_length=80)
    region: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)


class CompanySeed(RegistryModel):
    name: str = Field(min_length=1, max_length=100)
    aliases: list[str] = Field(default_factory=list)
    website_url: str | None = None
    careers_url: str | None = None
    categories: list[str] = Field(default_factory=list)
    industry: str | None = Field(default=None, max_length=100)
    priority_tier: int = Field(default=2, ge=1, le=3)
    office_locations: list[OfficeSeed] = Field(default_factory=list)
    sources: list[SourceSeed] = Field(default_factory=list)

    _urls = field_validator("website_url", "careers_url")(validate_url)

    @field_validator("aliases", "categories")
    @classmethod
    def validate_labels(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(value.strip() for value in values))
        if any(not normalized_alias(value) or len(value) > 200 for value in cleaned):
            raise ValueError("Registry aliases and categories must be nonempty labels of at most 200 characters")
        return cleaned


class RegistryDocument(RegistryModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    companies: list[CompanySeed]


def canonicalize_registry(document: RegistryDocument) -> list[CompanySeed]:
    grouped: dict[str, CompanySeed] = {}
    for entry in document.companies:
        identity = normalized_alias(entry.name)
        if not identity:
            raise ValueError("Company must have a meaningful name")
        if identity in grouped:
            current = grouped[identity]
            for label in ("aliases", "categories"):
                setattr(current, label, list(dict.fromkeys([*getattr(current, label), *getattr(entry, label)])))
            current.sources.extend(entry.sources)
            current.office_locations.extend(entry.office_locations)
            for field in ("website_url", "careers_url", "industry"):
                if not getattr(current, field):
                    setattr(current, field, getattr(entry, field))
        else:
            grouped[identity] = entry.model_copy(deep=True)
    alias_owners: dict[str, str] = {}
    source_owners: dict[tuple[str, str], str] = {}
    for identity, entry in grouped.items():
        for alias in [entry.name, *entry.aliases]:
            normalized = normalized_alias(alias)
            if normalized in alias_owners and alias_owners[normalized] != identity:
                raise ValueError(f"Ambiguous company alias: {alias}")
            alias_owners[normalized] = identity
        sources = {}
        for source in entry.sources:
            key = (source.provider, source.identifier)
            if key in source_owners and source_owners[key] != identity:
                raise ValueError(f"Source has conflicting employer ownership: {key}")
            source_owners[key] = identity
            if source.provider in {"greenhouse", "lever", "ashby"}:
                expected = urlparse(source_url(*key))
                supplied = urlparse(source.source_url) if source.source_url else expected
                if (supplied.hostname, supplied.path, supplied.port) != (expected.hostname, expected.path, expected.port):
                    raise ValueError(f"Source URL does not match its provider and identifier: {key}")
            elif not source.source_url:
                raise ValueError("Additional providers require a source URL")
            if key in sources:
                current_source = sources[key]
                current_source.source_url = current_source.source_url or source.source_url
                current_source.evidence_url = current_source.evidence_url or source.evidence_url
            else:
                sources[key] = source
        entry.sources = list(sources.values())
    return list(grouped.values())


def load_registry(path: str | Path | None = None) -> RegistryDocument:
    file = Path(path) if path is not None else DEFAULT_REGISTRY_PATH
    document = RegistryDocument.model_validate(json.loads(file.read_text(encoding="utf-8-sig")))
    if path is None:
        # Python lists remain supplementary bootstrap targets, never runtime routing.
        document.companies.extend(
            CompanySeed(name=item["company"], categories=[item["category"]])
            for item in SOURCE_DISCOVERY_COMPANIES
        )
        for provider, entries in VERIFIED_ATS_SOURCES.items():
            for item in entries:
                identifier = item.get("board") or item.get("site")
                document.companies.append(CompanySeed(
                    name=item["company"],
                    sources=[SourceSeed(provider=provider, identifier=identifier)],
                ))
    # Validate ownership and consolidate duplicates before any database mutation.
    document.companies = canonicalize_registry(document)
    return document


async def register_companies(db: AsyncSession, document: RegistryDocument) -> dict[str, int]:
    entries = canonicalize_registry(document)
    # Serialize bootstrap imports without changing the existing case-sensitive name constraint.
    await db.execute(select(func.pg_advisory_xact_lock(1000006)))
    companies = (await db.execute(select(Company))).scalars().all()
    aliases = (await db.execute(select(CompanyAlias))).scalars().all()
    sources = (await db.execute(select(CompanySource))).scalars().all()
    intelligence = {row.company_id: row for row in (await db.execute(select(CompanyIntelligence))).scalars()}
    offices = (await db.execute(select(CompanyLocation))).scalars().all()
    owners: dict[str, Company] = {}
    companies_by_id = {company.id: company for company in companies}
    for company in companies:
        identity = normalized_alias(company.name)
        if identity in owners and owners[identity].id != company.id:
            raise ValueError(f"Existing companies have conflicting normalized names: {company.name}")
        owners[identity] = company
    aliases_by_key = {alias.normalized_alias: alias for alias in aliases}
    for alias in aliases:
        owner = companies_by_id[alias.company_id]
        if alias.normalized_alias in owners and owners[alias.normalized_alias].id != owner.id:
            raise ValueError(f"Existing alias has conflicting ownership: {alias.alias}")
        owners[alias.normalized_alias] = owner
    sources_by_key = {(source.provider, source.identifier): source for source in sources}
    office_keys = {(loc.company_id, loc.country, loc.region, loc.city, loc.location_type) for loc in offices}
    new_companies = new_sources = 0
    registered_ids = set()
    for entry in entries:
        identities = {normalized_alias(name) for name in [entry.name, *entry.aliases]}
        candidates = {owners[name].id for name in identities if name in owners}
        candidates.update(sources_by_key[(source.provider, source.identifier)].company_id for source in entry.sources if (source.provider, source.identifier) in sources_by_key)
        if len(candidates) > 1:
            raise ValueError(f"Conflicting existing employer identities for {entry.name}; manual resolution required")
        if candidates:
            company = companies_by_id[next(iter(candidates))]
        else:
            company = Company(name=entry.name)
            db.add(company)
            await db.flush()
            companies_by_id[company.id] = company
            new_companies += 1
        registered_ids.add(company.id)
        company.website = company.website or entry.website_url
        company.industry = company.industry or entry.industry
        metadata = intelligence.get(company.id)
        if metadata is None:
            metadata = CompanyIntelligence(company_id=company.id, priority_tier=entry.priority_tier, tags=[])
            db.add(metadata)
            intelligence[company.id] = metadata
        metadata.careers_url = metadata.careers_url or entry.careers_url
        if not metadata.last_discovery_at and not metadata.discovery_claim_token:
            metadata.next_discovery_at = datetime.utcnow()
        if not metadata.careers_url and not company.website:
            metadata.discovery_status = "needs_careers_url"
        elif metadata.discovery_status == "needs_careers_url":
            metadata.discovery_status = "discovery_pending"
        metadata.tags = list(dict.fromkeys([*(metadata.tags or []), *entry.categories]))
        for name in [company.name, entry.name, *entry.aliases]:
            identity = normalized_alias(name)
            if identity not in aliases_by_key:
                alias = CompanyAlias(company_id=company.id, alias=name, normalized_alias=identity, source="registry_seed", is_primary=identity == normalized_alias(company.name))
                db.add(alias)
                aliases_by_key[identity] = alias
            owners[identity] = company
        for office in entry.office_locations:
            office_key = (company.id, office.country, office.region, office.city, "office")
            if office_key not in office_keys:
                db.add(CompanyLocation(company_id=company.id, **office.model_dump(), location_type="office"))
                office_keys.add(office_key)
        for seed in entry.sources:
            key = (seed.provider, seed.identifier)
            source = sources_by_key.get(key)
            if source is None:
                supported = seed.provider in SUPPORTED_PROVIDERS
                source = CompanySource(
                    company_id=company.id,
                    provider=seed.provider,
                    identifier=seed.identifier,
                    canonical_identity=canonical_identity(*key),
                    source_url=seed.source_url or source_url(*key),
                    evidence_url=seed.evidence_url,
                    status="unverified" if supported else "adapter_required",
                    managed_by_existing_provider=seed.provider in {"greenhouse", "lever"},
                )
                db.add(source)
                sources_by_key[key] = source
                new_sources += 1
            elif not source.evidence_url:
                source.evidence_url = seed.evidence_url
    await db.commit()
    source_company_ids = {source.company_id for source in sources_by_key.values()}
    return {
        "registered_companies": len(registered_ids),
        "new_companies": new_companies,
        "new_sources": new_sources,
        "configured_sources": sum(source.company_id in registered_ids for source in sources_by_key.values()),
        "discovery_pending": len(registered_ids - source_company_ids),
    }
