from app.database.database import SessionLocal
from app.models.jobs import Job

#This is db session we are testing and adding a new job to the database
db=SessionLocal()

new_job=Job(
    title="Software Engineer",
    company="Tech Company", 
    location="New York, NY",
    job_url="https://www.techcompany.com/jobs/software-engineer",
    description="We are looking for a skilled software engineer to join our team.",
    employment_type="Full-time"
)

db.add(new_job)
db.commit()
db.refresh(new_job)

print(f"New job added with ID: {new_job.id}")

db.close()