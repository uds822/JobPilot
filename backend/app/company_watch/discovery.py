"""Durable employer discovery, independent from scheduled inventory ingestion."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import func, or_, select, update

from app.company_watch.detection import Candidate, canonical_url, detect_url, inspect_page, structured_jobs
from app.company_watch.http import RequestBudget, public_client, request_public
from app.company_watch.models import CompanyDiscoveryAttempt, CompanyIntelligence, CompanySource
from app.company_watch.providers import SUPPORTED_PROVIDERS, source_url
from app.database.database import AsyncSessionLocal
from app.models.companies import Company

logger = logging.getLogger(__name__)
DISCOVERY_SECONDS = 90
DISCOVERY_REQUESTS = 12
DISCOVERY_PAGES = 6
DISCOVERY_DEPTH = 2
LEASE = timedelta(minutes=5)


@dataclass(frozen=True)
class ClaimedCompany:
    id: int
    name: str
    careers_url: str | None
    website: str | None
    token: str


@dataclass(frozen=True)
class DiscoveryResult:
    company: ClaimedCompany
    candidates: tuple[tuple[Candidate, dict], ...] = ()
    careers_url: str | None = None
    error: str | None = None


async def claim_due_companies(limit=20, force=False, company_ids=None):
    now = datetime.utcnow()
    usable_source = select(CompanySource.id).where(
        CompanySource.company_id == CompanyIntelligence.company_id,
        CompanySource.is_active.is_(True),
        CompanySource.provider.in_(SUPPORTED_PROVIDERS),
        CompanySource.ownership_status.in_(("registry_trusted", "ownership_verified")),
        or_(CompanySource.last_verified_at.is_not(None), CompanySource.last_success_at.is_not(None)),
        CompanySource.status.not_in(("stale", "source_broken", "unverified", "adapter_required", "ownership_conflict", "unsupported")),
        CompanySource.consecutive_failures < 3,
    ).exists()
    async with AsyncSessionLocal() as db:
        conditions = [
            CompanyIntelligence.is_active.is_(True),
            or_(CompanyIntelligence.careers_url.is_not(None), Company.website.is_not(None)),
            or_(CompanyIntelligence.discovery_claimed_until.is_(None), CompanyIntelligence.discovery_claimed_until <= now),
        ]
        if not force:
            conditions.extend([~usable_source, CompanyIntelligence.next_discovery_at <= now])
        if company_ids is not None:
            conditions.append(CompanyIntelligence.company_id.in_(company_ids))
        rows = (await db.execute(
            select(CompanyIntelligence, Company)
            .join(Company, Company.id == CompanyIntelligence.company_id)
            .where(*conditions)
            .order_by(CompanyIntelligence.priority_tier, CompanyIntelligence.next_discovery_at, Company.id)
            .limit(limit).with_for_update(of=CompanyIntelligence, skip_locked=True)
        )).all()
        claims = []
        for metadata, company in rows:
            token = str(uuid4())
            metadata.discovery_claim_token = token
            metadata.discovery_claimed_until = now + LEASE
            metadata.discovery_status = "discovering"
            metadata.discovery_attempts += 1
            claims.append(ClaimedCompany(company.id, company.name, metadata.careers_url, company.website, token))
        await db.commit()
        return claims


async def inspect_company(client, company, semaphore, hosts):
    root = company.careers_url or company.website
    if not root:
        return DiscoveryResult(company, error="No careers URL or official website")
    candidates, visited = {}, set()
    queue = [(root, 0, [root])]
    careers = company.careers_url
    budget = RequestBudget(remaining=DISCOVERY_REQUESTS)
    errors = []
    try:
        async with asyncio.timeout(DISCOVERY_SECONDS):
            while queue and len(visited) < DISCOVERY_PAGES:
                url, depth, path = queue.pop(0)
                if url in visited:
                    continue
                visited.add(url)
                try:
                    response = await request_public(client, url, budget=budget, semaphore=semaphore, hosts=hosts)
                    response.raise_for_status()
                    final_url = str(response.url)
                    chain = response.extensions.get("redirect_chain", [url])
                    if careers is None and depth > 0:
                        careers = final_url
                    if "json" in response.headers.get("content-type", ""):
                        found, links, jobs = [], [], structured_jobs(response.json())
                        if jobs:
                            found = [Candidate("custom_api", hashlib.sha256(canonical_url(final_url).encode()).hexdigest(), final_url)]
                    else:
                        found, links, jobs = inspect_page(response.text, final_url)
                        if jobs and not found:
                            found.append(Candidate("direct_html", hashlib.sha256(canonical_url(final_url).encode()).hexdigest(), final_url))
                    redirected = detect_url(final_url)
                    if redirected:
                        found.append(redirected)
                    for candidate in found:
                        candidates.setdefault(candidate.identity, (candidate, {
                            "official_url": root,
                            "evidence_url": final_url,
                            "detected_url": candidate.url,
                            "redirect_chain": chain,
                            "link_chain": path,
                            "discovered_at": datetime.utcnow().isoformat(),
                            "method": "official_careers_link" if company.careers_url else "official_website_link",
                        }))
                    if found:
                        if careers is None:
                            careers = final_url if depth else next((link for link in links), final_url)
                        # Don't spend a full crawl budget once actionable source evidence exists.
                        break
                    if depth < DISCOVERY_DEPTH:
                        for link in links[:20]:
                            try:
                                clean = canonical_url(link)
                            except ValueError:
                                continue
                            queue.append((clean, depth + 1, [*path, clean]))
                    # Keep non-ATS sites visible for later site-specific work.
                    if company.careers_url and depth == 0 and not jobs:
                        candidate = Candidate("direct_html", hashlib.sha256(canonical_url(final_url).encode()).hexdigest(), final_url)
                        candidates.setdefault(candidate.identity, (candidate, {
                            "official_url": root, "evidence_url": final_url, "detected_url": final_url,
                            "redirect_chain": chain, "link_chain": path, "discovered_at": datetime.utcnow().isoformat(),
                            "method": "unstructured_careers_page", "extraction_required": True,
                        }))
                except Exception as exc:
                    errors.append((str(exc) or repr(exc))[:300])
            if queue and not candidates:
                errors.append("Discovery page/depth budget reached")
    except TimeoutError:
        errors.append("Discovery time budget reached")
    # Prefer validated-format candidates over the root's unstructured fallback.
    actionable = {key: value for key, value in candidates.items() if not value[1].get("extraction_required")}
    if actionable:
        candidates = actionable
    return DiscoveryResult(company, tuple(candidates.values()), careers, "; ".join(errors)[:1000] or (None if candidates else "No source found within discovery budget"))


async def record_discovery(result):
    now = datetime.utcnow()
    new_ids, conflict = [], None
    async with AsyncSessionLocal() as db:
        await db.execute(select(func.pg_advisory_xact_lock(1000006)))
        metadata = await db.scalar(select(CompanyIntelligence).where(CompanyIntelligence.company_id == result.company.id).with_for_update())
        if not metadata or metadata.discovery_claim_token != result.company.token or not metadata.discovery_claimed_until or metadata.discovery_claimed_until <= now:
            return {"status": "lease_lost", "source_ids": []}
        # Share the importer lock: seed and concurrent discovery cannot race source ownership.
        for candidate, evidence in result.candidates:
            source = await db.scalar(select(CompanySource).where(or_(
                CompanySource.canonical_identity == candidate.identity,
                (CompanySource.provider == candidate.provider) & (func.lower(CompanySource.identifier) == candidate.identifier.lower()),
            )).with_for_update())
            if source and source.company_id != metadata.company_id:
                conflict = f"Ownership conflict: {candidate.identity} belongs to company {source.company_id}"
                continue
            supported = candidate.provider in SUPPORTED_PROVIDERS and not evidence.get("extraction_required")
            if source is None:
                source = CompanySource(
                    company_id=metadata.company_id, provider=candidate.provider, identifier=candidate.identifier,
                    canonical_identity=candidate.identity, ownership_status="ownership_verified",
                    source_url=source_url(candidate.provider, candidate.identifier) if candidate.provider in {"greenhouse", "lever", "ashby"} else candidate.url,
                    status="unverified" if supported else "adapter_required",
                    managed_by_existing_provider=False,
                )
                db.add(source)
                await db.flush()
            source.canonical_identity = candidate.identity
            source.evidence_url = evidence["evidence_url"]
            source.discovery_evidence = evidence
            source.ownership_status = "ownership_verified"
            if supported and source.status in {"adapter_required", "unsupported", "stale", "source_broken"}:
                source.status = "unverified"
                source.next_verify_at = now
            if supported and source.is_active:
                new_ids.append(source.id)
        if result.careers_url and not metadata.careers_url:
            metadata.careers_url = result.careers_url
        if conflict:
            status = "ownership_conflict"
        elif new_ids:
            status = "source_discovered"
        elif result.candidates:
            status = "adapter_required"
        elif not metadata.careers_url:
            status = "needs_careers_url"
        else:
            status = "discovery_failed"
        metadata.discovery_status = status
        metadata.last_discovery_at = now
        metadata.discovery_error = conflict or result.error
        delay = min(72, 2 ** min(metadata.discovery_attempts - 1, 7))
        metadata.next_discovery_at = now + (timedelta(days=7) if status in {"adapter_required", "ownership_conflict"} else timedelta(hours=delay))
        metadata.discovery_claim_token = None
        metadata.discovery_claimed_until = None
        db.add(CompanyDiscoveryAttempt(company_id=metadata.company_id, checked_at=now, status=status,
            evidence={"careers_url": result.careers_url, "candidates": [{"identity": candidate.identity, **evidence} for candidate, evidence in result.candidates]}, error=metadata.discovery_error))
        await db.commit()
    return {"status": status, "source_ids": new_ids, "checked_at": now}


async def renew_discovery_claims(claims, stop):
    while True:
        try:
            await asyncio.wait_for(stop.wait(), timeout=30)
            return
        except TimeoutError:
            pass
        now = datetime.utcnow()
        async with AsyncSessionLocal() as db:
            for claim in claims:
                await db.execute(update(CompanyIntelligence).where(
                    CompanyIntelligence.company_id == claim.id,
                    CompanyIntelligence.discovery_claim_token == claim.token,
                    CompanyIntelligence.discovery_claimed_until > now,
                ).values(discovery_claimed_until=now + LEASE))
            await db.commit()


async def discover_due_companies(limit=20, concurrency=4, force=False, company_ids=None):
    if not 1 <= limit <= 100 or not 1 <= concurrency <= 10:
        raise ValueError("Discovery limit must be 1..100 and concurrency 1..10")
    claims = await claim_due_companies(limit, force, company_ids)
    summary = {"claimed": len(claims), "discovered": 0, "adapter_required": 0, "failed": 0, "verified": 0}
    if not claims:
        return summary
    stop = asyncio.Event()
    heartbeat = asyncio.create_task(renew_discovery_claims(claims, stop))
    semaphore, company_semaphore, hosts = asyncio.Semaphore(concurrency), asyncio.Semaphore(concurrency), {}
    from app.company_watch.service import verify_due_sources
    try:
        async with public_client() as client:
            async def work(claim):
                async with company_semaphore:
                    result = await inspect_company(client, claim, semaphore, hosts)
                    recorded = await record_discovery(result)
                    if recorded["source_ids"]:
                        verified = await verify_due_sources(limit=len(recorded["source_ids"]), concurrency=concurrency, source_ids=recorded["source_ids"], request_semaphore=semaphore, host_semaphores=hosts)
                        validated = verified["successful"] + verified.get("partial", 0)
                        summary["verified"] += validated
                        summary["discovered"] += 1
                        async with AsyncSessionLocal() as db:
                            await db.execute(update(CompanyIntelligence).where(
                                CompanyIntelligence.company_id == claim.id,
                                CompanyIntelligence.last_discovery_at == recorded["checked_at"],
                                CompanyIntelligence.discovery_claim_token.is_(None),
                            ).values(discovery_status="source_verified" if validated else "source_discovered"))
                            await db.commit()
                    elif recorded["status"] == "adapter_required":
                        summary["adapter_required"] += 1
                    else:
                        summary["failed"] += 1
            outcomes = await asyncio.gather(*(work(claim) for claim in claims), return_exceptions=True)
            for claim, outcome in zip(claims, outcomes):
                if isinstance(outcome, Exception):
                    logger.error("Discovery failed for company_id=%s: %s", claim.id, outcome)
                    summary["failed"] += 1
                    try:
                        await record_discovery(DiscoveryResult(claim, error=(str(outcome) or repr(outcome))[:1000]))
                    except Exception:
                        logger.exception("Could not record discovery failure; lease will expire")
    finally:
        stop.set()
        await heartbeat
    return summary
