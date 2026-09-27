import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.applications import Application
from app.schemas.application import ApplicationStatus


def manual_application_payload(job_url: str, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "company_name": "Acme Corp Test",
        "title": "Software Test Engineer",
        "location": "Remote",
        "description": "A test application",
        "job_url": job_url,
        "notes": "Initial notes",
        "status": "APPLIED",
    }
    payload.update(overrides)
    return payload


def test_create_application_succeeds_and_persists_database_state(
    auth_client: TestClient,
    db_session: Session,
    test_user,
):
    response = auth_client.post(
        "/applications/manual",
        json=manual_application_payload("https://example.com/business-create"),
    )

    assert response.status_code == 200
    response_data = response.json()
    application = db_session.get(Application, response_data["id"])

    assert application is not None
    assert application.user_id == test_user.id
    assert application.status == "APPLIED"
    assert application.notes == "Initial notes"


def test_duplicate_application_returns_conflict_and_creates_no_second_record(
    auth_client: TestClient,
):
    payload = manual_application_payload("https://example.com/business-duplicate")

    first_response = auth_client.post("/applications/manual", json=payload)
    second_response = auth_client.post("/applications/manual", json=payload)

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    assert second_response.json() == {"detail": "You have already applied to this job."}


def test_application_unique_constraint_rejects_duplicate_user_and_job(
    db_session: Session,
    test_application: Application,
):
    user_id = test_application.user_id
    job_id = test_application.job_id
    application_id = test_application.id
    duplicate = Application(
        user_id=user_id,
        job_id=job_id,
        status="APPLIED",
    )

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(duplicate)
            db_session.flush()

    applications = (
        db_session.query(Application)
        .filter(
            Application.user_id == user_id,
            Application.job_id == job_id,
        )
        .all()
    )
    assert len(applications) == 1
    assert applications[0].id == application_id


@pytest.mark.parametrize(
    "status",
    [
        ApplicationStatus.APPLIED,
        ApplicationStatus.INTERVIEWING,
        ApplicationStatus.OFFERED,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    ],
)
def test_update_application_status_persists_supported_statuses(
    auth_client: TestClient,
    db_session: Session,
    test_application: Application,
    status: ApplicationStatus,
):
    response = auth_client.patch(
        f"/applications/{test_application.id}",
        json={"status": status.value},
    )

    assert response.status_code == 200
    db_session.expire_all()
    updated_application = db_session.get(Application, test_application.id)

    assert updated_application is not None
    assert updated_application.status == status.value


def test_update_application_notes_persists(
    auth_client: TestClient,
    db_session: Session,
    test_application: Application,
):
    response = auth_client.patch(
        f"/applications/{test_application.id}",
        json={"notes": "Updated interview preparation notes"},
    )

    assert response.status_code == 200
    db_session.expire_all()
    updated_application = db_session.get(Application, test_application.id)

    assert updated_application is not None
    assert updated_application.notes == "Updated interview preparation notes"


def test_delete_application_removes_database_record(
    auth_client: TestClient,
    db_session: Session,
    test_application: Application,
):
    response = auth_client.delete(f"/applications/{test_application.id}")

    assert response.status_code == 200
    assert db_session.get(Application, test_application.id) is None
