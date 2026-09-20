from fastapi import APIRouter, Depends,Request
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.models.users import User
from app.security.security import hash_password
from app.dependencies import get_current_user
from app.exceptions import ConflictError
from app.middleware.rate_limit import check_rate_limit

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/register", response_model=UserResponse)
def create_user(request:Request,user_data: UserCreate, db: Session = Depends(get_db)):
    client_ip = request.client.host
    check_rate_limit(
        key=f"rate_limit:register:{client_ip}",
        limit=5,
        window_seconds=3600,
    )
    existing_user = (
        db.query(User)
        .filter((User.username == user_data.username) | (User.email == user_data.email))
        .first()
    )
    if existing_user:
        raise ConflictError("Username or email already registered")

    hashed_password = hash_password(user_data.password)
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        password_hash=hashed_password,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
