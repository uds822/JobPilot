import pytest
from fastapi.testclient import TestClient
from app.middleware.rate_limit import check_rate_limit


@pytest.fixture(autouse=True)
def setup_fake_redis_boundary(monkeypatch):
    """
    Overrides the autouse mock_redis fixture for rate-limit testing.
    Re-enables the REAL check_rate_limit middleware function, but mocks
    ONLY the external redis_client.eval boundary using an in-memory dictionary.
    """
    counts = {}

    def fake_redis_eval(script, numkeys, key, window_seconds):
        counts[key] = counts.get(key, 0) + 1
        return counts[key]

    # Un-mock check_rate_limit so its actual code executes
    monkeypatch.setattr("app.middleware.rate_limit.check_rate_limit", check_rate_limit)
    monkeypatch.setattr("app.routers.auth.check_rate_limit", check_rate_limit)
    monkeypatch.setattr("app.routers.users.check_rate_limit", check_rate_limit)
    monkeypatch.setattr("app.routers.application.check_rate_limit", check_rate_limit)

    # Mock ONLY the Redis eval call at the external boundary
    monkeypatch.setattr("app.core.redis.redis_client.eval", fake_redis_eval)
    monkeypatch.setattr("app.middleware.rate_limit.redis_client.eval", fake_redis_eval)

    return counts


def test_login_rate_limit_allowed_within_limit(client: TestClient):
    """
    1. Requests within the configured limit (5 for /auth/login) are allowed.
    """
    for i in range(5):
        response = client.post(
            "/auth/login",
            data={"username": "user", "password": "wrongpassword"},
        )
        # Should return 401 Unauthorized (credentials error), NOT 429 Rate Limit
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid username or password"


def test_login_rate_limit_exceeded_returns_429(client: TestClient):
    """
    2. The first request beyond the limit (6th request) returns HTTP 429.
    3. The 429 response contains the expected rate-limit error message.
    """
    # First 5 requests allowed
    for _ in range(5):
        client.post(
            "/auth/login",
            data={"username": "user", "password": "wrongpassword"},
        )

    # 6th request exceeds limit (5)
    response_6th = client.post(
        "/auth/login",
        data={"username": "user", "password": "wrongpassword"},
    )
    assert response_6th.status_code == 429
    assert response_6th.json() == {"detail": "Rate limit exceeded. Try again later."}


def test_register_rate_limit_exceeded_returns_429(client: TestClient):
    """
    Test rate limit on POST /users/register (limit: 5 requests).
    """
    for i in range(5):
        res = client.post(
            "/users/register",
            json={"username": f"reguser_{i}", "email": f"reg_{i}@example.com", "password": "Password123!"},
        )
        assert res.status_code in (200, 409)

    # 6th request exceeds limit
    res_exceeded = client.post(
        "/users/register",
        json={"username": "reguser_over", "email": "reg_over@example.com", "password": "Password123!"},
    )
    assert res_exceeded.status_code == 429
    assert res_exceeded.json() == {"detail": "Rate limit exceeded. Try again later."}


def test_url_preview_rate_limit_exceeded_returns_429(client: TestClient, auth_headers: dict[str, str], monkeypatch):
    """
    Test rate limit on POST /applications/url/preview (limit: 10 requests).
    """
    monkeypatch.setattr(
        "app.routers.application.scrape_job",
        lambda url: {"company": "Co", "title": "Dev", "location": "Remote", "description": "Desc"},
    )

    for i in range(10):
        res = client.post(
            "/applications/url/preview",
            json={"job_url": f"https://example.com/job_{i}"},
            headers=auth_headers,
        )
        assert res.status_code == 200

    # 11th request exceeds limit (10)
    res_11th = client.post(
        "/applications/url/preview",
        json={"job_url": "https://example.com/job_over"},
        headers=auth_headers,
    )
    assert res_11th.status_code == 429
    assert res_11th.json() == {"detail": "Rate limit exceeded. Try again later."}


def test_rate_limits_isolated_by_client_ip_key(client: TestClient):
    """
    4. Rate limits are isolated by the configured key (client IP).
    """
    ip_a_client = TestClient(client.app, client=("10.0.0.1", 50000))
    ip_b_client = TestClient(client.app, client=("10.0.0.2", 50000))

    # Exhaust limit (5) for IP A
    for _ in range(5):
        res = ip_a_client.post("/auth/login", data={"username": "u", "password": "p"})
        assert res.status_code == 401

    # 6th request for IP A is blocked (429)
    res_a_blocked = ip_a_client.post("/auth/login", data={"username": "u", "password": "p"})
    assert res_a_blocked.status_code == 429

    # IP B makes a request - should be allowed (401, not 429)
    res_b_allowed = ip_b_client.post("/auth/login", data={"username": "u", "password": "p"})
    assert res_b_allowed.status_code == 401
