from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import get_db
from app.dependencies import get_current_user
from app.exceptions import ConflictError
from app.middleware.rate_limit import check_rate_limit
from app.models.users import User
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.security.security import hash_password

router = APIRouter(prefix="/users", tags=["Users"])


# ── Scalability: 5k-10k Concurrent Users ─────────────────────────────────────
# Async endpoint prevents server threads from blocking during password hashing and DB writes.
@router.post("/register", response_model=UserResponse)
async def create_user(
    request: Request,
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    client_ip = request.client.host
    check_rate_limit(
        key=f"rate_limit:register:{client_ip}",
        limit=5,
        window_seconds=3600,
    )

    # Async query to check for existing username or email using SQLAlchemy 2.0 select
    stmt = select(User).where(
        or_(User.username == user_data.username, User.email == user_data.email)
    )
    result = await db.execute(stmt)
    existing_user = result.scalars().first()

    if existing_user:
        raise ConflictError("Username or email already registered")

    hashed_password = hash_password(user_data.password)
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        password_hash=hashed_password,
    )

    # In-memory stage (no await needed for db.add)
    db.add(new_user)
    # Network I/O to Postgres — MUST be awaited
    await db.commit()
    await db.refresh(new_user)

    return new_user


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user
