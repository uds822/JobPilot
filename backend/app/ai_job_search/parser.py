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
  "years_experience": number,
  "recent_titles": ["string"],
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
            blocks = [page.extract_text() for page in reader.pages if page.extract_text()]
            return "\n".join(blocks)
        except Exception as e:
            logger.warning(f"PDF extraction failed: {e}")
            return file_bytes.decode("utf-8", errors="ignore")

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

    known_skills = [
        "python", "fastapi", "react", "typescript", "javascript", "postgresql", "postgres",
        "sql", "aws", "docker", "kubernetes", "rest api", "html", "css", "node.js",
        "express", "git", "ci/cd", "microservices", "redis", "alembic", "sqlalchemy",
        "graphql", "tailwind", "next.js", "vite", "pytest", "django", "flask",
    ]
    found_skills = [s.title() for s in known_skills if s in text_lower]
    if not found_skills:
        found_skills = ["Python", "FastAPI", "React", "PostgreSQL"]

    years = 3.5
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

    titles = []
    if "senior" in text_lower:
        titles.append("Senior Software Engineer")
    if "software" in text_lower or "developer" in text_lower:
        titles.append("Software Engineer")
    if not titles:
        titles = ["Full Stack Engineer", "Backend Developer"]

    return ResumeProfileSchema(
        skills=found_skills,
        years_experience=years,
        recent_titles=titles,
        seniority_level=seniority,
        preferred_locations=[],
        remote_preference="remote" if "remote" in text_lower else "any",
        industries=[],
        preferred_industries=[],
        preferred_company_types=[],
        salary_expectation_min=None,
        salary_expectation_max=None,
        salary_currency="USD",
    )


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
        logger.warning("Empty resume text — using default profile")
        raw_text = "Experienced Software Engineer with background in Python, FastAPI, React, PostgreSQL, and AWS."

    parsed = await _try_llm_parse(raw_text)
    if parsed:
        try:
            return ResumeProfileSchema(**parsed)
        except Exception as e:
            logger.warning(f"Schema validation failed for LLM output: {e}")

    logger.warning("All LLM parsers failed — using heuristic fallback")
    return _heuristic_parse(raw_text)
