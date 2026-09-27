from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.database import get_db
from app.exceptions import UnauthorizedError
from app.models.users import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ── Scalability: 5k-10k Concurrent Users ─────────────────────────
# Converting authentication dependency to async ensures that DB user queries
# yield control to the asyncio event loop while waiting for Postgres response.
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = UnauthorizedError("Could not validate credentials")

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        user_id_raw = payload.get("sub")

        if user_id_raw is None:
            raise credentials_exception

        user_id = int(user_id_raw)
    except (JWTError, TypeError, ValueError):
        raise credentials_exception

    # await db.get avoids blocking threads during JWT session validation
    user = await db.get(User, user_id)
    if user is None:
        raise credentials_exception

    return user

