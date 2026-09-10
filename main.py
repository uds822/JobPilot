from fastapi import FastAPI
from app.routers import jobs

from app.routers.companies import router as companies_router
from app.routers.users import router as users_router
from app.routers.auth import router as auth_router
from app.routers.application import router as application_router
app=FastAPI()

@app.get("/")
def root():
    return {"message": "Hello World"}


@app.get("/hello")
def hello():
    return {"message": "Hello, World!"}

app.include_router(jobs.router)
app.include_router(companies_router)
app.include_router(users_router)
app.include_router(auth_router)
app.include_router(application_router)