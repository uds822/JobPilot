from pydantic import BaseModel, ConfigDict, Field


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    website: str | None = Field(default=None, min_length=1)
    industry: str | None = Field(default=None, min_length=1, max_length=100)
    location: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=10000)


class CompanyResponse(BaseModel):
    id: int
    name: str | None
    website: str | None
    industry: str | None
    location: str | None
    description: str | None

    model_config = ConfigDict(from_attributes=True)


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    website: str | None = Field(default=None, min_length=1)
    industry: str | None = Field(default=None, min_length=1, max_length=100)
    location: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=10000)
