import re
import json
import logging
from typing import Dict, Any, Tuple, Optional, Set
import httpx


from app.config import settings
from app.ai_job_search.experience import assess_experience, extract_experience_facts
from app.ai_job_search.schemas import ResumeProfileSchema, NormalizedJobSchema

logger = logging.getLogger(__name__)

KNOWN_INDUSTRIES = [
    "Software", "AI/ML", "FinTech", "Healthcare", "Semiconductor",
    "E-commerce", "Telecom", "Banking", "Cybersecurity", "EdTech", "Consulting"
]

RESUME_SCHEMA_PROMPT = """\
You are a job matching assistant. Score how well this candidate fits the job.
Return ONLY a valid JSON object with these exact keys and numeric values 0-100:
skills_overlap, experience_fit, role_similarity, location_fit, industry_fit, company_type_fit, posting_freshness.
Also include: strengths (list of 1-2 short strings), gaps (list of 1-2 short strings).

CANDIDATE: Core skills: {primary_skills}. Supporting skills: {supporting_skills}.
Tools: {tools}. Domain expertise: {domain_skills}. Experience: {exp} years.
Target roles: {target_roles}. Recent roles: {titles}.
JOB: Title: {title}. Company: {company}. Location: {location}.
Description: {desc}

RULE: Do not infer required years from the title or treat missing years as a confirmed experience fit.
Return ONLY the JSON object. No other text.\
"""


def classify_company(company_name: str, job_title: str, description: str) -> Tuple[str, str, float]:
    """Classify company into industry + company_type via keyword heuristics."""
    c = company_name.lower()
    d = (description or "").lower()

    if any(k in c for k in ["stripe", "github", "gitlab", "figma", "netflix", "spotify", "google", "microsoft"]):
        return ("Software", "product", 0.95)
    if "bank" in c or "plaid" in c or "fintech" in d:
        return ("FinTech", "product", 0.90)
    if "ai" in c or "neural" in c or "data" in c:
        return ("AI/ML", "product", 0.85)

    industry = "Software"
    for ind in KNOWN_INDUSTRIES:
        if ind.lower() in d or ind.lower() in c:
            industry = ind
            break

    c_type = "product"
    if "consulting" in d or "services" in c:
        c_type = "consulting"
    elif "startup" in d or "seed" in d or "series a" in d:
        c_type = "startup"
    elif "enterprise" in d:
        c_type = "enterprise"

    return (industry, c_type, 0.80)


def extract_required_experience_range(
    title: str, description: str
) -> Optional[Tuple[float, Optional[float]]]:
    """Extract an explicit experience lower bound and optional upper bound."""
    text = f"{title} {description}".lower()
    number = r"\d+(?:\.\d+)?"
    range_patterns = (
        rf"\b(?P<low>{number})\s*(?:-|\u2013|to)\s*(?P<high>{number})\s*(?:yrs?|years?)(?:['\u2019])?\s+(?:of\s+)?(?:[a-z+#./-]+\s+){{0,5}}(?:experience|exp)\b",
        rf"\b(?:experience|exp)\s+(?:of\s+)?(?P<low>{number})\s*(?:-|\u2013|to)\s*(?P<high>{number})\s*(?:yrs?|years?)\b",
    )
    for pattern in range_patterns:
        match = re.search(pattern, text)
        if match:
            low, high = float(match.group("low")), float(match.group("high"))
            if 0 <= low <= high <= 40:
                return low, high

    minimum_patterns = (
        rf"\b(?:at\s+least\s+|minimum\s+(?:of\s+)?|min\.?\s*)?(?P<low>{number})\s*\+\s*(?:yrs?|years?)(?:['\u2019])?\s+(?:of\s+)?(?:[a-z+#./-]+\s+){{0,5}}(?:experience|exp)\b",
        rf"\b(?:at\s+least\s+|minimum\s+(?:of\s+)?|min\.?\s*)(?P<low>{number})\s*(?:yrs?|years?)(?:['\u2019])?\s+(?:of\s+)?(?:[a-z+#./-]+\s+){{0,5}}(?:experience|exp)\b",
        rf"\b(?P<low>{number})\s*(?:yrs?|years?)(?:['\u2019])?\s+(?:of\s+)?(?:[a-z+#./-]+\s+){{0,5}}(?:experience|exp)\b",
    )
    for pattern in minimum_patterns:
        match = re.search(pattern, text)
        if match:
            low = float(match.group("low"))
            if 0 <= low <= 40:
                return low, None
    return None


def extract_required_experience(title: str, description: str) -> Optional[float]:
    """Backward-compatible helper returning the explicit minimum years."""
    experience_range = extract_required_experience_range(title, description)
    return experience_range[0] if experience_range else None


