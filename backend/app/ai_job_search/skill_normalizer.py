"""
Skill normalization — canonical alias mapping.

Rules applied in order:
  1. Lowercase + strip whitespace
  2. Alias substitution (aliases → canonical form)
  3. Punctuation / spacing collapse

All archetypes, resume parsers, and job skill extractors must run skills
through normalize_skill() before comparison so "fast api", "fast-api",
and "FastAPI" are all treated as the same skill.
"""

# Alias → canonical mapping.
# Keys must be lowercase. Values are the canonical (also lowercase) form.
SKILL_ALIASES: dict[str, str] = {
    # Python ecosystem
    "fast api":        "fastapi",
    "fast-api":        "fastapi",
    "fast_api":        "fastapi",
    # Databases
    "postgres":        "postgresql",
    "postgres sql":    "postgresql",
    "postgre sql":     "postgresql",
    "psql":            "postgresql",
    "mongo":           "mongodb",
    "mongo db":        "mongodb",
    # JavaScript / TypeScript
    "js":              "javascript",
    "ts":              "typescript",
    "node":            "node.js",
    "nodejs":          "node.js",
    "node js":         "node.js",
    "nextjs":          "next.js",
    "next js":         "next.js",
    "reactjs":         "react",
    "react js":        "react",
    "vuejs":           "vue.js",
    "vue js":          "vue.js",
    # AI / ML
    "lang chain":      "langchain",
    "lang-chain":      "langchain",
    "hugging face":    "huggingface",
    "open ai":         "openai",
    "llms":            "llm",
    "large language model": "llm",
    "large language models": "llm",
    "rag":             "rag",
    "retrieval augmented generation": "rag",
    "gen ai":          "generative ai",
    "genai":           "generative ai",
    "pytorch":         "pytorch",
    "torch":           "pytorch",
    "tensorflow":      "tensorflow",
    "tf":              "tensorflow",
    "scikit learn":    "scikit-learn",
    "sklearn":         "scikit-learn",
    "xg boost":        "xgboost",
    # Cloud / Infra
    "amazon web services": "aws",
    "gcp":             "google cloud",
    "google cloud platform": "google cloud",
    "azure":           "microsoft azure",
    "k8s":             "kubernetes",
    "kube":            "kubernetes",
    # Data
    "apache spark":    "spark",
    "apache kafka":    "kafka",
    "apache airflow":  "airflow",
    "big query":       "bigquery",
    # Other
    "rest":            "rest api",
    "restful":         "rest api",
    "restful api":     "rest api",
    "graphql api":     "graphql",
    "ci cd":           "ci/cd",
    "ci-cd":           "ci/cd",
    "continuous integration": "ci/cd",
}


def normalize_skill(skill: str) -> str:
    """
    Normalize a skill name to its canonical lowercase form.

    Steps:
      1. Lowercase + strip
      2. Alias lookup
      3. Collapse internal whitespace
    """
    s = skill.lower().strip()
    # Direct alias hit
    if s in SKILL_ALIASES:
        return SKILL_ALIASES[s]
    # Collapse multiple spaces and try again
    s_collapsed = " ".join(s.split())
    if s_collapsed in SKILL_ALIASES:
        return SKILL_ALIASES[s_collapsed]
    return s_collapsed


def normalize_skills(skills: list[str]) -> list[str]:
    """Normalize a list of skills, preserving order, removing duplicates."""
    seen: set[str] = set()
    result: list[str] = []
    for s in skills:
        n = normalize_skill(s)
        if n and n not in seen:
            seen.add(n)
            result.append(n)
    return result
