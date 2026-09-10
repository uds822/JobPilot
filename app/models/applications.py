from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base


class Application(Base):


    __tablename__ = "applications"

    __table_args__ = (
         UniqueConstraint(
             "user_id",
             "job_id",
             name="uq_user_job_application"
        ),
     )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )

    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id"),
        nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default="APPLIED"
    )

    applied_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    notes: Mapped[str | None] = mapped_column(Text)

    user = relationship("User", back_populates="applications")
    job = relationship("Job", back_populates="applications")