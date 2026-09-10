from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.models.users import User
from app.security.security import hash_password, verify_password

from app.dependencies import get_current_user

router = APIRouter(prefix="/users", tags=["Users"])

@router.post("/register", response_model=UserResponse)
def create_user(user_data: UserCreate, db:Session=Depends(get_db)):

    existing_user=db.query(User).filter((User.username==user_data.username) | (User.email==user_data.email)).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="Username or email already registered")

    hashed_password = hash_password(user_data.password)
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        password_hash=hashed_password
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

#this will ge current user

@router.get("/me",response_model=UserResponse)
def get_me(current_user:User=Depends(get_current_user)):
    return current_user


