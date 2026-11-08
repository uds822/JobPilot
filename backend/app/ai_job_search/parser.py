import re
import io
import json
import logging
import httpx

from app.config import settings
from app.ai_job_search.schemas import ResumeProfileSchema

logger = logging.getLogger(__name__)

RESUME_PARSE_PROMPT = """\
Extract a structured candidate profile from this resume text.
Return ONLY a valid JSON object matching this exact schema — no other text:
{{
  "skills": ["string"],
  "skill_groups": {{
    "primary": ["core skills clearly demonstrated in recent work or projects"],
    "supporting": ["additional relevant skills"],
    "tools": ["frameworks, platforms, databases and developer tools"],
    "domain": ["industry and problem-domain expertise"]
  }},
  "years_experience": number,
  "recent_titles": ["string"],
  "target_roles": ["up to 10 evidence-backed roles, ordered by strongest fit; include backend Python, SDE I, applied GenAI/LLM roles, and applied ML only when resume evidence supports them"],
  "seniority_level": "entry" | "mid" | "senior" | "lead" | "exec",
  "preferred_locations": ["string"],
  "remote_preference": "remote" | "hybrid" | "onsite" | "any",
  "industries": ["string"],
  "preferred_industries": ["string"],
  "preferred_company_types": ["startup" | "product" | "services" | "consulting" | "enterprise" | "other"],
  "salary_expectation_min": number or null,
  "salary_expectation_max": number or null,
  "salary_currency": "USD"
}}

RESUME TEXT:
{text}
"""


def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """Extract raw text from PDF or DOCX file bytes."""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

    if ext == "pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            blocks = [text for page in reader.pages if (text := page.extract_text())]
            extracted = "\n".join(blocks).strip()
            if not extracted:
                raise ValueError("No selectable text found in this PDF. Upload a text-based PDF or DOCX.")
            return extracted
        except ImportError as e:
            logger.exception("PDF extraction dependency pypdf is unavailable")
            raise ValueError("PDF support is not installed in the backend. Install backend requirements and restart the API.") from e
        except ValueError:
            raise
        except Exception as e:
            logger.exception("PDF text extraction failed")
            raise ValueError("Could not read this PDF. Try exporting it as a text-based PDF or DOCX.") from e

    if ext in ("docx", "doc"):
        try:
            import docx
            doc = docx.Document(io.BytesIO(file_bytes))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            logger.warning(f"DOCX extraction failed: {e}")
            return file_bytes.decode("utf-8", errors="ignore")

    return file_bytes.decode("utf-8", errors="ignore")


def _extract_json(raw: str) -> dict:
    """Strip markdown fences and extract the first JSON object."""
    clean = re.sub(r"^```json\s*", "", raw, flags=re.MULTILINE)
    clean = re.sub(r"^```\s*", "", clean, flags=re.MULTILINE)
    m = re.search(r'\{.*\}', clean, re.DOTALL)
    if m:
        clean = m.group(0)
    return json.loads(clean.strip())