def candidate_experience_range(
    user_prefs: Dict[str, Any], profile: ResumeProfileSchema
) -> Tuple[Optional[float], Optional[float]]:
    """Read the user's confirmed range, falling back to the legacy resume estimate."""
    low = user_prefs.get("experience_min_years")
    high = user_prefs.get("experience_max_years")
    if (
        "experience_min_years" not in user_prefs
        and "experience_max_years" not in user_prefs
    ):
        legacy = user_prefs.get("years_experience")
        if legacy is None:
            legacy = profile.years_experience
        if legacy is None or float(legacy) <= 0:
            return None, None
        return float(legacy), float(legacy)
    return (
        float(low) if low is not None else None,
        float(high) if high is not None else None,
    )


def experience_fit_score(
    job: NormalizedJobSchema, profile: ResumeProfileSchema, user_prefs: Dict[str, Any]
) -> float:
    candidate_min, candidate_max = candidate_experience_range(user_prefs, profile)
    facts = extract_experience_facts(
        job.title, job.description, completeness=job.description_completeness
    )
    assessment = assess_experience(facts, candidate_min, candidate_max)
    if assessment.seniority_conflict or assessment.status == "mismatched":
        return 20.0
    if assessment.status == "matched":
        return 95.0
    return 70.0


def experience_range_matches(
    title: str,
    description: str,
    candidate_min: Optional[float],
    candidate_max: Optional[float],
) -> bool:
    """Keep unknown requirements; otherwise require the candidate and role ranges to overlap."""
    required = extract_required_experience_range(title, description)
    if required is None:
        normalized_title = title.lower()
        if re.search(r"\b(?:staff|principal|director|distinguished)\b|\bhead\s+of\b", normalized_title):
            required = (8.0, None)
        elif re.search(r"\b(?:senior|sr\.?)\b|\b(?:engineering|technical|team)\s+lead\b", normalized_title):
            required = (5.0, None)
    if required is None or (candidate_min is None and candidate_max is None):
        return True
    required_min, required_max = required
    if candidate_max is not None and required_min > candidate_max + 0.25:
        return False
    if (
        candidate_min is not None
        and required_max is not None
        and required_max < candidate_min - 0.25
    ):
        return False
    return True


def _extract_json(raw: str) -> dict:
    """Strip markdown fences and extract the first JSON object."""
    clean = re.sub(r"^```json\s*", "", raw, flags=re.MULTILINE)
    clean = re.sub(r"^```\s*", "", clean, flags=re.MULTILINE)
    m = re.search(r'\{.*\}', clean, re.DOTALL)
    if m:
        clean = m.group(0)
    return json.loads(clean.strip())


