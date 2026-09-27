import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.users import User


def test_login_success(client: TestClient, test_user: User):
    """
    1. Successful login with valid credentials
    """
    response = client.post(
        "/auth/login",
        data={"username": "testuser_default", "password": "password123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert isinstance(data["access_token"], str)
    assert len(data["access_token"]) > 0


def test_login_wrong_password(client: TestClient, test_user: User):
    """
    2. Login with wrong password
    """
    response = client.post(
        "/auth/login",
        data={"username": "testuser_default", "password": "wrongpassword!"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid username or password"}


def test_login_nonexistent_user(client: TestClient, db_session: Session):
    """
    3. Login with nonexistent user
    """
    response = client.post(
        "/auth/login",
        data={"username": "nonexistent_user_999", "password": "password123"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid username or password"}


def test_login_missing_required_fields(client: TestClient):
    """
    4. Missing required login fields
    """
    # Missing password
    response_no_pw = client.post(
        "/auth/login",
        data={"username": "testuser_default"},
    )
    assert response_no_pw.status_code == 422

    # Missing username
    response_no_user = client.post(
        "/auth/login",
        data={"password": "password123"},
    )
    assert response_no_user.status_code == 422

    # Missing both fields
    response_empty = client.post(
        "/auth/login",
        data={},
    )
    assert response_empty.status_code == 422


def test_get_me_valid_jwt(client: TestClient, auth_headers: dict[str, str], test_user: User):
    """
    5. Accessing /users/me with a valid JWT
    """
    response = client.get("/users/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_user.id
    assert data["username"] == test_user.username
    assert data["email"] == test_user.email


def test_get_me_missing_jwt(client: TestClient):
    """
    6. Accessing /users/me without a JWT
    """
    response = client.get("/users/me")
    assert response.status_code == 401
    assert "detail" in response.json()


def test_get_me_invalid_jwt(client: TestClient):
    """
    7. Accessing /users/me with an invalid JWT
    """
    invalid_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    response = client.get("/users/me", headers={"Authorization": f"Bearer {invalid_token}"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


def test_get_me_malformed_jwt(client: TestClient):
    """
    8. Accessing /users/me with a malformed JWT
    """
    malformed_headers = {"Authorization": "Bearer not-a-real-token-string"}
    response = client.get("/users/me", headers=malformed_headers)
    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}
