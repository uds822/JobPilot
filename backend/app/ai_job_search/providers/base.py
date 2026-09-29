from abc import ABC, abstractmethod
from typing import List, Dict, Any
import hashlib
from app.ai_job_search.schemas import NormalizedJobSchema


class JobProvider(ABC):
    """Abstract Base Class for external Job Board Providers."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def search(self, query: str, location: str = "us", min_salary: float | None = None, company: str | None = None, max_results: int = 20) -> List[NormalizedJobSchema]:
        """Fetch job postings for a query and location."""
        pass

    def generate_job_hash(self, source: str, external_id: str) -> str:
        """Create a deterministic hash for deduplication across database runs."""
        raw = f"{source.lower().strip()}:{external_id.strip()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
