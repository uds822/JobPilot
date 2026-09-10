from pydantic import BaseModel, ConfigDict


class CompanyCreate(BaseModel):
    name: str
    website: str | None = None
    industry: str | None = None
    location: str | None = None
    description: str | None = None

class CompanyResponse(BaseModel):
    id: int
    name: str | None
    website: str | None
    industry: str | None
    location: str | None
    description: str | None

    model_config = ConfigDict(from_attributes=True) 

class CompanyUpdate(BaseModel):
    name: str | None = None
    website: str | None = None
    industry: str | None = None
    location: str | None = None
    description: str | None = None

