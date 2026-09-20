import pytest
from app.models.applications import Application
from app.models.companies import Company
from app.models.jobs import Job
from app.models.users import User
from app.services.application import get_user_applications_paginated, get_kanban_board_data


def create_test_user(db, username="testuser_kanban", email="kanban@example.com"):
    user = User(username=username, email=email, hashed_password="hashed_pw_123")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_test_company(db, name="Test Co"):
    company = Company(name=name)
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def create_test_job(db, company_id, title="Test Job"):
    job = Job(title=title, company_id=company_id)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def test_empty_applications_kanban(db_session):
    user = create_test_user(db_session, "user_empty", "empty@example.com")
    data = get_kanban_board_data(db_session, user, limit_per_status=20)

    assert "applied" in data
    assert data["applied"]["total"] == 0
    assert data["applied"]["items"] == []
    assert data["applied"]["has_more"] is False


def test_applications_pagination_and_max_limit_capping(db_session):
    user = create_test_user(db_session, "user_pagination", "pagination@example.com")
    company = create_test_company(db_session, "Pagination Co")

    # Create 250 test applications for this user across APPLIED status
    for i in range(250):
        job = create_test_job(db_session, company.id, f"Software Dev #{i}")
        app = Application(user_id=user.id, job_id=job.id, status="APPLIED", notes=f"Note #{i}")
        db_session.add(app)
    db_session.commit()

    # Query with default limit=20, offset=0
    res1 = get_user_applications_paginated(db_session, user, status="APPLIED", limit=20, offset=0)
    assert res1["total"] == 250
    assert len(res1["items"]) == 20
    assert res1["has_more"] is True

    # Query next batch offset=20
    res2 = get_user_applications_paginated(db_session, user, status="APPLIED", limit=20, offset=20)
    assert len(res2["items"]) == 20
    assert res2["has_more"] is True

    # Test max limit capping: passing limit=500 should cap limit to 100
    res_max = get_user_applications_paginated(db_session, user, status="APPLIED", limit=500, offset=0)
    assert res_max["limit"] == 100
    assert len(res_max["items"]) == 100
    assert res_max["has_more"] is True

    # Test final batch offset=240
    res_end = get_user_applications_paginated(db_session, user, status="APPLIED", limit=20, offset=240)
    assert len(res_end["items"]) == 10
    assert res_end["has_more"] is False


def test_user_isolation(db_session):
    user1 = create_test_user(db_session, "user1_iso", "user1_iso@example.com")
    user2 = create_test_user(db_session, "user2_iso", "user2_iso@example.com")
    company = create_test_company(db_session, "Iso Co")
    job1 = create_test_job(db_session, company.id, "Job 1")
    job2 = create_test_job(db_session, company.id, "Job 2")

    app1 = Application(user_id=user1.id, job_id=job1.id, status="APPLIED")
    app2 = Application(user_id=user2.id, job_id=job2.id, status="OFFERED")
    db_session.add_all([app1, app2])
    db_session.commit()

    user1_data = get_kanban_board_data(db_session, user1)
    user2_data = get_kanban_board_data(db_session, user2)

    assert user1_data["applied"]["total"] == 1
    assert user1_data["offered"]["total"] == 0

    assert user2_data["applied"]["total"] == 0
    assert user2_data["offered"]["total"] == 1
