import os
from typing import Generator

# Enforce environment variables for testing BEFORE loading app modules
os.environ["DATABASE_URL"] = "postgresql+psycopg://postgres:Rajan123@localhost:5432/jobtracker_test"
os.environ["SECRET_KEY"] = "test_secret_key_1234567890_testing"
os.environ["ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "60"

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from main import app
from app.database.database import Base, get_db
from app.dependencies import get_current_user
from app.models.users import User
from app.models.companies import Company
from app.models.jobs import Job
from app.models.applications import Application
from app.security.security import hash_password, create_access_token


TEST_DATABASE_URL = os.environ["DATABASE_URL"]

test_engine = create_engine(
    TEST_DATABASE_URL,
    pool_pre_ping=True,
)

TestingSessionLocal = sessionmaker(
    bind=test_engine,
    autocommit=False,
    autoflush=False,
)


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """
    Session-scoped fixture to create all database tables in jobtracker_test at test start.
    """
    tables = set(inspect(test_engine).get_table_names())
    alembic_config = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    alembic_config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    if tables and "alembic_version" not in tables:
        # Older local test databases were created by metadata and have no
        # revision marker. Treat that known schema as the pre-extension head.
        command.stamp(alembic_config, "a1000cw00003")
    command.upgrade(alembic_config, "head")
    Base.metadata.create_all(bind=test_engine)
    yield
    # Optionally drop tables or leave intact for inspection
    # Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """
    Creates a new database session for a test function.
    Wraps session in a transaction and rolls it back after test execution,
    ensuring 100% test isolation and zero leftover data.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(autouse=True)
def mock_redis(monkeypatch):
    """
    Automatically mock Redis rate limiting calls across all tests to prevent
    redis.exceptions.ConnectionError when Redis is not running locally.
    """
    monkeypatch.setattr("app.core.redis.redis_client.eval", lambda *args, **kwargs: 1)
    monkeypatch.setattr("app.middleware.rate_limit.check_rate_limit", lambda *args, **kwargs: None)


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """
    FastAPI TestClient with app.dependency_overrides[get_db] set to yield the test db_session.
    """
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def test_user(db_session: Session) -> User:
    """
    Creates and returns a test user model instance.
    """
    user = User(
        username="testuser_default",
        email="testuser_default@example.com",
        password_hash=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def auth_headers(test_user: User) -> dict[str, str]:
    """
    Generates a valid JWT Authorization header for test_user.
    """
    token = create_access_token({"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def auth_client(client: TestClient, test_user: User) -> TestClient:
    """
    Returns a TestClient instance with get_current_user pre-overridden to test_user.
    """
    app.dependency_overrides[get_current_user] = lambda: test_user
    return client


@pytest.fixture(scope="function")
def test_company(db_session: Session) -> Company:
    """
    Creates and returns a test company model instance.
    """
    company = Company(
        name="Acme Corp Test",
        website="https://acme.example.com",
        industry="Technology",
        location="New York, NY",
        description="A software testing tech company",
    )
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)
    return company


@pytest.fixture(scope="function")
def test_job(db_session: Session, test_company: Company) -> Job:
    """
    Creates and returns a test job model instance linked to test_company.
    """
    job = Job(
        title="Software Test Engineer",
        company_id=test_company.id,
        location="Remote",
        job_url="https://acme.example.com/jobs/123",
        description="Test description for software role",
        employment_type="Full-time",
        status="SAVED",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


@pytest.fixture(scope="function")
def test_application(db_session: Session, test_user: User, test_job: Job) -> Application:
    """
    Creates and returns a test application model instance linked to test_user and test_job.
    """
    application = Application(
        user_id=test_user.id,
        job_id=test_job.id,
        status="APPLIED",
        notes="Applied via website",
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)
    return application
