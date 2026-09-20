from app.schemas.user import UserLogin
from app.security.security import verify_password, create_access_token
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.models.users import User
from fastapi.security import OAuth2PasswordRequestForm

from app.exceptions import UnauthorizedError
from app.middleware.rate_limit import check_rate_limit
from fastapi import Request

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login")
def login(
    request:Request,
    form_data: OAuth2PasswordRequestForm = Depends(),db: Session = Depends(get_db)
):  
    client_ip=request.client.host
    check_rate_limit(
        key=f"rate_limit:login:{client_ip}",
        limit=5,
        window_seconds=60,
    )
    
    user = db.query(User).filter(User.username == form_data.username).first()

    if user is None or not verify_password(form_data.password, user.password_hash):
        raise UnauthorizedError("Invalid username or password")

    access_token = create_access_token({"sub": str(user.id)})

    return {"access_token": access_token, "token_type": "bearer"}
