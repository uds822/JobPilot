from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import sessionmaker
from app.database.database import Base
from app.schemas.job import JobStatus
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship
#database model for jobs
class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(200))
    job_url: Mapped[str | None] = mapped_column(Text,unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    employment_type: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50), default="SAVED")
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)

    company = relationship("Company", back_populates="jobs")
    applications = relationship("Application", back_populates="job")