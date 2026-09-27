import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.users import User
from app.models.companies import Company
from app.models.jobs import Job
from app.models.applications import Application


@pytest.fixture
def seeded_applications(db_session: Session, test_user: User, test_company: Company):
    """
    Seeds 15 applications for test_user:
    - 10 APPLIED
    - 5 INTERVIEWING
    """
    apps = []
    for i in range(15):
        status = "INTERVIEWING" if i < 5 else "APPLIED"
        job = Job(
            title=f"Engineer #{i}",
            company_id=test_company.id,
            job_url=f"https://example.com/job_seed_{i}",
        )
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)

        app_obj = Application(
            user_id=test_user.id,
            job_id=job.id,
            status=status,
            notes=f"Seed note #{i}",
        )
        db_session.add(app_obj)
        apps.append(app_obj)

    db_session.commit()
    return apps


def test_default_pagination_behavior(client: TestClient, auth_headers: dict[str, str], seeded_applications):
    """
    1. Default pagination behavior (limit=20, offset=0).
    """
    response = client.get("/applications", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 20
    assert data["offset"] == 0
    assert data["total"] == 15
    assert len(data["items"]) == 15
    assert data["has_more"] is False


def test_custom_limit(client: TestClient, auth_headers: dict[str, str], seeded_applications):
    """
    2. Custom limit parameter (e.g., limit=5).
    """
    response = client.get("/applications?limit=5", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 5
    assert data["offset"] == 0
    assert data["total"] == 15
    assert len(data["items"]) == 5
    assert data["has_more"] is True


def test_custom_offset(client: TestClient, auth_headers: dict[str, str], seeded_applications):
    """
    3. Custom offset parameter (e.g., offset=5).
    """
    response = client.get("/applications?limit=5&offset=5", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 5
    assert data["offset"] == 5
    assert data["total"] == 15
    assert len(data["items"]) == 5
    assert data["has_more"] is True


def test_maximum_serverside_limit_enforcement(client: TestClient, auth_headers: dict[str, str]):
    """
    4. Maximum server-side limit enforcement (limit > 100 triggers HTTP 422 validation error).
    """
    response = client.get("/applications?limit=150", headers=auth_headers)
    assert response.status_code == 422
    assert "detail" in response.json()


def test_invalid_negative_limit(client: TestClient, auth_headers: dict[str, str]):
    """
    5. Invalid/negative/zero limit parameter returns HTTP 422.
    """
    # Negative limit
    res_neg = client.get("/applications?limit=-5", headers=auth_headers)
    assert res_neg.status_code == 422

    # Zero limit
    res_zero = client.get("/applications?limit=0", headers=auth_headers)
    assert res_zero.status_code == 422


def test_invalid_negative_offset(client: TestClient, auth_headers: dict[str, str]):
    """
    6. Invalid/negative offset parameter returns HTTP 422.
    """
    response = client.get("/applications?offset=-10", headers=auth_headers)
    assert response.status_code == 422


def test_valid_status_filtering(client: TestClient, auth_headers: dict[str, str], seeded_applications):
    """
    7. Valid status filtering (e.g. status=INTERVIEWING vs status=APPLIED).
    """
    response_interviewing = client.get("/applications?status=INTERVIEWING", headers=auth_headers)
    assert response_interviewing.status_code == 200
    data = response_interviewing.json()
    assert data["total"] == 5
    assert len(data["items"]) == 5
    for item in data["items"]:
        assert item["status"] == "INTERVIEWING"

    response_applied = client.get("/applications?status=APPLIED", headers=auth_headers)
    assert response_applied.status_code == 200
    data_applied = response_applied.json()
    assert data_applied["total"] == 10
    assert len(data_applied["items"]) == 10
    for item in data_applied["items"]:
        assert item["status"] == "APPLIED"


def test_invalid_status_filtering(client: TestClient, auth_headers: dict[str, str]):
    """
    8. Invalid status filtering returns HTTP 422 Unprocessable Entity.
    """
    response = client.get("/applications?status=INVALID_STATUS_NAME", headers=auth_headers)
    assert response.status_code == 422


def test_empty_result_set(client: TestClient, auth_headers: dict[str, str]):
    """
    9. Empty result set returns HTTP 200 with total=0, items=[], has_more=False.
    """
    response = client.get("/applications", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []
    assert data["has_more"] is False


def test_response_structure_and_fields(client: TestClient, auth_headers: dict[str, str], test_application: Application):
    """
    10. Response structure and pagination-related fields verification.
    """
    response = client.get("/applications", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    # Top-level pagination keys
    assert "items" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data
    assert "has_more" in data

    # Schema keys of returned items
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["id"] == test_application.id
    assert item["user_id"] == test_application.user_id
    assert item["job_id"] == test_application.job_id
    assert item["status"] == test_application.status
    assert "applied_at" in item
    assert item["notes"] == test_application.notes
