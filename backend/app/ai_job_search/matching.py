import re
import json
import logging
from typing import Dict, Any, Tuple, Optional, Set
import httpx


from app.config import settings
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

CANDIDATE: Skills: {skills}. Experience: {exp} years. Recent roles: {titles}.
JOB: Title: {title}. Company: {company}. Location: {location}.
Description: {desc}

RULE: If job requires more than {exp_limit} years experience, set experience_fit=20. Otherwise set experience_fit to 85 or higher.
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


def extract_required_experience(title: str, description: str) -> Optional[float]:
    """Extract minimum required years of experience via regex."""
    text = f"{title} {description}".lower()
    patterns = [
        r'(?:min|minimum|at least)?\s*(\d+(?:\.\d+)?)\s*(?:-|to|\+)?\s*(?:\d+(?:\.\d+)?)?\s*(?:yrs?|years?)\s*(?:of)?\s*(?:exp|experience)?',
        r'(\d+(?:\.\d+)?)\s*\+\s*(?:yrs?|years?)',
        r'(\d+(?:\.\d+)?)\s*to\s*(\d+(?:\.\d+)?)\s*years'
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            try:
                val = float(m.group(1))
                if 0.5 <= val <= 25.0:
                    return val
            except ValueError:
                pass
    return None


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
    cand_exp = float(user_prefs.get("years_experience") or profile.years_experience or 1.0)
    skills_str = ", ".join(profile.skills[:10]) if profile.skills else "Not specified"
    titles_str = ", ".join(profile.recent_titles[:3]) if profile.recent_titles else "Software Engineer"
    desc_snippet = (job.description or "")[:800]

    prompt = RESUME_SCHEMA_PROMPT.format(
        skills=skills_str,
        exp=cand_exp,
        titles=titles_str,
        title=job.title,
        company=job.company,
        location=job.location,
        desc=desc_snippet,
        exp_limit=round(cand_exp + 1.0, 1),
    )

    factors = await _call_llm(prompt, timeout=15.0)
    if factors:
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
    cand_exp = float(user_prefs.get("years_experience") or profile.years_experience or 1.0)

    matching = [s for s in profile.skills if s.lower() in job_text]
    missing = [s for s in profile.skills if s.lower() not in job_text]

    skills_score = (len(matching) / max(len(profile.skills), 1)) * 100.0
    skills_score = min(100.0, max(20.0, skills_score + 15.0 if matching else 20.0))

    req_exp = extract_required_experience(job.title, job.description or "")
    exp_score = 95.0 if (req_exp is None or req_exp <= cand_exp + 0.25) else 30.0

    role_score = 70.0
    t_lower = job.title.lower()
    for title in profile.recent_titles:
        terms = [t for t in title.lower().split() if len(t) > 2]
        if any(term in t_lower for term in terms):
            role_score = 95.0
            break

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

    cand_exp = float(user_prefs.get("years_experience") or profile.years_experience or 1.0)

    # Normalize resume skills to canonical form for fair comparison
    resume_skills_norm: Set[str] = {normalize_skill(s) for s in profile.skills}

    # Skill overlap: what fraction of resume skills appear in job requirements?
    matched: Set[str] = resume_skills_norm & job_skills
    missing: Set[str] = resume_skills_norm - job_skills

    if resume_skills_norm:
        raw_ratio = len(matched) / len(resume_skills_norm)
        skills_score = min(100.0, max(20.0, raw_ratio * 100.0 + (15.0 if matched else 0.0)))
    else:
        skills_score = 50.0

    # Experience fit
    req_exp = extract_required_experience(job.title, job.description or "")
    exp_score = 95.0 if (req_exp is None or req_exp <= cand_exp + 0.25) else 30.0

    # Role similarity — title keyword overlap
    role_score = 70.0
    t_lower = job.title.lower()
    for title in profile.recent_titles:
        terms = [t for t in title.lower().split() if len(t) > 2]
        if any(term in t_lower for term in terms):
            role_score = 95.0
            break

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
