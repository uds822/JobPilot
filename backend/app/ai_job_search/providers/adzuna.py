"""
Step 1 — Adzuna provider (multi-query × multi-location × multi-page).

Interface:
    async def fetch(
        queries: list[str],
        locations: list[str],
        pages: int = 3,
        max_days_old: int = 14,
        concurrency: int = 5,
    ) -> list[NormalizedJobSchema]

Every (query, location, page) combination is fetched concurrently within
a bounded semaphore. One failed combination never fails the entire search.
Transient HTTP errors (5xx / network) are retried with exponential backoff.
Permanent 4xx errors are logged and skipped immediately.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime
from itertools import product
from typing import Optional

import httpx

from app.ai_job_search.schemas import NormalizedJobSchema
from app.config import settings

logger = logging.getLogger(__name__)

# ── Retry config ──────────────────────────────────────────────────────────────
_MAX_RETRIES = 3
_BACKOFF_BASE = 1.5   # seconds; delay = base ** attempt

# Translate the labels already used by the UI into terms Adzuna understands,
# while retaining aliases for validating each returned job's actual location.
_LOCATION_SEARCH_TERMS = {
    "india": "",
    "bengaluru (bangalore)": "Bengaluru",
    "hyderabad": "Hyderabad",
    "pune": "Pune",
    "chennai": "Chennai",
    "mumbai": "Mumbai",
    "delhi": "Delhi",
    "noida": "Noida",
    "gurugram (gurgaon)": "Gurugram",
    "kolkata": "Kolkata",
    "indore": "Indore",
    "ahmedabad": "Ahmedabad",
    "jaipur": "Jaipur",
    "kochi": "Kochi",
    "chandigarh": "Chandigarh",
    "delhi ncr (gurugram / noida)": "Delhi NCR",
}

_LOCATION_MATCH_ALIASES = {
    "india": (
        "india", "karnataka", "telangana", "maharashtra", "tamil nadu",
        "delhi", "uttar pradesh", "west bengal", "madhya pradesh",
        "gujarat", "rajasthan", "kerala", "chandigarh", "bengaluru",
        "bangalore", "hyderabad", "pune", "chennai", "mumbai", "noida",
        "gurugram", "gurgaon", "kolkata", "indore", "ahmedabad", "jaipur",
        "kochi", "cochin",
    ),
    "bengaluru (bangalore)": ("bengaluru", "bangalore"),
    "hyderabad": ("hyderabad",),
    "pune": ("pune",),
    "chennai": ("chennai", "madras"),
    "mumbai": ("mumbai", "bombay"),
    "delhi": ("delhi", "new delhi"),
    "noida": ("noida", "greater noida"),
    "gurugram (gurgaon)": ("gurugram", "gurgaon"),
    "kolkata": ("kolkata", "calcutta"),
    "indore": ("indore",),
    "ahmedabad": ("ahmedabad",),
    "jaipur": ("jaipur",),
    "kochi": ("kochi", "cochin"),
    "chandigarh": ("chandigarh",),
    "delhi ncr (gurugram / noida)": (
        "delhi", "new delhi", "noida", "gurugram", "gurgaon",
    ),
}

_LOCATION_INPUT_ALIASES = {
    "bengaluru": "Bengaluru (Bangalore)",
    "bangalore": "Bengaluru (Bangalore)",
    "bengaluru (bangalore)": "Bengaluru (Bangalore)",
    "gurugram": "Gurugram (Gurgaon)",
    "gurgaon": "Gurugram (Gurgaon)",
    "gurugram (gurgaon)": "Gurugram (Gurgaon)",
    "new delhi": "Delhi",
    "greater noida": "Noida",
}

_INDIA_LOCATION_LABELS = {
    "Bengaluru (Bangalore)", "Hyderabad", "Pune", "Chennai", "Mumbai",
    "Delhi", "Noida", "Gurugram (Gurgaon)", "Kolkata", "Indore",
    "Ahmedabad", "Jaipur", "Kochi", "Chandigarh",
}

_FOREIGN_LOCATION_MARKERS = {
    "singapore", "london", "united kingdom", "uk", "united states", "usa",
    "new york", "canada", "toronto", "dubai", "uae", "berlin", "germany",
    "sydney", "australia", "worldwide",
}


def _job_hash(source: str, external_id: str) -> str:
    return hashlib.sha256(f"{source}:{external_id}".encode()).hexdigest()[:24]


def _normalize(item: dict, is_india: bool) -> NormalizedJobSchema:
    """Map one raw Adzuna API result to NormalizedJobSchema."""
    ext_id = str(item.get("id", ""))
    title = (
        item.get("title", "Software Engineer")
        .replace("<strong>", "")
        .replace("</strong>", "")
        .strip()
    )
    company = item.get("company", {}).get("display_name", "Tech Company")
    loc = item.get("location", {}).get("display_name", "Remote")
    is_remote = "remote" in title.lower() or "remote" in loc.lower()
    desc = item.get("description", "")

    sal_min = item.get("salary_min")
    sal_max = item.get("salary_max")
    currency = "INR" if is_india else "USD"

    return NormalizedJobSchema(
        job_hash=_job_hash("adzuna", ext_id),
        source="adzuna",
        external_id=ext_id,
        title=title,
        company=company,
        location=loc,
        remote=is_remote,
        description=desc,
        salary_min=float(sal_min) if sal_min else None,
        salary_max=float(sal_max) if sal_max else None,
        salary_currency=currency,
        salary_interval="annual",
        salary_source="provider",
        apply_url=item.get("redirect_url", "https://adzuna.com"),
        source_url=item.get("redirect_url"),
        posted_date=datetime.utcnow(),
        is_active=True,
    )


def _is_india(location: str) -> bool:
    india_keywords = {
        "india", "bengaluru", "bangalore", "hyderabad", "pune",
        "mumbai", "delhi", "gurugram", "gurgaon", "noida", "kolkata", "chennai",
        "indore", "ahmedabad", "jaipur", "kochi", "cochin", "chandigarh",
    }
    return any(k in location.lower() for k in india_keywords)


def normalize_india_search_locations(locations: list[str]) -> list[str]:
    """Keep supported Indian locations; use all India when none are selected."""
    normalized: list[str] = []
    labels_by_lower = {label.lower(): label for label in _INDIA_LOCATION_LABELS}

    for location in locations:
        key = str(location).strip().lower()
        if not key:
            continue
        if key == "india":
            return ["India"]
        label = _LOCATION_INPUT_ALIASES.get(key) or labels_by_lower.get(key)
        if label and label not in normalized:
            normalized.append(label)

    return normalized or ["India"]


def provider_location_term(location: str) -> str:
    """Convert a saved UI label to the provider's `where` search term."""
    stripped = location.strip()
    return _LOCATION_SEARCH_TERMS.get(stripped.lower(), stripped)


