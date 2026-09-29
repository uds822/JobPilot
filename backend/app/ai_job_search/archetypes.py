"""
Role archetype configuration for AI job search.
Add new archetypes here without touching classifier or query generator code.
"""

# ── Archetype skill sets ──────────────────────────────────────────────────────
# Each skill must be in normalized form (lowercase, canonical alias).
# Use the same canonical names as SKILL_ALIASES in skill_normalizer.py.

ARCHETYPES: dict[str, dict] = {
    "AI_ENGINEER": {
        "skills": {
            "python", "llm", "rag", "langchain", "agents", "fastapi",
            "pytorch", "openai", "vector database", "embeddings",
            "transformers", "huggingface", "generative ai", "prompt engineering",
        },
    },
    "BACKEND_DEV": {
        "skills": {
            "python", "fastapi", "django", "flask", "node.js", "postgresql",
            "redis", "docker", "rest api", "grpc", "microservices",
            "celery", "sqlalchemy", "aws", "kubernetes",
        },
    },
    "ML_ENGINEER": {
        "skills": {
            "python", "pytorch", "tensorflow", "scikit-learn", "mlflow",
            "feature engineering", "model deployment", "spark", "pandas",
            "numpy", "xgboost", "kubeflow", "data pipeline",
        },
    },
    "DATA_ENGINEER": {
        "skills": {
            "python", "spark", "airflow", "kafka", "dbt", "snowflake",
            "bigquery", "redshift", "etl", "data pipeline", "postgresql",
            "aws", "databricks", "pandas",
        },
    },
    "FULL_STACK": {
        "skills": {
            "python", "javascript", "typescript", "react", "node.js",
            "fastapi", "django", "postgresql", "rest api", "docker",
            "html", "css", "next.js", "aws",
        },
    },
    # Future archetypes — uncomment when ready:
    # "MLOPS_ENGINEER": { ... },
    # "DATA_SCIENTIST": { ... },
    # "DEVOPS_ENGINEER": { ... },
    # "CLOUD_ENGINEER": { ... },
    # "SOFTWARE_ENGINEER": { ... },
}


# ── Query templates per archetype ─────────────────────────────────────────────
# 2-3 natural-language search queries per archetype.
# These are passed directly to Adzuna's `what` parameter.

ARCHETYPE_QUERIES: dict[str, list[str]] = {
    "AI_ENGINEER": [
        "AI engineer",
        "LLM engineer",
        "GenAI developer",
    ],
    "BACKEND_DEV": [
        "backend engineer",
        "Python backend developer",
        "backend software engineer",
    ],
    "ML_ENGINEER": [
        "machine learning engineer",
        "ML engineer",
        "applied ML engineer",
    ],
    "DATA_ENGINEER": [
        "data engineer",
        "data pipeline engineer",
        "ETL engineer",
    ],
    "FULL_STACK": [
        "full stack developer",
        "full stack engineer",
        "software engineer full stack",
    ],
}
