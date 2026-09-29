"""Evidence-based source identities and structured job-page inspection."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from app.company_watch.http import validate_destination


def canonical_url(url: str) -> str:
    validate_destination(url)
    parsed = urlsplit(url)
    query = [(key, value) for key, values in sorted(parse_qs(parsed.query).items())
             if not key.lower().startswith("utm_") for value in sorted(values)]
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", urlencode(query), ""))


def canonical_identity(provider: str, identifier: str) -> str:
    return f"{provider.lower()}:{identifier.lower()}"


@dataclass(frozen=True)
class Candidate:
    provider: str
    identifier: str
    url: str

    @property
    def identity(self):
        return canonical_identity(self.provider, self.identifier)


def detect_url(url: str) -> Candidate | None:
    try:
        url = canonical_url(url)
    except ValueError:
        return None
    parsed = urlsplit(url)
    host, parts = parsed.hostname, [part for part in parsed.path.split("/") if part]
    board = None
    if host in {"boards.greenhouse.io", "job-boards.greenhouse.io", "boards-api.greenhouse.io"}:
        board = parse_qs(parsed.query).get("for", [None])[0] or (parts[2] if parts[:2] == ["v1", "boards"] and len(parts) > 2 else (parts[0] if parts else None))
        provider = "greenhouse"
    elif host in {"jobs.lever.co", "api.lever.co"}:
        board = parts[2] if parts[:2] == ["v0", "postings"] and len(parts) > 2 else (parts[0] if parts else None)
        provider = "lever"
    elif host in {"jobs.ashbyhq.com", "api.ashbyhq.com"}:
        board = parts[2] if parts[:2] == ["posting-api", "job-board"] and len(parts) > 2 else (parts[0] if parts else None)
        provider = "ashby"
    elif host and host.endswith(".myworkdayjobs.com") and len(host.split(".")) >= 4:
        tenant = host.split(".")[0]
        if parts[:2] == ["wday", "cxs"] and len(parts) >= 4:
            tenant, site = parts[2:4]
        else:
            if parts and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", parts[0]):
                parts = parts[1:]
            site = parts[0] if parts else None
        if site and re.fullmatch(r"[\w.-]+", site):
            return Candidate("workday", f"{host}:{tenant}:{site}", f"https://{host}/{site}")
        return None
    elif host in {"jobs.smartrecruiters.com", "careers.smartrecruiters.com", "api.smartrecruiters.com"}:
        board = parts[1] if parts[:1] == ["v1"] and len(parts) > 1 else (parts[0] if parts else None)
        provider = "smartrecruiters"
    elif host in {"www.google.com", "careers.google.com"} and ("careers" in parts or host == "careers.google.com"):
        return Candidate("google", "google", "https://www.google.com/about/careers/applications/jobs/results/?location=India")
    else:
        patterns = (
            ("icims", lambda h: h.endswith(".icims.com")),
            ("jobvite", lambda h: h == "jobs.jobvite.com"),
            ("oracle", lambda h: h.endswith(".oraclecloud.com")),
            ("successfactors", lambda h: h.endswith((".successfactors.com", ".successfactors.eu", ".successfactors.jobs"))),
            ("eightfold", lambda h: h.endswith(".eightfold.ai")),
        )
        for provider, matches in patterns:
            if host and matches(host):
                if provider == "icims":
                    return Candidate(provider, host, f"https://{host}/jobs/search")
                if provider == "jobvite" and parts:
                    return Candidate(provider, parts[0], f"https://{host}/{parts[0]}")
                if provider == "eightfold":
                    return Candidate(provider, host, f"https://{host}/careers")
                if provider == "oracle" and "sites" in parts and len(parts) > parts.index("sites") + 1:
                    site = parts[parts.index("sites") + 1]
                    return Candidate(provider, f"{host}:{site}", urlunsplit((parsed.scheme, parsed.netloc, "/" + "/".join(parts[:parts.index("sites") + 2]), "", "")))
                if provider == "successfactors" and parse_qs(parsed.query).get("company"):
                    return Candidate(provider, f"{host}:{parse_qs(parsed.query)['company'][0]}", url)
                return Candidate(provider, hashlib.sha256(url.encode()).hexdigest(), url)
        return None
    if board and re.fullmatch(r"[A-Za-z0-9_.-]+", board) and board not in {"embed", "v1", "v0"}:
        return Candidate(provider, board if provider == "smartrecruiters" else board.lower(), url)
    return None


def structured_jobs(payload) -> list[dict]:
    result = []
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, dict):
            kind = node.get("@type", [])
            if kind == "JobPosting" or isinstance(kind, list) and "JobPosting" in kind:
                result.append(node)
            else:
                stack.extend(value for key, value in node.items() if key in {"@graph", "itemListElement", "item", "jobs", "data"})
    return result


def inspect_page(text: str, url: str) -> tuple[list[Candidate], list[str], list[dict]]:
    soup = BeautifulSoup(text, "html.parser")
    urls = [url]
    links = []
    jobs = []
    for element in soup.find_all(["a", "iframe", "script"]):
        ref = element.get("href") or element.get("src")
        if ref:
            absolute = urljoin(url, ref)
            urls.append(absolute)
            label = element.get_text(" ", strip=True).lower()
            target = urlsplit(absolute)
            career_label = re.fullmatch(r"careers?|jobs|vacancies|open positions|current openings|job opportunities|join us|join our team|work with us|view(?: all)? jobs|search jobs|explore(?: our)? careers|careers at .+", label)
            career_path = re.search(r"/(?:careers?|jobs?|positions|vacancies|openings)(?:/|$)", target.path.lower())
            career_host = (target.hostname or "").startswith(("careers.", "jobs."))
            if element.name == "a" and (career_label or career_path or career_host):
                links.append(absolute)
        if element.name == "script" and element.get("type") == "application/ld+json":
            try:
                jobs.extend(structured_jobs(json.loads(element.string or element.get_text())))
            except (ValueError, TypeError):
                pass
        elif element.name == "script":
            # Static evidence only. Never execute scripts discovered on a page.
            urls.extend(re.findall(r"https?://[^\s\"'<>\\]+", element.get_text().replace("\\/", "/")))
    candidates = {}
    for ref in urls:
        candidate = detect_url(ref)
        if candidate:
            candidates[candidate.identity] = candidate
    return list(candidates.values()), list(dict.fromkeys(links)), jobs
