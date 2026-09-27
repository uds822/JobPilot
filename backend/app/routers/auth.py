from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import get_db
from app.exceptions import UnauthorizedError
from app.middleware.rate_limit import check_rate_limit
from app.models.users import User
from app.schemas.user import UserLogin
from app.security.security import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ── Scalability: 5k-10k Concurrent Users ─────────────────────────────────────
# Converting /login to async def allows thousands of concurrent login requests
# to execute DB lookups non-blockingly on the event loop.
@router.post("/login")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    client_ip = request.client.host
    # In-memory rate limiting for now — easily swapped to Redis key-value store later
    check_rate_limit(
        key=f"rate_limit:login:{client_ip}",
        limit=5,
        window_seconds=60,
    )

    # Async query execution using SQLAlchemy 2.0 select syntax
    result = await db.execute(
        select(User).where(User.username == form_data.username)
    )
    user = result.scalars().first()

    # Password verification using CPU-bound Argon2 / bcrypt hash checking
    if user is None or not verify_password(form_data.password, user.password_hash):
        raise UnauthorizedError("Invalid username or password")

    access_token = create_access_token({"sub": str(user.id)})

    return {"access_token": access_token, "token_type": "bearer"}
