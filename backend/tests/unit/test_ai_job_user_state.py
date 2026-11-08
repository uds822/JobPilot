import asyncio
import hashlib
import selectors
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select

from app.ai_job_search.models import (
    AIJob,
    AIJobMatch,
    SearchRun,
    UserJobState,
    UserResumeProfile,
)
from app.ai_job_search.router import delete_ai_jobs, get_ai_matched_jobs, update_match_action
from app.ai_job_search.schemas import DeleteAIJobsRequest, MatchActionRequest
from app.database.database import AsyncSessionLocal, engine
from app.models.applications import Application
from app.models.companies import Company
from app.models.jobs import Job
from app.models.users import User
from app.services.application import get_kanban_board_data


def _run(coro):
    async def run_and_dispose():
        try:
            return await coro
        finally:
            await engine.dispose()

    with asyncio.Runner(
        loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())
    ) as runner:
        return runner.run(run_and_dispose())


async def _cards(db, user, view):
    return await get_ai_matched_jobs(
        view=view,
        industry=None,
        company_type=None,
        company_name=None,
        min_score=60.0,
        min_salary=None,
        remote_only=False,
        sort_by="relevance",
        offset=0,
        limit=20,
        current_user=user,
        db=db,
    )


def test_durable_save_unsave_expiry_and_confirmed_application():
    async def scenario():
        suffix = uuid4().hex
        user_id = job_id = None
        company_name = f"AI State Co {suffix}"
        try:
            async with AsyncSessionLocal() as db:
                user = User(
                    username=f"ai_state_{suffix}",
                    email=f"ai_state_{suffix}@example.com",
                    password_hash="test-password-hash",
                )
                db.add(user)
                await db.flush()
                user_id = user.id

                profile = UserResumeProfile(
                    user_id=user.id,
                    parsed_profile={"skills": ["Python"]},
                    user_preferences={},
                )
                db.add(profile)
                await db.flush()
                run = SearchRun(
                    user_id=user.id,
                    profile_version_id=profile.id,
                    status="completed",
                )
                db.add(run)
                await db.flush()
                canonical = AIJob(
                    job_hash=hashlib.sha256(suffix.encode()).hexdigest(),
                    source="adzuna",
                    external_id=f"state-{suffix}",
                    title="Backend Engineer",
                    company=company_name,
                    location="Bengaluru",
                    description="Python FastAPI",
                    apply_url=f"https://example.com/jobs/{suffix}",
                    source_url=f"https://example.com/jobs/{suffix}",
                    is_active=True,
                )
                db.add(canonical)
                await db.flush()
                job_id = canonical.id
                match = AIJobMatch(
                    search_run_id=run.id,
                    user_id=user.id,
                    profile_version_id=profile.id,
                    job_id=canonical.id,
                    match_score=91,
                    match_level="Strong match",
                    callback_likelihood="high",
                    strengths=["Python"],
                    gaps=[],
                )
                db.add(match)
                await db.commit()

                await update_match_action(
                    match.id, MatchActionRequest(action="save"), user, db
                )
                state = await db.scalar(
                    select(UserJobState).where(
                        UserJobState.user_id == user.id,
                        UserJobState.job_id == canonical.id,
                    )
                )
                assert state is not None and state.status == "saved"

                await update_match_action(
                    match.id, MatchActionRequest(action="unsave"), user, db
                )
                await db.refresh(state)
                assert state.status == "viewed"
                assert state.saved_at is None

                await update_match_action(
                    match.id, MatchActionRequest(action="save"), user, db
                )
                canonical.is_active = False
                await db.commit()
                saved_cards = await _cards(db, user, "saved")
                assert len(saved_cards) == 1
                assert saved_cards[0].is_expired is True
                assert saved_cards[0].is_saved is True

                # Confirmation must work even if the listing closed after submission.
                response = await update_match_action(
                    match.id, MatchActionRequest(action="apply"), user, db
                )
                assert response["application_id"] is not None
                for view in ("new", "top_matches", "all_unapplied", "saved", "for_you", "all_active"):
                    assert await _cards(db, user, view) == []
                applied_cards = await _cards(db, user, "applied")
                assert len(applied_cards) == 1
                assert applied_cards[0].status == "applied"
                assert applied_cards[0].is_saved is True

                application = await db.get(Application, response["application_id"])
                assert application is not None
                assert application.status == "APPLIED"
                async with AsyncSessionLocal() as board_db:
                    board = await get_kanban_board_data(board_db, user)
                    assert [item.id for item in board["applied"]["items"]] == [application.id]

                await db.refresh(state)
                applied_at = state.applied_at
                repeated = await update_match_action(
                    match.id, MatchActionRequest(action="apply"), user, db
                )
                assert repeated["application_id"] == application.id
                await db.refresh(state)
                assert state.applied_at == applied_at
                for action in ("save", "unsave", "dismiss"):
                    with pytest.raises(HTTPException) as error:
                        await update_match_action(
                            match.id, MatchActionRequest(action=action), user, db
                        )
                    assert error.value.status_code == 409
                    await db.rollback()
                    await db.refresh(user)
                    await db.refresh(match)
                assert len(await _cards(db, user, "applied")) == 1
        finally:
            async with AsyncSessionLocal() as db:
                if user_id is not None:
                    await db.execute(
                        delete(UserJobState).where(UserJobState.user_id == user_id)
                    )
                    await db.execute(
                        delete(AIJobMatch).where(AIJobMatch.user_id == user_id)
                    )
                    await db.execute(
                        delete(SearchRun).where(SearchRun.user_id == user_id)
                    )
                    await db.execute(
                        delete(UserResumeProfile).where(
                            UserResumeProfile.user_id == user_id
                        )
                    )
                    await db.execute(
                        delete(Application).where(Application.user_id == user_id)
                    )
                    await db.execute(delete(User).where(User.id == user_id))
                if job_id is not None:
                    await db.execute(delete(AIJob).where(AIJob.id == job_id))
                tracked_jobs = select(Job.id).join(Company).where(
                    Company.name == company_name
                )
                await db.execute(
                    delete(Job).where(Job.id.in_(tracked_jobs))
                )
                await db.execute(delete(Company).where(Company.name == company_name))
                await db.commit()

    _run(scenario())


