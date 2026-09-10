from fastapi import Depends,HTTPException
from sqlalchemy.orm import Session
from app.database.database import get_db
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from app.models.users import User
from app.config import settings

oauth2_scheme=OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token:str=Depends(oauth2_scheme),db:Session=Depends(get_db)):

    credentials_exception=HTTPException(
        status_code=401,
        detail="Could not validate credentials"
    )

    try:
        payload=jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )

        user_id=payload.get("sub")

        if user_id is None:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    user=db.get(User,int(user_id))
    if user is None:
        raise credentials_exception
    return user