def matches_selected_locations(job_location: str, selected_locations: list[str]) -> bool:
    """Return true when the provider location matches any selected location."""
    actual = (job_location or "").strip().lower()
    if not actual:
        return False

    for selected in selected_locations:
        selected_key = selected.strip().lower()
        if selected_key == "india":
            return not any(marker in actual for marker in _FOREIGN_LOCATION_MARKERS)
        aliases = _LOCATION_MATCH_ALIASES.get(selected_key, (selected_key,))
        if any(alias and alias in actual for alias in aliases):
            return True
    return False


async def _fetch_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    app_id: str,
    app_key: str,
    query: str,
    location: str,
    page: int,
    max_days_old: int,
) -> list[NormalizedJobSchema]:
    """
    Fetch a single (query, location, page) combination from Adzuna.
    Retries transient errors; skips permanent 4xx errors.
    """
    provider_location = provider_location_term(location)
    india = _is_india(location)
    country = "in" if india else "us"
    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "what": query,
        "where": provider_location,
        "results_per_page": 30,
        "max_days_old": max_days_old,
        "content-type": "application/json",
    }

    async with semaphore:
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await client.get(url, params=params, timeout=12.0)

                if resp.status_code == 200:
                    items = resp.json().get("results", [])
                    jobs = [_normalize(item, india) for item in items]
                    logger.info(
                        f"Adzuna OK: query='{query}' loc='{location}' page={page} → {len(jobs)} jobs"
                    )
                    return jobs

                if 400 <= resp.status_code < 500:
                    logger.warning(
                        f"Adzuna {resp.status_code} (permanent): query='{query}' "
                        f"loc='{location}' page={page} — skipping. {resp.text[:150]}"
                    )
                    return []

                # 5xx — transient, will retry
                logger.warning(
                    f"Adzuna {resp.status_code} (attempt {attempt+1}): "
                    f"query='{query}' loc='{location}' page={page}"
                )

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                logger.warning(
                    f"Adzuna network error (attempt {attempt+1}): "
                    f"query='{query}' loc='{location}' page={page} — {e}"
                )

            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(_BACKOFF_BASE ** attempt)

    logger.error(
        f"Adzuna: all {_MAX_RETRIES} attempts failed for "
        f"query='{query}' loc='{location}' page={page}"
    )
    return []


async def fetch(
    queries: list[str],
    locations: list[str],
    pages: int = 3,
    max_days_old: int = 14,
    concurrency: int = 5,
) -> list[NormalizedJobSchema]:
    """
    Fetch jobs from Adzuna for all combinations of queries × locations × pages.

    Args:
        queries:      List of natural-language search queries (from query_generator).
        locations:    List of target locations, e.g. ["Bengaluru", "Hyderabad"].
        pages:        How many Adzuna result pages to fetch per combination (default 3).
        max_days_old: Only return jobs posted within this many days.
        concurrency:  Max parallel HTTP requests (Semaphore limit).

    Returns:
        Flat deduplicated list of NormalizedJobSchema (dedup by job_hash).
    """
    app_id = settings.ADZUNA_APP_ID
    app_key = settings.ADZUNA_APP_KEY

    if not app_id or not app_key:
        logger.error("Adzuna credentials missing — ADZUNA_APP_ID / ADZUNA_APP_KEY not set")
        return []

    combinations = list(product(queries, locations, range(1, pages + 1)))
    logger.info(
        f"Adzuna fetch: {len(queries)} queries × {len(locations)} locations × "
        f"{pages} pages = {len(combinations)} requests (concurrency={concurrency})"
    )

    semaphore = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient() as client:
        tasks = [
            _fetch_one(client, semaphore, app_id, app_key, q, loc, pg, max_days_old)
            for q, loc, pg in combinations
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Flatten, skip exceptions, deduplicate by job_hash
    seen_hashes: set[str] = set()
    all_jobs: list[NormalizedJobSchema] = []
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Adzuna task raised exception: {result}")
            continue
        for job in result:
            if job.job_hash not in seen_hashes:
                seen_hashes.add(job.job_hash)
                all_jobs.append(job)

    logger.info(f"Adzuna total: {len(all_jobs)} unique jobs after dedup")
    return all_jobs
