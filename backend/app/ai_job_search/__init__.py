"""
AI Job Search Package
Isolated feature module for parsing resumes, fetching job listings from Adzuna, Greenhouse, and Lever,
filtering, deduplicating, scoring, and providing API endpoints for AI-matched jobs.
"""

__all__ = ["ai_jobs_router"]


def __getattr__(name):
    # Workers import provider helpers without bootstrapping the HTTP router.
    if name == "ai_jobs_router":
        from app.ai_job_search.router import router
        return router
    raise AttributeError(name)