def test_strict_experience_filters_recommendations_not_unapplied_inventory():
    async def scenario():
        suffix = uuid4().hex
        user_id = None
        job_ids = []
        try:
            async with AsyncSessionLocal() as db:
                user = User(
                    username=f"ai_experience_{suffix}",
                    email=f"ai_experience_{suffix}@example.com",
                    password_hash="test-password-hash",
                )
                db.add(user)
                await db.flush()
                user_id = user.id
                profile = UserResumeProfile(
                    user_id=user.id,
                    parsed_profile={"skills": ["Python"]},
                    user_preferences={"experience_min_years": 1, "experience_max_years": 2},
                )
                db.add(profile)
                await db.flush()
                run = SearchRun(user_id=user.id, profile_version_id=profile.id, status="completed")
                db.add(run)
                await db.flush()
                postings = (
                    ("Quality Engineer II", "Syndigo", "Syndigo builds software. " * 25, "snippet"),
                    ("Lead Quality Engineer", "Syndigo", "Syndigo builds software. " * 25, "snippet"),
                    ("Generative AI Quality Engineer - Assistant Vice President", "Citi", "Build AI tools. " * 35, "snippet"),
                    ("Python Software Engineer", "Example", "Requires 1-2 years of total experience building Python services.", "full"),
                )
                for index, (title, company, description, completeness) in enumerate(postings):
                    job = AIJob(
                        job_hash=hashlib.sha256(f"{suffix}-{index}".encode()).hexdigest(),
                        source="adzuna",
                        external_id=f"experience-{suffix}-{index}",
                        title=title,
                        company=company,
                        location="Bengaluru",
                        description=description,
                        description_completeness=completeness,
                        apply_url=f"https://example.com/jobs/{suffix}/{index}",
                        is_active=True,
                    )
                    db.add(job)
                    await db.flush()
                    job_ids.append(job.id)
                    db.add(AIJobMatch(
                        search_run_id=run.id,
                        user_id=user.id,
                        profile_version_id=profile.id,
                        job_id=job.id,
                        match_score=42 if index == 0 else 96,
                        match_level="Strong match",
                        callback_likelihood="high",
                    ))
                await db.commit()

                newly_fetched = await _cards(db, user, "new")
                assert len(newly_fetched) == 4
                assert {card.title for card in newly_fetched} == {title for title, *_ in postings}
                assert next(card for card in newly_fetched if card.title == "Quality Engineer II").match_score == 42
                top_cards = await _cards(db, user, "top_matches")
                assert [card.title for card in top_cards] == ["Python Software Engineer"]
                assert top_cards[0].experience_status == "matched"

                cards = await _cards(db, user, "all_unapplied")
                assert len(cards) == 4
                statuses = {card.title: card.experience_status for card in cards}
                assert statuses["Quality Engineer II"] == "unknown"
                assert statuses["Lead Quality Engineer"] == "unknown"
                assert statuses["Generative AI Quality Engineer - Assistant Vice President"] == "unknown"
                assert statuses["Python Software Engineer"] == "matched"
                assert next(card for card in cards if card.title == "Lead Quality Engineer").seniority_conflict

                profile.user_preferences = {"experience_min_years": 3, "experience_max_years": 6}
                await db.commit()
                assert not await _cards(db, user, "top_matches")
                assert len(await _cards(db, user, "new")) == 4
                cards = await _cards(db, user, "all_unapplied")
                assert next(card for card in cards if card.title == "Python Software Engineer").experience_status == "mismatched"
        finally:
            async with AsyncSessionLocal() as db:
                if user_id is not None:
                    await db.execute(delete(AIJobMatch).where(AIJobMatch.user_id == user_id))
                    await db.execute(delete(SearchRun).where(SearchRun.user_id == user_id))
                    await db.execute(delete(UserResumeProfile).where(UserResumeProfile.user_id == user_id))
                    await db.execute(delete(User).where(User.id == user_id))
                if job_ids:
                    await db.execute(delete(AIJob).where(AIJob.id.in_(job_ids)))
                await db.commit()

    _run(scenario())


