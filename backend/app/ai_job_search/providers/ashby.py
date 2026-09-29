"""Normalization for Ashby's published job-board feed, independent of user scoring."""

from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from app.ai_job_search.providers.ats_filters import (
    ats_location_matches,
    html_to_text,
    parse_provider_datetime,
)
from app.ai_job_search.schemas import NormalizedJobSchema


class AshbyProvider:
    name = "ashby"

    @staticmethod
    def posting_id(board: str, item: dict[str, Any]) -> str:
        url = urlparse(str(item.get("jobUrl") or ""))
        parts = url.path.strip("/").split("/")
        if url.scheme != "https" or url.hostname != "jobs.ashbyhq.com":
            raise ValueError("Ashby posting must have a valid hosted jobUrl")
        if len(parts) != 2 or parts[0].lower() != board.lower():
            raise ValueError("Ashby posting URL does not belong to this board")
        return str(UUID(parts[1]))

    @staticmethod
    def _description(item: dict[str, Any]) -> str:
        return str(item.get("descriptionPlain") or html_to_text(item.get("descriptionHtml")))

    @classmethod
    def _india_locations(cls, item: dict[str, Any]) -> list[str]:
        address = item.get("address") or {}
        if not isinstance(address, dict):
            raise ValueError("Malformed Ashby address")
        primary = {"location": item.get("location"), "address": address.get("postalAddress") or {}}
        secondary = item.get("secondaryLocations") or []
        if not isinstance(secondary, list):
            raise ValueError("Malformed Ashby secondary locations")
        eligible = []
        remote = item.get("isRemote") is True or item.get("workplaceType") == "Remote"
        for entry in [primary, *secondary]:
            if not isinstance(entry, dict) or not isinstance(entry.get("address") or {}, dict):
                raise ValueError("Malformed Ashby location")
            postal = entry.get("address") or {}
            country = str(postal.get("addressCountry") or "").strip()
            if country and country.lower() not in {"india", "in", "ind"}:
                continue
            country = "India" if country else ""
            values = [entry.get("location"), postal.get("addressLocality"), postal.get("addressRegion"), country]
            location = ", ".join(dict.fromkeys(str(value) for value in values if value)) or "Remote"
            if remote and "remote" not in location.lower():
                location = "Remote, " + location
            if ats_location_matches(location, cls._description(item), ["India"]):
                eligible.append(location)
        return list(dict.fromkeys(eligible))

    def _normalize(self, company: str, board: str, item: dict[str, Any]) -> NormalizedJobSchema | None:
        posting_id = self.posting_id(board, item)
        if item.get("isListed") is False:
            return None
        locations = self._india_locations(item)
        if not locations:
            return None
        apply_url = str(item.get("applyUrl") or item["jobUrl"])
        parsed_apply = urlparse(apply_url)
        if parsed_apply.scheme != "https" or not parsed_apply.hostname:
            raise ValueError("Invalid Ashby application URL")
        salary = None
        compensation = item.get("compensation") or {}
        if isinstance(compensation, dict):
            components = compensation.get("summaryComponents") or []
            salaries = [c for c in components if isinstance(c, dict) and c.get("compensationType") == "Salary"]
            if len(salaries) == 1:
                salary = salaries[0]
        external_id = f"{board}_{posting_id}"
        return NormalizedJobSchema(
            job_hash=hashlib.sha256(f"ashby:{external_id}".encode()).hexdigest(),
            source=self.name,
            external_id=external_id,
            title=item["title"],
            company=company,
            location=" / ".join(locations),
            remote=item.get("isRemote") is True or item.get("workplaceType") == "Remote",
            description=self._description(item) or None,
            salary_min=salary.get("minValue") if salary else None,
            salary_max=salary.get("maxValue") if salary else None,
            salary_currency=salary.get("currencyCode") if salary else None,
            salary_interval={"1 YEAR": "annual", "1 MONTH": "monthly", "1 HOUR": "hourly"}.get(salary.get("interval"), salary.get("interval")) if salary else None,
            salary_source="provider" if salary else None,
            apply_url=apply_url,
            source_url=item["jobUrl"],
            posted_date=parse_provider_datetime(item.get("publishedAt")),
            is_active=True,
        )
