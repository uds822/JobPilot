import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.applications import Application
from app.models.companies import Company
from app.models.jobs import Job
from app.models.users import User
from app.exceptions import ConflictError
from app.services.application import create_application_manual
from app.schemas.application import ApplicationManualCreate


def flush_in_savepoint(db_session: Session, record: object) -> None:
    with db_session.begin_nested():
        db_session.add(record)
        db_session.flush()


def test_duplicate_username_is_rejected_by_postgresql(
    db_session: Session,
    test_user: User,
):
    duplicate = User(
        username=test_user.username,
        email="different-username@example.com",
        password_hash="hashed-password",
    )

    with pytest.raises(IntegrityError):
        flush_in_savepoint(db_session, duplicate)

    assert db_session.query(User).filter(User.username == test_user.username).count() == 1


def test_duplicate_email_is_rejected_by_postgresql(
    db_session: Session,
    test_user: User,
):
    duplicate = User(
        username="different-email-user",
        email=test_user.email,
        password_hash="hashed-password",
    )

    with pytest.raises(IntegrityError):
        flush_in_savepoint(db_session, duplicate)

    assert db_session.query(User).filter(User.email == test_user.email).count() == 1


def test_duplicate_job_url_is_rejected_by_postgresql(
    db_session: Session,
    test_job: Job,
    test_company: Company,
):
    duplicate = Job(
        title="Another job",
        company_id=test_company.id,
        job_url=test_job.job_url,
        status="SAVED",
    )

    with pytest.raises(IntegrityError):
        flush_in_savepoint(db_session, duplicate)

    assert db_session.query(Job).filter(Job.job_url == test_job.job_url).count() == 1


def test_duplicate_application_pair_is_rejected_by_postgresql(
    db_session: Session,
    test_application: Application,
):
    duplicate = Application(
        user_id=test_application.user_id,
        job_id=test_application.job_id,
        status="APPLIED",
    )

    with pytest.raises(IntegrityError):
        flush_in_savepoint(db_session, duplicate)

    assert (
        db_session.query(Application)
        .filter(
            Application.user_id == test_application.user_id,
            Application.job_id == test_application.job_id,
        )
        .count()
        == 1
    )


def test_invalid_application_status_is_rejected_by_postgresql(
    db_session: Session,
    test_user: User,
    test_job: Job,
):
    invalid_application = Application(
        user_id=test_user.id,
        job_id=test_job.id,
        status="INVALID_STATUS",
    )

    with pytest.raises(IntegrityError):
        flush_in_savepoint(db_session, invalid_application)

    assert db_session.query(Application).filter(Application.user_id == test_user.id).count() == 0


def test_invalid_job_status_is_rejected_by_postgresql(
    db_session: Session,
    test_company: Company,
):
    invalid_job = Job(
        title="Invalid status job",
        company_id=test_company.id,
        job_url="https://example.com/invalid-job-status",
        status="INVALID_STATUS",
    )

    with pytest.raises(IntegrityError):
        flush_in_savepoint(db_session, invalid_job)

    assert db_session.query(Job).filter(Job.job_url == invalid_job.job_url).count() == 0


@pytest.mark.parametrize(
    "record_factory",
    [
        lambda user, company, job: User(
            username=None,
            email="null-username@example.com",
            password_hash="hashed-password",
        ),
        lambda user, company, job: User(
            username="null-email-user",
            email=None,
            password_hash="hashed-password",
        ),
        lambda user, company, job: User(
            username="null-password-user",
            email="null-password@example.com",
            password_hash=None,
        ),
        lambda user, company, job: Job(
            title=None,
            company_id=company.id,
            job_url="https://example.com/null-job-title",
        ),
        lambda user, company, job: Job(
            title="Null company job",
            company_id=None,
            job_url="https://example.com/null-company",
        ),
        lambda user, company, job: Application(
            user_id=None,
            job_id=job.id,
            status="APPLIED",
        ),
        lambda user, company, job: Application(
            user_id=user.id,
            job_id=None,
            status="APPLIED",
        ),
    ],
)
def test_required_non_null_fields_reject_null(
    db_session: Session,
    test_user: User,
    test_company: Company,
    test_job: Job,
    record_factory,
):
    invalid_record = record_factory(test_user, test_company, test_job)

    with pytest.raises(IntegrityError):
        flush_in_savepoint(db_session, invalid_record)


def test_failed_application_operation_leaves_no_partial_application_data(
    db_session: Session,
    test_user: User,
    test_application: Application,
):
    job_url = test_application.job.job_url
    duplicate_payload = ApplicationManualCreate(
        company_name="New Partial Company",
        title="Duplicate Application",
        job_url=job_url,
        status="APPLIED",
    )

    with pytest.raises(ConflictError, match="already applied"):
        create_application_manual(duplicate_payload, test_user, db_session)

    assert db_session.query(Company).filter(Company.name == "New Partial Company").count() == 0
    assert db_session.query(Job).filter(Job.job_url == job_url).count() == 0


def test_nested_transaction_handles_duplicate_and_session_remains_usable(
    db_session: Session,
    test_user: User,
    test_application: Application,
):
    duplicate = Application(
        user_id=test_user.id,
        job_id=test_application.job_id,
        status="APPLIED",
    )

    with pytest.raises(IntegrityError):
        flush_in_savepoint(db_session, duplicate)

    follow_up_user = User(
        username="usable-after-failure",
        email="usable-after-failure@example.com",
        password_hash="hashed-password",
    )
    db_session.add(follow_up_user)
    db_session.flush()

    assert db_session.get(User, follow_up_user.id) is not None
