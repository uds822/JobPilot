"""
Step 9.1 — Deterministic job skill extractor with capped LLM fallback.

Public interface:
    extract_job_skills(description_text, known_skills, normalizer) -> set[str]

Constants (configurable):
    MIN_CONFIDENT_SKILLS          — minimum extracted skills to trust rule-based result
    MAX_LLM_FALLBACK_PER_SEARCH   — hard cap on LLM calls when rule-based is sparse

Architecture:
    500 jobs
        |
        v
    deterministic dictionary extraction  (this file, no network)
        |
        +-- confident (≥ MIN_CONFIDENT_SKILLS) → score immediately, no LLM
        |
        +-- low confidence
                    |
                    v
             capped at MAX_LLM_FALLBACK_PER_SEARCH
                    |
                    v
             optional LLM (≤ 15 calls, not 500)
"""
from __future__ import annotations

import re

from app.ai_job_search.skill_normalizer import normalize_skill, SKILL_ALIASES
from app.ai_job_search.archetypes import ARCHETYPES

# ── Tunable constants ─────────────────────────────────────────────────────────
MIN_CONFIDENT_SKILLS: int = 2
"""
Minimum number of skills that must be extracted deterministically for the
result to be considered confident. Jobs below this threshold join the
LLM fallback queue.
"""

MAX_LLM_FALLBACK_PER_SEARCH: int = 15
"""
Hard cap on LLM calls per search run.
If the fallback queue has 100 low-confidence jobs, only MAX_LLM_FALLBACK_PER_SEARCH
of them will get an LLM call; the rest are scored with the sparse deterministic result.
"""

# ── Build KNOWN_SKILLS vocabulary at import time ──────────────────────────────
# Source 1: All canonical forms from alias map
_alias_canonicals: set[str] = set(SKILL_ALIASES.values())

# Source 2: All archetype skill sets (normalized)
_archetype_skills: set[str] = set()
for _arch in ARCHETYPES.values():
    for _s in _arch["skills"]:
        _archetype_skills.add(normalize_skill(_s))

# Source 3: Extended vocabulary — skills common in Indian tech job listings
# that aren't already covered by archetypes or aliases.
_EXTENDED_SKILLS: set[str] = {
    # Languages
    "java", "c++", "c#", "go", "golang", "rust", "scala", "ruby", "php",
    "kotlin", "swift", "r",
    # Frameworks / libraries
    "spring", "spring boot", "express.js", "rails", "laravel", "asp.net",
    "angular", "vue.js", "svelte", "gatsby",
    "pandas", "numpy", "matplotlib", "seaborn", "plotly",
    "huggingface", "transformers", "langchain", "openai",
    "scikit-learn", "xgboost", "lightgbm", "catboost",
    "pytorch", "tensorflow", "keras",
    # Databases
    "mysql", "sqlite", "oracle", "mariadb", "dynamodb",
    "cassandra", "couchdb", "neo4j", "influxdb",
    "elasticsearch", "solr", "opensearch", "postgresql", "mongodb",
    "snowflake", "bigquery", "redshift", "databricks",
    # Cloud / infra
    "google cloud", "microsoft azure",
    "terraform", "ansible", "chef", "puppet",
    "jenkins", "github actions", "gitlab ci", "circleci", "azure devops",
    "nginx", "apache", "haproxy",
    "linux", "ubuntu", "bash", "shell scripting",
    "rabbitmq", "celery", "sqs", "pubsub",
    # Data / AI
    "machine learning", "deep learning", "natural language processing",
    "nlp", "computer vision", "reinforcement learning",
    "data science", "data analysis", "data visualization", "data engineering",
    "etl", "data pipeline", "feature engineering", "model deployment",
    "mlflow", "kubeflow", "airflow", "spark", "kafka",
    "dbt", "hive", "presto", "flink",
    "tableau", "power bi", "looker", "metabase",
    # APIs / architecture
    "rest api", "graphql", "grpc", "websocket",
    "microservices", "event driven", "cqrs", "ddd",
    "system design", "software architecture", "api design",
    # DevOps
    "docker", "kubernetes", "helm", "istio",
    "aws", "ec2", "s3", "lambda", "ecs", "eks",
    "ci/cd", "devops", "site reliability",
    # Testing
    "pytest", "jest", "mocha", "junit", "selenium", "cypress",
    "unit testing", "integration testing", "test driven development",
    # Other
    "agile", "scrum", "kanban", "jira", "confluence",
    "git", "github", "gitlab",
    "oauth", "jwt", "security", "cryptography",
    "redis", "memcached",
    "react native", "flutter", "ionic",
    "hadoop", "hbase",
    "opencv", "ffmpeg",
    "llm", "rag", "generative ai", "prompt engineering",
    "vector database", "embeddings", "agents",
}

KNOWN_SKILLS: set[str] = _alias_canonicals | _archetype_skills | _EXTENDED_SKILLS


# ── Tokenizer ─────────────────────────────────────────────────────────────────
_HTML_TAG = re.compile(r"<[^>]+>")
_NOISE = re.compile(r"[^\w\s.\+#\/\-]")
_WHITESPACE = re.compile(r"\s+")


def _tokenize(text: str) -> list[str]:
    """
    Strip HTML, lowercase, remove noise, return word tokens.
    Preserves characters that are meaningful in skill names:
        .  → node.js
        +  → c++
        #  → c#
        /  → ci/cd, rest api/graphql
        -  → scikit-learn
    """
    text = _HTML_TAG.sub(" ", text)
    text = text.lower()
    text = _NOISE.sub(" ", text)
    text = _WHITESPACE.sub(" ", text).strip()
    
    # Split into words and strip trailing punctuation from tokens
    # so 'postgresql.' becomes 'postgresql'
    tokens = text.split()
    return [t.strip(".,;") for t in tokens if t.strip(".,;")]


def extract_job_skills(
    description_text: str,
    known_skills: set[str],
    normalizer,
) -> set[str]:
    """
    Deterministic dictionary-based job skill extraction.

    Generates 1-gram, 2-gram, and 3-gram windows from the tokenized
    description, normalizes each phrase, and matches against known_skills.
    Multi-word phrases (e.g. "rest api", "machine learning") are handled
    explicitly through the n-gram window.

    Args:
        description_text: raw job description (HTML allowed, will be stripped).
        known_skills:     set of canonical skill names to match against.
        normalizer:       callable(str) -> str; must be the same normalizer used
                          to build known_skills entries.

    Returns:
        Set of canonical skill strings found in the description.

    Complexity: O(3n) where n = number of tokens — well under 100 ms on CPU.
    No network call. No LLM call. No exceptions for normal input.
    """
    if not description_text:
        return set()

    tokens = _tokenize(description_text)
    n = len(tokens)
    found: set[str] = set()

    # Longer windows first so "machine learning" matches before "machine" or "learning"
    for window_size in (3, 2, 1):
        if window_size > n:
            continue
        for i in range(n - window_size + 1):
            phrase = " ".join(tokens[i : i + window_size])
            canonical = normalizer(phrase)
            if canonical in known_skills:
                found.add(canonical)

    return found