def test_discovery_views_use_first_search_and_keep_previous_unapplied_jobs():
    async def scenario():
        suffix = uuid4().hex
        user_id = None
        job_ids = []
        try:
            async with AsyncSessionLocal() as db:
                user = User(
                    username=f"ai_views_{suffix}",
                    email=f"ai_views_{suffix}@example.com",
                    password_hash="test-password-hash",
                )
                db.add(user)
                await db.flush()
                user_id = user.id
                now = datetime.utcnow()
                previous_run = SearchRun(user_id=user.id, status="completed", started_at=now - timedelta(days=1))
                latest_run = SearchRun(user_id=user.id, status="completed", started_at=now)
                db.add_all([previous_run, latest_run])
                await db.flush()
                for index, (score, active) in enumerate([(91, True), (42, True), (87, True), (80, False)]):
                    job = AIJob(
                        job_hash=hashlib.sha256(f"{suffix}-{index}".encode()).hexdigest(),
                        source="lever",
                        external_id=f"views-{suffix}-{index}",
                        title=f"Backend Engineer {index}",
                        company=f"Views Co {suffix}",
                        location="Bengaluru",
                        apply_url=f"https://example.com/jobs/{suffix}/{index}",
                        is_active=active,
                    )
                    db.add(job)
                    await db.flush()
                    job_ids.append(job.id)
                    db.add(AIJobMatch(
                        user_id=user.id,
                        job_id=job.id,
                        search_run_id=latest_run.id if index == 2 else previous_run.id,
                        match_score=score,
                        created_at=now if index == 2 else now - timedelta(days=1),
                    ))
                    if index == 0:
                        # A repeat fetch updates the score, but does not make an old job new.
                        db.add(AIJobMatch(
                            user_id=user.id, job_id=job.id, search_run_id=latest_run.id,
                            match_score=95, created_at=now,
                        ))
                    if index == 1:
                        db.add(UserJobState(
                            user_id=user.id, job_id=job.id, status="saved", saved_at=now,
                        ))
                # A newer queued/failed search must not replace the discovery batch.
                db.add_all([
                    SearchRun(user_id=user.id, status="queued", started_at=now + timedelta(seconds=1)),
                    SearchRun(user_id=user.id, status="failed", started_at=now + timedelta(seconds=2)),
                ])
                await db.commit()

                new_cards = await _cards(db, user, "new")
                assert [card.job_id for card in new_cards] == [job_ids[2]]
                assert new_cards[0].show_count == 0  # New does not depend on first-page exposure.
                top_cards = await _cards(db, user, "top_matches")
                assert [(card.job_id, card.match_score) for card in top_cards] == [
                    (job_ids[0], 95), (job_ids[2], 87)
                ]
                assert {card.job_id for card in await _cards(db, user, "all_unapplied")} == set(job_ids)
                saved_cards = await _cards(db, user, "saved")
                assert [card.job_id for card in saved_cards] == [job_ids[1]]
                assert saved_cards[0].is_saved is True

                # Bookmarking works from both new and historical discovery views.
                for card in (new_cards[0], top_cards[0]):
                    await update_match_action(card.id, MatchActionRequest(action="save"), user, db)
                assert {card.job_id for card in await _cards(db, user, "saved")} == set(job_ids[:3])
                await update_match_action(top_cards[0].id, MatchActionRequest(action="unsave"), user, db)
                assert {card.job_id for card in await _cards(db, user, "saved")} == {job_ids[1], job_ids[2]}
                assert (await _cards(db, user, "top_matches"))[0].is_saved is False
                await update_match_action(new_cards[0].id, MatchActionRequest(action="apply"), user, db)
                assert await _cards(db, user, "new") == []
                assert {card.job_id for card in await _cards(db, user, "all_unapplied")} == {job_ids[0], job_ids[1], job_ids[3]}
                assert {card.job_id for card in await _cards(db, user, "saved")} == {job_ids[1]}
        finally:
            async with AsyncSessionLocal() as db:
                if user_id is not None:
                    await db.execute(delete(UserJobState).where(UserJobState.user_id == user_id))
                    await db.execute(delete(AIJobMatch).where(AIJobMatch.user_id == user_id))
                    await db.execute(delete(SearchRun).where(SearchRun.user_id == user_id))
                    await db.execute(delete(Application).where(Application.user_id == user_id))
                    await db.execute(delete(User).where(User.id == user_id))
                if job_ids:
                    await db.execute(delete(AIJob).where(AIJob.id.in_(job_ids)))
                tracked_jobs = select(Job.id).join(Company).where(Company.name == f"Views Co {suffix}")
                await db.execute(delete(Job).where(Job.id.in_(tracked_jobs)))
                await db.execute(delete(Company).where(Company.name == f"Views Co {suffix}"))
                await db.commit()

    _run(scenario())


