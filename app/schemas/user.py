from pydantic import BaseModel, ConfigDict

from datetime import datetime



class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class UserUpdate(BaseModel):
    username: str | None = None
    email: str | None = None
    password: str | None = None
  
class UserLogin(BaseModel):
    username: str
    password: str

