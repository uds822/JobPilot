from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from app.company_watch.service import (
    ingest_due_sources,
    coverage_report,
    seed_registry,
    source_health_status,
    verify_due_sources,
)
from app.company_watch.discovery import discover_due_companies
from app.company_watch.models import CompanySource, CompanyIntelligence
from app.database.database import AsyncSessionLocal
from app.models.companies import Company
from sqlalchemy import func, select


def _windows_selector_policy() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def _run(args: argparse.Namespace) -> None:
    if args.command == "seed":
        summary = await seed_registry(args.registry)
        print(json.dumps(summary, sort_keys=True))
        return
    if args.command == "coverage":
        print(json.dumps(await coverage_report(), default=str, indent=2))
        return
    if args.command == "status":
        rows = await source_health_status()
        if args.json:
            print(json.dumps(rows, default=str, indent=2))
            return
        print(f"Registered employers: {len({row['company_id'] for row in rows})}; "
              f"fetchable sources: {sum(row['fetchable'] for row in rows)}")
        for row in rows:
            print(
                "{provider:12} {company:24} {status:18} verified={verified} "
                "fetchable={fetchable} categories={categories} HTTP={http_status} {error}".format(**row)
            )
        return
    company_ids = source_ids = None
    if args.company:
        async with AsyncSessionLocal() as db:
            company_ids = list((await db.execute(select(Company.id).join(CompanyIntelligence, CompanyIntelligence.company_id == Company.id)
                .where(func.lower(Company.name).in_([name.lower() for name in args.company])))).scalars())
            if len(company_ids) != len(set(name.lower() for name in args.company)):
                raise ValueError("One or more company names are not registered")
            source_ids = list((await db.execute(select(CompanySource.id).where(CompanySource.company_id.in_(company_ids)))).scalars())
    if args.command == "discover":
        print(json.dumps(await discover_due_companies(limit=args.limit, concurrency=args.concurrency, force=args.force, company_ids=company_ids), sort_keys=True))
        return
    if args.command == "ingest":
        result = await ingest_due_sources(
            limit=args.limit,
            concurrency=args.concurrency,
            force=args.force,
            source_ids=source_ids,
        )
        print(
            "Ingestion run {run_id}: claimed={claimed} successful={successful} "
            "failed={failed} raw={raw_jobs} India={india_jobs} technical={technical_jobs} "
            "inserted={inserted} updated={updated} persistence_failures={persistence_failures}".format(**result)
        )
        return
    result = await verify_due_sources(
        limit=args.limit,
        concurrency=args.concurrency,
        force=args.force,
        source_ids=source_ids,
    )
    print(
        "Verification run {run_id}: claimed={claimed} successful={successful} "
        "failed={failed} India jobs={india_jobs}".format(**result)
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="company-watch")
    subparsers = parser.add_subparsers(dest="command", required=True)
    seed = subparsers.add_parser("seed", help="Import employer metadata and ATS source candidates")
    seed.add_argument("--registry", help="Custom JSON registry; default also merges legacy bootstrap targets")
    status = subparsers.add_parser("status", help="Show registry companies, including discovery-pending employers")
    status.add_argument("--json", action="store_true", help="Print structured registry health")
    subparsers.add_parser("coverage", help="Report live company coverage and direct-source job counts")
    discover = subparsers.add_parser("discover", help="Discover and validate due company sources")
    discover.add_argument("--limit", type=int, default=20)
    discover.add_argument("--concurrency", type=int, default=4)
    discover.add_argument("--force", action="store_true")
    verify = subparsers.add_parser("verify", help="Verify due ATS sources once")
    verify.add_argument("--limit", type=int, default=50)
    verify.add_argument("--concurrency", type=int, default=10)
    verify.add_argument("--force", action="store_true", help="Check active sources before next_check_at")
    ingest = subparsers.add_parser("ingest", help="Fetch and persist India-relevant postings")
    ingest.add_argument("--limit", type=int, default=50)
    ingest.add_argument("--concurrency", type=int, default=10)
    ingest.add_argument("--force", action="store_true", help="Ingest active sources before next_check_at")
    for command in (discover, verify, ingest):
        command.add_argument("--company", action="append", help="Restrict work to an exact registered company name; repeatable")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    _windows_selector_policy()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