def test_bulk_delete_is_user_scoped_and_removes_only_unshared_canonical_jobs():
    async def scenario():
        suffix = uuid4().hex
        users = []
        run_ids = []
        job_ids = []
        try:
            async with AsyncSessionLocal() as db:
                first = User(username=f"delete_a_{suffix}", email=f"delete_a_{suffix}@example.com", password_hash="test")
                second = User(username=f"delete_b_{suffix}", email=f"delete_b_{suffix}@example.com", password_hash="test")
                db.add_all([first, second])
                await db.flush()
                users.extend([first, second])
                first_run = SearchRun(user_id=first.id, status="completed")
                second_run = SearchRun(user_id=second.id, status="completed")
                db.add_all([first_run, second_run])
                await db.flush()
                run_ids.extend([first_run.id, second_run.id])
                jobs = [
                    AIJob(job_hash=hashlib.sha256(f"{suffix}-{index}".encode()).hexdigest(), source="test", external_id=f"{suffix}-{index}", title="Engineer", company="Delete Test", apply_url=f"https://example.com/{suffix}/{index}")
                    for index in range(3)
                ]
                db.add_all(jobs)
                await db.flush()
                job_ids.extend(job.id for job in jobs)
                db.add_all([
                    AIJobMatch(user_id=first.id, search_run_id=first_run.id, job_id=jobs[0].id, match_score=80),
                    AIJobMatch(user_id=first.id, search_run_id=first_run.id, job_id=jobs[1].id, match_score=80),
                    AIJobMatch(user_id=second.id, search_run_id=second_run.id, job_id=jobs[1].id, match_score=80),
                    AIJobMatch(user_id=second.id, search_run_id=second_run.id, job_id=jobs[2].id, match_score=80),
                    UserJobState(user_id=first.id, job_id=jobs[0].id, status="saved"),
                    UserJobState(user_id=second.id, job_id=jobs[1].id, status="saved"),
                ])
                await db.commit()

                selected = await delete_ai_jobs(
                    DeleteAIJobsRequest(job_ids=job_ids), first, db
                )
                assert selected == {
                    "deleted_matches": 2,
                    "deleted_states": 1,
                    "deleted_jobs": 1,
                    "retained_shared_jobs": 1,
                }
                assert await db.get(AIJob, job_ids[0]) is None
                assert await db.get(AIJob, job_ids[1]) is not None
                assert await db.get(AIJob, job_ids[2]) is not None
                assert await db.scalar(select(AIJobMatch.id).where(AIJobMatch.user_id == second.id, AIJobMatch.job_id == job_ids[1])) is not None

                all_remaining = await delete_ai_jobs(
                    DeleteAIJobsRequest(delete_all=True), second, db
                )
                assert all_remaining == {
                    "deleted_matches": 2,
                    "deleted_states": 1,
                    "deleted_jobs": 2,
                    "retained_shared_jobs": 0,
                }
                for job_id in job_ids:
                    assert await db.get(AIJob, job_id) is None
        finally:
            async with AsyncSessionLocal() as db:
                if users:
                    user_ids = [user.id for user in users]
                    await db.execute(delete(UserJobState).where(UserJobState.user_id.in_(user_ids)))
                    await db.execute(delete(AIJobMatch).where(AIJobMatch.user_id.in_(user_ids)))
                    await db.execute(delete(SearchRun).where(SearchRun.id.in_(run_ids)))
                    await db.execute(delete(Application).where(Application.user_id.in_(user_ids)))
                    await db.execute(delete(User).where(User.id.in_(user_ids)))
                if job_ids:
                    await db.execute(delete(AIJob).where(AIJob.id.in_(job_ids)))
                await db.commit()

    _run(scenario())
