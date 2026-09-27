import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.users import User
from app.models.companies import Company
from app.models.jobs import Job
from app.models.applications import Application
from app.security.security import hash_password, create_access_token


@pytest.fixture
def user_a(db_session: Session) -> User:
    user = User(
        username="user_a",
        email="user_a@example.com",
        password_hash=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def headers_a(user_a: User) -> dict[str, str]:
    token = create_access_token({"sub": str(user_a.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_b(db_session: Session) -> User:
    user = User(
        username="user_b",
        email="user_b@example.com",
        password_hash=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def headers_b(user_b: User) -> dict[str, str]:
    token = create_access_token({"sub": str(user_b.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def app_a(db_session: Session, user_a: User, test_company: Company) -> Application:
    job = Job(
        title="Job User A",
        company_id=test_company.id,
        job_url="https://example.com/job_a",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    app_obj = Application(
        user_id=user_a.id,
        job_id=job.id,
        status="APPLIED",
        notes="Notes for App A",
    )
    db_session.add(app_obj)
    db_session.commit()
    db_session.refresh(app_obj)
    return app_obj


@pytest.fixture
def app_b(db_session: Session, user_b: User, test_company: Company) -> Application:
    job = Job(
        title="Job User B",
        company_id=test_company.id,
        job_url="https://example.com/job_b",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    app_obj = Application(
        user_id=user_b.id,
        job_id=job.id,
        status="INTERVIEWING",
        notes="Notes for App B",
    )
    db_session.add(app_obj)
    db_session.commit()
    db_session.refresh(app_obj)
    return app_obj


def test_user_a_can_access_own_application(client: TestClient, headers_a: dict[str, str], app_a: Application):
    """
    1. User A can access their own application.
    """
    response = client.get(f"/applications/{app_a.id}", headers=headers_a)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == app_a.id
    assert data["user_id"] == app_a.user_id
    assert data["status"] == "APPLIED"


def test_user_a_cannot_access_user_b_application(client: TestClient, headers_a: dict[str, str], app_b: Application):
    """
    2. User A cannot access User B's application (returns 404 to prevent resource enumeration).
    """
    response = client.get(f"/applications/{app_b.id}", headers=headers_a)
    assert response.status_code == 404
    assert response.json() == {"detail": "Application not found"}


def test_user_a_cannot_update_user_b_application(
    client: TestClient, headers_a: dict[str, str], app_b: Application, db_session: Session
):
    """
    3. User A cannot update User B's application (returns 404, DB state remains unchanged).
    """
    update_payload = {"status": "REJECTED", "notes": "Unauthorized modification"}
    response = client.patch(f"/applications/{app_b.id}", json=update_payload, headers=headers_a)
    assert response.status_code == 404
    assert response.json() == {"detail": "Application not found"}

    # Verify DB state of app_b was not modified
    db_session.refresh(app_b)
    assert app_b.status == "INTERVIEWING"
    assert app_b.notes == "Notes for App B"


def test_user_a_cannot_delete_user_b_application(
    client: TestClient, headers_a: dict[str, str], app_b: Application, db_session: Session
):
    """
    4. User A cannot delete User B's application (returns 404, record remains in DB).
    """
    response = client.delete(f"/applications/{app_b.id}", headers=headers_a)
    assert response.status_code == 404
    assert response.json() == {"detail": "Application not found"}

    # Verify app_b still exists in DB
    existing_app = db_session.get(Application, app_b.id)
    assert existing_app is not None
    assert existing_app.id == app_b.id


def test_user_b_can_access_own_application(client: TestClient, headers_b: dict[str, str], app_b: Application):
    """
    5. User B can access their own application.
    """
    response = client.get(f"/applications/{app_b.id}", headers=headers_b)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == app_b.id
    assert data["user_id"] == app_b.user_id
    assert data["status"] == "INTERVIEWING"


def test_unauthenticated_requests_rejected(client: TestClient, app_a: Application):
    """
    6. Requests without authentication are rejected (HTTP 401).
    """
    get_res = client.get(f"/applications/{app_a.id}")
    assert get_res.status_code == 401

    patch_res = client.patch(f"/applications/{app_a.id}", json={"status": "OFFERED"})
    assert patch_res.status_code == 401

    delete_res = client.delete(f"/applications/{app_a.id}")
    assert delete_res.status_code == 401

    kanban_res = client.get("/applications/kanban")
    assert kanban_res.status_code == 401

    manual_res = client.post(
        "/applications/manual",
        json={"company_name": "Test Co", "title": "Developer", "status": "APPLIED"},
    )
    assert manual_res.status_code == 401