async def _call_llm(prompt: str, timeout: float = 15.0) -> Optional[dict]:
    """
    Try Groq (primary) then OpenRouter (fallback).
    Returns parsed JSON dict or None if both fail.
    """
    groq_key = settings.GROQ_API_KEY
    groq_model = settings.GROQ_MODEL
    or_key = settings.OPENROUTER_API_KEY
    or_model = settings.OPENROUTER_MODEL

    providers = []
    if groq_key:
        providers.append({
            "name": "Groq",
            "url": "https://api.groq.com/openai/v1/chat/completions",
            "headers": {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
            "model": groq_model,
        })
    if or_key:
        providers.append({
            "name": "OpenRouter",
            "url": "https://openrouter.ai/api/v1/chat/completions",
            "headers": {
                "Authorization": f"Bearer {or_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://jobpilot.app",
                "X-Title": "JobPilot",
            },
            "model": or_model,
        })

    for p in providers:
        try:
            body = {
                "model": p["model"],
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 350,
            }
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(p["url"], headers=p["headers"], json=body)
                if resp.status_code == 200:
                    raw = resp.json()["choices"][0]["message"]["content"]
                    if not raw:
                        raise ValueError("Empty response")
                    result = _extract_json(raw)
                    logger.info(f"LLM scoring OK via {p['name']} ({p['model']})")
                    return result
                else:
                    logger.warning(f"{p['name']} HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"{p['name']} failed: {e}")

    return None


async def compute_match_score_llm(
    job: NormalizedJobSchema,
    profile: ResumeProfileSchema,
    user_prefs: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Score job against candidate profile using Groq (primary) or OpenRouter (fallback).
    Falls back to heuristic scoring if both LLMs are unavailable.
    """
    exp_min, exp_max = candidate_experience_range(user_prefs, profile)
    cand_exp = exp_max if exp_max is not None else (exp_min or 1.0)
    skills_str = ", ".join(profile.skills[:10]) if profile.skills else "Not specified"
    groups = profile.skill_groups
    titles_str = ", ".join(profile.recent_titles[:3]) or "Not specified"
    desc_snippet = (job.description or "")[:800]

    prompt = RESUME_SCHEMA_PROMPT.format(
        primary_skills=", ".join(groups.primary[:8]) or skills_str,
        supporting_skills=", ".join(groups.supporting[:8]) or "Not specified",
        tools=", ".join(groups.tools[:8]) or "Not specified",
        domain_skills=", ".join(groups.domain[:8]) or "Not specified",
        target_roles=", ".join(profile.target_roles[:5]) or "Not specified",
        exp=(f"{exp_min:g}-{exp_max:g}" if exp_min is not None and exp_max is not None and exp_min != exp_max else f"{cand_exp:g}"),
        titles=titles_str,
        title=job.title,
        company=job.company,
        location=job.location,
        desc=desc_snippet,
    )

    factors = await _call_llm(prompt, timeout=15.0)
    if factors:
        factors["experience_fit"] = experience_fit_score(job, profile, user_prefs)
        ind, c_type, _ = classify_company(job.company, job.title, job.description or "")
        return _calculate_weighted_score(job, profile, factors, ind, c_type)

    # Heuristic fallback
    logger.warning(f"All LLMs failed for '{job.title}' — using heuristic scoring")
    return await _heuristic_score(job, profile, user_prefs)


async def _heuristic_score(
    job: NormalizedJobSchema,
    profile: ResumeProfileSchema,
    user_prefs: Dict[str, Any],
) -> Dict[str, Any]:
    """Pure Python heuristic scoring — no LLM required."""
    job_text = f"{job.title} {job.description}".lower()

    matching = [s for s in profile.skills if s.lower() in job_text]
    missing = [s for s in profile.skills if s.lower() not in job_text]

    skills_score = (len(matching) / max(len(profile.skills), 1)) * 100.0
    skills_score = min(100.0, max(20.0, skills_score + 15.0 if matching else 20.0))

    exp_score = experience_fit_score(job, profile, user_prefs)

    role_score = _role_similarity(job.title, profile)

    ind, c_type, _ = classify_company(job.company, job.title, job.description or "")

    pref_industries = user_prefs.get("preferred_industries") or profile.preferred_industries
    is_any_ind = not pref_industries or "any" in [i.lower() for i in pref_industries]
    ind_score = 90.0 if is_any_ind or any(pi.lower() in ind.lower() for pi in pref_industries) else 50.0

    pref_ctypes = user_prefs.get("preferred_company_types") or profile.preferred_company_types
    is_any_ctype = not pref_ctypes or "any" in [ct.lower() for ct in pref_ctypes]
    ctype_score = 90.0 if is_any_ctype or any(pct.lower() == c_type.lower() for pct in pref_ctypes) else 50.0

    rem_pref = user_prefs.get("remote_preference") or profile.remote_preference or "any"
    loc_score = 95.0 if job.remote or rem_pref == "any" else 80.0

    factors = {
        "skills_overlap": skills_score,
        "experience_fit": exp_score,
        "role_similarity": role_score,
        "industry_fit": ind_score,
        "company_type_fit": ctype_score,
        "location_fit": loc_score,
        "posting_freshness": 95.0,
        "strengths": [f"Core skills match: {', '.join(matching[:3])}"] if matching else ["Matches target role profile"],
        "gaps": [f"Missing keywords: {', '.join(missing[:2])}"] if missing else ["No major gaps identified"],
    }
    return _calculate_weighted_score(job, profile, factors, ind, c_type)


def _calculate_weighted_score(
    job: NormalizedJobSchema,
    profile: ResumeProfileSchema,
    factors: Dict[str, Any],
    industry: str,
    company_type: str,
) -> Dict[str, Any]:
    raw = (
        float(factors.get("skills_overlap", 70)) * 0.30 +
        float(factors.get("experience_fit", 70)) * 0.20 +
        float(factors.get("role_similarity", 70)) * 0.15 +
        float(factors.get("industry_fit", 70)) * 0.10 +
        float(factors.get("company_type_fit", 70)) * 0.10 +
        float(factors.get("location_fit", 70)) * 0.10 +
        float(factors.get("posting_freshness", 90)) * 0.05
    )
    score = round(min(100.0, max(0.0, raw)), 1)
    return {
        "match_score": score,
        "match_level": "Strong match" if score >= 80.0 else "Good match",
        "callback_likelihood": "high" if score >= 85 else "medium",
        "match_reasoning": f"Profile shows {score}% compatibility with {job.title} at {job.company}.",
        "strengths": factors.get("strengths") or ["High role fit"],
        "gaps": factors.get("gaps") or ["No critical gaps"],
        "skills_overlap": round(float(factors.get("skills_overlap", 70)), 1),
        "experience_fit": round(float(factors.get("experience_fit", 70)), 1),
        "role_similarity": round(float(factors.get("role_similarity", 70)), 1),
        "location_fit": round(float(factors.get("location_fit", 70)), 1),
        "industry_fit": round(float(factors.get("industry_fit", 70)), 1),
        "company_type_fit": round(float(factors.get("company_type_fit", 70)), 1),
        "posting_freshness": round(float(factors.get("posting_freshness", 90)), 1),
        "industry": industry,
        "company_type": company_type,
    }


_GENERIC_ROLE_TERMS = {
    "engineer", "engineering", "developer", "development", "software",
    "senior", "junior", "staff", "principal", "lead", "the", "and",
}


def _role_similarity(job_title: str, profile: ResumeProfileSchema) -> float:
    role_titles = profile.target_roles or profile.recent_titles
    if not role_titles:
        return 50.0
    job_terms = set(re.findall(r"[a-z0-9+#.]+", job_title.lower())) - _GENERIC_ROLE_TERMS
    if not job_terms:
        return 50.0
    best = 0.0
    for role in role_titles:
        role_terms = set(re.findall(r"[a-z0-9+#.]+", role.lower())) - _GENERIC_ROLE_TERMS
        if role_terms:
            best = max(best, len(job_terms & role_terms) / len(role_terms))
    return round(50.0 + 45.0 * best, 1)


def compute_match_score_deterministic(
    job: NormalizedJobSchema,
    profile: ResumeProfileSchema,
    job_skills: Set[str],
    user_prefs: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Score a job using a pre-extracted set of canonical skill strings.

    This is the primary scoring path (called for every job).
    No network call. No LLM call. Synchronous.

    Args:
        job:        Normalized job record.
        profile:    Parsed resume profile.
        job_skills: Canonical skills extracted from job description by
                    extract_job_skills() in job_skill_extractor.py.
                    The caller is responsible for producing this set;
                    this function only consumes it.
        user_prefs: User preference overrides (may be empty dict).

    Returns:
        Same shape as compute_match_score_llm() — compatible with DB persistence.
    """
    from app.ai_job_search.skill_normalizer import normalize_skill

    skill_weights = {"primary": 2.5, "supporting": 1.35, "tools": 0.8, "domain": 1.1}
    weighted_skills: Dict[str, float] = {}
    for group, weight in skill_weights.items():
        for skill in getattr(profile.skill_groups, group, []):
            normalized = normalize_skill(skill)
            if normalized:
                weighted_skills[normalized] = max(weighted_skills.get(normalized, 0), weight)
    for skill in profile.skills:
        normalized = normalize_skill(skill)
        if normalized:
            weighted_skills.setdefault(normalized, 1.0)

    resume_skills_norm: Set[str] = set(weighted_skills)
    matched: Set[str] = resume_skills_norm & job_skills
    missing: Set[str] = resume_skills_norm - job_skills

    if weighted_skills:
        total_weight = sum(weighted_skills.values())
        matched_weight = sum(weighted_skills[skill] for skill in matched)
        raw_ratio = matched_weight / total_weight
        skills_score = min(100.0, max(20.0, raw_ratio * 100.0 + (15.0 if matched else 0.0)))
    else:
        skills_score = 50.0

    # Experience fit
    exp_score = experience_fit_score(job, profile, user_prefs)

    # Role similarity — title keyword overlap
    role_score = _role_similarity(job.title, profile)

    # Industry / company type
    ind, c_type, _ = classify_company(job.company, job.title, job.description or "")

    pref_industries = user_prefs.get("preferred_industries") or profile.preferred_industries
    is_any_ind = not pref_industries or "any" in [i.lower() for i in pref_industries]
    ind_score = 90.0 if is_any_ind or any(pi.lower() in ind.lower() for pi in pref_industries) else 50.0

    pref_ctypes = user_prefs.get("preferred_company_types") or profile.preferred_company_types
    is_any_ctype = not pref_ctypes or "any" in [ct.lower() for ct in pref_ctypes]
    ctype_score = 90.0 if is_any_ctype or any(pct.lower() == c_type.lower() for pct in pref_ctypes) else 50.0

    # Location fit
    rem_pref = user_prefs.get("remote_preference") or profile.remote_preference or "any"
    loc_score = 95.0 if job.remote or rem_pref == "any" else 80.0

    matched_list = sorted(matched)
    missing_list = sorted(missing)

    factors: Dict[str, Any] = {
        "skills_overlap": skills_score,
        "experience_fit": exp_score,
        "role_similarity": role_score,
        "industry_fit": ind_score,
        "company_type_fit": ctype_score,
        "location_fit": loc_score,
        "posting_freshness": 95.0,
        "strengths": (
            [f"Matched skills: {', '.join(matched_list[:3])}"] if matched_list
            else ["Matches target role profile"]
        ),
        "gaps": (
            [f"Missing: {', '.join(missing_list[:2])}"] if missing_list
            else ["No major gaps identified"]
        ),
    }
    return _calculate_weighted_score(job, profile, factors, ind, c_type)
