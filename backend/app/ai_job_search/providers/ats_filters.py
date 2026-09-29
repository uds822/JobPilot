"""Deterministic pre-scoring filters shared by company-specific ATS providers."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

from app.ai_job_search.providers.adzuna import (
    matches_selected_locations,
    normalize_india_search_locations,
)


_FOREIGN_MARKERS = {
    "singapore", "london", "united kingdom", " uk", "united states", " usa",
    "new york", "canada", "toronto", "dubai", "uae", "berlin", "germany",
    "sydney", "australia", "europe", "emea", "worldwide",
}

_INDIA_MARKERS = {
    "india", "bengaluru", "bangalore", "hyderabad", "pune", "chennai",
    "mumbai", "bombay", "delhi", "noida", "gurugram", "gurgaon", "kolkata",
    "calcutta", "indore", "ahmedabad", "jaipur", "kochi", "cochin",
    "chandigarh", "karnataka", "telangana", "maharashtra", "tamil nadu",
    "uttar pradesh", "west bengal", "madhya pradesh", "gujarat", "rajasthan",
    "kerala", "odisha",
}

_GENERIC_REMOTE = {"remote", "remote role", "work from home", "anywhere"}
_INDIA_COUNTRY_CODES = {"in", "ind"}
_FOREIGN_COUNTRY_CODES = {"au", "ca", "de", "gb", "sg", "uk", "us", "usa"}
_REMOTE_MARKERS = {"remote", "work from home", "work-from-home", "wfh"}
_INDIA_REMOTE_DESCRIPTION_MARKERS = {
    "anywhere in india",
    "across india",
    "based in india",
    "candidates in india",
    "candidates located in india",
    "located in india",
    "remote in india",
    "remote - india",
    "remote, india",
    "reside in india",
    "within india",
}
_TITLE_TOKEN_ALIASES = {
    "developer": "engineer",
    "development": "engineer",
    "engineering": "engineer",
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def html_to_text(value: str | None) -> str:
    if not value:
        return ""
    parser = _TextExtractor()
    parser.feed(value)
    parser.close()
    return " ".join(parser.parts)


def _title_tokens(value: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9+#.]+", value.lower())
    return {_TITLE_TOKEN_ALIASES.get(token, token) for token in tokens}


def title_matches_queries(title: str, queries: list[str]) -> bool:
    """Require every meaningful token from at least one generated query."""
    title_tokens = _title_tokens(title)
    if not title_tokens:
        return False
    return any(
        query_tokens and query_tokens.issubset(title_tokens)
        for query_tokens in (_title_tokens(query) for query in queries)
    )


def ats_location_matches(
    location: str | None,
    description: str | None,
    target_locations: list[str],
) -> bool:
    """Use structured location first and description only for ambiguous remote jobs."""
    actual = (location or "").strip().lower()
    description_text = (description or "").lower()
    normalized_targets = normalize_india_search_locations(target_locations)

    if actual in _FOREIGN_COUNTRY_CODES or any(
        marker in actual for marker in _FOREIGN_MARKERS
    ):
        return False

    all_india = normalized_targets == ["India"]
    generic_remote = not actual or actual in _GENERIC_REMOTE
    structured_india = actual in _INDIA_COUNTRY_CODES or any(
        marker in actual for marker in _INDIA_MARKERS
    )
    structured_remote = any(marker in actual for marker in _REMOTE_MARKERS)

    if not generic_remote:
        if all_india:
            return structured_india
        if structured_remote and structured_india:
            return True
        return matches_selected_locations(actual, normalized_targets)

    if any(marker in description_text for marker in _FOREIGN_MARKERS):
        return False
    if all_india:
        return any(marker in description_text for marker in _INDIA_MARKERS)
    if any(marker in description_text for marker in _INDIA_REMOTE_DESCRIPTION_MARKERS):
        return True
    return matches_selected_locations(description_text, normalized_targets)


def parse_provider_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            seconds = value / 1000 if value > 10_000_000_000 else value
            return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(tzinfo=None)
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except (TypeError, ValueError, OSError):
        return None