async def _try_llm_parse(text: str) -> dict | None:
    """
    Try Groq (primary, ~1.4s) then OpenRouter (fallback, ~10s).
    Returns parsed dict or None.
    """
    groq_key = settings.GROQ_API_KEY
    groq_model = settings.GROQ_MODEL
    or_key = settings.OPENROUTER_API_KEY
    or_model = settings.OPENROUTER_MODEL

    prompt = RESUME_PARSE_PROMPT.format(text=text[:4000])

    providers = []
    if groq_key:
        providers.append({
            "name": "Groq",
            "url": "https://api.groq.com/openai/v1/chat/completions",
            "headers": {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
            "model": groq_model,
            "timeout": 20.0,
        })
    if or_key:
        providers.append({
            "name": "OpenRouter",
            "url": "https://openrouter.ai/api/v1/chat/completions",
            "headers": {
                "Authorization": f"Bearer {or_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://jobpilot.app",
                "X-Title": "JobPilot Resume Parser",
            },
            "model": or_model,
            "timeout": 30.0,
        })

    for p in providers:
        try:
            body = {
                "model": p["model"],
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 1024,
            }
            async with httpx.AsyncClient(timeout=p["timeout"]) as client:
                resp = await client.post(p["url"], headers=p["headers"], json=body)
                if resp.status_code == 200:
                    raw = resp.json()["choices"][0]["message"]["content"]
                    result = _extract_json(raw)
                    logger.info(f"Resume parsed via {p['name']} ({p['model']})")
                    return result
                else:
                    logger.warning(f"{p['name']} HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"{p['name']} resume parse failed: {e}")

    return None


def _heuristic_parse(text: str) -> ResumeProfileSchema:
    """Keyword-based heuristic parser — used when no LLM is available."""
    text_lower = text.lower()

    from app.ai_job_search.job_skill_extractor import KNOWN_SKILLS, extract_job_skills
    from app.ai_job_search.skill_normalizer import normalize_skill

    canonical_skills = sorted(extract_job_skills(text, KNOWN_SKILLS, normalize_skill))
    display_names = {
        "aws": "AWS", "c++": "C++", "c#": "C#", "ci/cd": "CI/CD",
        "fastapi": "FastAPI", "javascript": "JavaScript", "node.js": "Node.js",
        "postgresql": "PostgreSQL", "react": "React", "rest api": "REST API",
        "sql": "SQL", "typescript": "TypeScript",
    }
    found_skills = [display_names.get(skill, skill.title()) for skill in canonical_skills]
    tool_names = {
        "aws", "microsoft azure", "google cloud", "docker", "kubernetes", "terraform",
        "jenkins", "git", "linux", "postgresql", "mysql", "mongodb", "redis", "jira",
    }
    tools = [name for skill, name in zip(canonical_skills, found_skills) if skill in tool_names]
    primary = [name for skill, name in zip(canonical_skills, found_skills) if skill not in tool_names]

    years = 0.0
    yr_match = re.search(r"(\d+)\+?\s*years?(?:\s+of)?\s+experience", text_lower)
    if yr_match:
        try:
            years = float(yr_match.group(1))
        except ValueError:
            pass

    seniority = "mid"
    if "senior" in text_lower or "lead" in text_lower or years >= 5:
        seniority = "senior"
    elif "principal" in text_lower or "architect" in text_lower:
        seniority = "lead"
    elif "junior" in text_lower or "entry" in text_lower or years <= 1:
        seniority = "entry"

    role_patterns = (
        ("Machine Learning Engineer", ("machine learning engineer", "ml engineer")),
        ("AI Engineer", ("ai engineer", "artificial intelligence engineer")),
        ("Data Engineer", ("data engineer",)),
        ("Data Scientist", ("data scientist",)),
        ("Backend Engineer", ("backend engineer", "backend developer")),
        ("Frontend Engineer", ("frontend engineer", "frontend developer")),
        ("Full Stack Engineer", ("full stack engineer", "full-stack engineer", "full stack developer")),
        ("DevOps Engineer", ("devops engineer", "site reliability engineer", "sre")),
        ("Software Engineer", ("software engineer", "software developer")),
    )
    titles = [label for label, phrases in role_patterns if any(phrase in text_lower for phrase in phrases)][:3]

    return ResumeProfileSchema(
        skills=found_skills,
        skill_groups={"primary": primary, "tools": tools},
        years_experience=years,
        recent_titles=titles,
        target_roles=titles.copy(),
        seniority_level=seniority,
        preferred_locations=[],
        remote_preference="remote" if "remote" in text_lower else "any",
        industries=[],
        preferred_industries=[],
        preferred_company_types=[],
        salary_expectation_min=None,
        salary_expectation_max=None,
        salary_currency="USD",
        parse_method="heuristic",
    )


def _infer_target_roles(
    profile: ResumeProfileSchema, evidence_text: str = ""
) -> ResumeProfileSchema:
    roles: list[str] = []
    declared_roles = list(profile.target_roles) + list(profile.recent_titles)
    normalized_skills = {
        skill.lower().replace(" ", "")
        for skill in profile.skills
        + profile.skill_groups.primary
        + profile.skill_groups.supporting
        + profile.skill_groups.tools
        + profile.skill_groups.domain
    }
    evidence = f"{evidence_text} {' '.join(profile.recent_titles)}".lower()

    has_python = "python" in normalized_skills or "python" in evidence
    backend_signals = (
        "fastapi", "django", "flask", "postgresql", "sqlalchemy", "restapi",
        "redis", "microservices", "backend engineer", "backend developer",
    )
    has_backend_evidence = any(
        signal.replace(" ", "") in normalized_skills or signal in evidence
        for signal in backend_signals
    )
    ai_signals = (
        "llm", "langchain", "langgraph", "rag", "agentic", "generative ai",
        "azure ai foundry", "semantic kernel", "vector search", "embeddings",
    )
    matched_ai_signals = [signal for signal in ai_signals if signal in evidence or signal.replace(" ", "") in normalized_skills]
    has_ai_evidence = len(matched_ai_signals) >= 2

    current_title_is_software = any(
        title in evidence for title in ("software engineer", "software development engineer", "sde")
    )
    if current_title_is_software and profile.years_experience <= 3:
        roles.append("Software Development Engineer I")
    if has_python and has_backend_evidence:
        roles.extend(("Python Backend Engineer", "Backend Developer"))
    if has_ai_evidence:
        roles.extend(("Applied AI Engineer", "Generative AI Engineer", "LLM Application Engineer"))
    if has_python and has_backend_evidence and has_ai_evidence:
        roles.append("AI Backend Engineer")
    if any(term in evidence for term in ("sentence transformers", "model deployment", "machine learning")):
        roles.extend(("Applied Machine Learning Engineer", "Machine Learning Engineer"))

    if roles:
        roles.extend(declared_roles)
        profile.target_roles = list(dict.fromkeys(role.strip() for role in roles if role.strip()))[:10]
        return profile
    if declared_roles:
        profile.target_roles = list(dict.fromkeys(role.strip() for role in declared_roles if role.strip()))[:10]
        return profile

    from app.ai_job_search.resume_archetype import classify_resume

    role_names = {
        "AI_ENGINEER": "AI Engineer",
        "BACKEND_DEV": "Backend Engineer",
        "ML_ENGINEER": "Machine Learning Engineer",
        "DATA_ENGINEER": "Data Engineer",
        "FULL_STACK": "Full Stack Engineer",
    }
    ranked = classify_resume(profile)["top_archetypes"]
    profile.target_roles = [
        role_names[item["name"]]
        for item in ranked
        if item["confidence"] >= 0.2 and item["name"] in role_names
    ][:3]
    return profile


async def parse_resume_content(file_bytes: bytes, filename: str) -> ResumeProfileSchema:
    """
    Parse a PDF/DOCX resume into a structured ResumeProfileSchema.

    Flow:
      1. Extract raw text from file (PDF/DOCX)
      2. Try Groq gpt-oss-120b (~1.4s)
      3. Try OpenRouter llama-3.3-70b-instruct (~10s)
      4. Heuristic keyword fallback
    """
    raw_text = extract_text_from_file(file_bytes, filename)
    if not raw_text.strip():
        raise ValueError("No readable text found in this resume. Try a text-based PDF or DOCX file.")

    parsed = await _try_llm_parse(raw_text)
    if parsed:
        try:
            profile = ResumeProfileSchema(**parsed, parse_method="llm")
            if profile.skills or profile.recent_titles:
                return _infer_target_roles(profile, raw_text)
            logger.warning("LLM returned an empty resume profile; using heuristic extraction")
        except Exception as e:
            logger.warning(f"Schema validation failed for LLM output: {e}")

    logger.warning("Using heuristic resume extraction")
    profile = _infer_target_roles(_heuristic_parse(raw_text), raw_text)
    if not profile.skills and not profile.recent_titles and not profile.target_roles:
        raise ValueError("Could not identify skills or job roles in this resume. Check that it contains selectable text.")
    return profile
