import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.applications import Application
from app.models.jobs import Job
from app.models.companies import Company
from app.models.users import User


def test_e2e_full_user_and_application_lifecycle(client: TestClient, db_session: Session):
    """
    Complete E2E workflow:
    1. Register a new user.
    2. Login with that user and obtain JWT token.
    3. Verify /users/me endpoint.
    4. Create a company/job/application manually via POST /applications/manual.
    5. Update application status and notes via PATCH /applications/{id}.
    6. Fetch single application and Kanban board data.
    7. Verify final persisted state directly in the PostgreSQL database.
    """
    # -----------------------------------------------------------------------
    # Step 1: Register a new user
    # -----------------------------------------------------------------------
    reg_payload = {
        "username": "e2e_candidate",
        "email": "candidate_e2e@example.com",
        "password": "SecurePassword123!",
    }
    reg_res = client.post("/users/register", json=reg_payload)
    assert reg_res.status_code == 200
    reg_data = reg_res.json()
    assert reg_data["username"] == "e2e_candidate"
    assert reg_data["email"] == "candidate_e2e@example.com"
    user_id = reg_data["id"]

    # -----------------------------------------------------------------------
    # Step 2: Login with credentials to obtain JWT
    # -----------------------------------------------------------------------
    login_res = client.post(
        "/auth/login",
        data={"username": "e2e_candidate", "password": "SecurePassword123!"},
    )
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert "access_token" in login_data
    assert login_data["token_type"] == "bearer"
    access_token = login_data["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # -----------------------------------------------------------------------
    # Step 3: Access /users/me with JWT
    # -----------------------------------------------------------------------
    me_res = client.get("/users/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["id"] == user_id

    # -----------------------------------------------------------------------
    # Step 4 & 5: Create job, company, and application
    # -----------------------------------------------------------------------
    manual_app_payload = {
        "company_name": "Acme Enterprise Systems",
        "title": "Principal Staff Engineer",
        "location": "San Francisco, CA",
        "description": "Lead architecture of real-time streaming engines.",
        "job_url": "https://acme.example.com/jobs/staff-eng",
        "status": "APPLIED",
        "notes": "Submitted application via internal referral.",
    }
    create_res = client.post("/applications/manual", json=manual_app_payload, headers=headers)
    assert create_res.status_code == 200
    app_data = create_res.json()
    app_id = app_data["id"]
    assert app_data["user_id"] == user_id
    assert app_data["status"] == "APPLIED"

    # -----------------------------------------------------------------------
    # Step 6: Update application status and notes
    # -----------------------------------------------------------------------
    update_payload = {
        "status": "INTERVIEWING",
        "notes": "Passed initial screening. Technical interview scheduled.",
    }
    patch_res = client.patch(f"/applications/{app_id}", json=update_payload, headers=headers)
    assert patch_res.status_code == 200
    patched_data = patch_res.json()
    assert patched_data["status"] == "INTERVIEWING"
    assert patched_data["notes"] == "Passed initial screening. Technical interview scheduled."

    # -----------------------------------------------------------------------
    # Step 7: Fetch application details & Kanban board
    # -----------------------------------------------------------------------
    get_res = client.get(f"/applications/{app_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["status"] == "INTERVIEWING"

    kanban_res = client.get("/applications/kanban", headers=headers)
    assert kanban_res.status_code == 200
    kanban_data = kanban_res.json()
    assert kanban_data["interviewing"]["total"] == 1
    assert kanban_data["applied"]["total"] == 0
    assert kanban_data["interviewing"]["items"][0]["id"] == app_id

    # -----------------------------------------------------------------------
    # Step 8: Verify final response & DB persisted state
    # -----------------------------------------------------------------------
    db_app = db_session.get(Application, app_id)
    assert db_app is not None
    assert db_app.id == app_id
    assert db_app.user_id == user_id
    assert db_app.status == "INTERVIEWING"
    assert db_app.notes == "Passed initial screening. Technical interview scheduled."
    assert db_app.job.title == "Principal Staff Engineer"
    assert db_app.job.company.name == "Acme Enterprise Systems"


def test_e2e_url_confirm_and_deletion_lifecycle(client: TestClient, db_session: Session):
    """
    E2E URL Confirm & Deletion Lifecycle:
    1. Register User 2 & Login.
    2. Confirm application from URL preview confirmation endpoint.
    3. Delete application.
    4. Verify deletion in database.
    """
    # 1. Register & Login
    client.post(
        "/users/register",
        json={"username": "e2e_user2", "email": "e2e_user2@example.com", "password": "Password123!"},
    )
    login_res = client.post("/auth/login", data={"username": "e2e_user2", "password": "Password123!"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Confirm application from URL
    confirm_payload = {
        "job_url": "https://careers.google.com/jobs/1001",
        "company_name": "Google",
        "title": "Senior Cloud Developer",
        "location": "Mountain View, CA",
        "description": "Cloud platform services.",
        "status": "OFFERED",
        "notes": "Offer letter received!",
    }
    confirm_res = client.post("/applications/url/confirm", json=confirm_payload, headers=headers)
    assert confirm_res.status_code == 200
    app_id = confirm_res.json()["id"]

    # 3. Delete application
    del_res = client.delete(f"/applications/{app_id}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json() == {"message": "Application deleted successfully"}

    # 4. Verify record removed from DB
    deleted_app = db_session.get(Application, app_id)
    assert deleted_app is None
