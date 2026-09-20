from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from app.routers import jobs
from app.routers.companies import router as companies_router
from app.routers.users import router as users_router
from app.routers.auth import router as auth_router
from app.routers.application import router as application_router

from app.exceptions import (
    AppException,
    NotFoundError,
    ConflictError,
    BadRequestError,
    UnauthorizedError,
)
from app.core.logging import setup_logging
from app.middleware.request_logging import RequestLoggingMiddleware
from fastapi.middleware.cors import CORSMiddleware
import logging

app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestLoggingMiddleware)

setup_logging()


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(NotFoundError)
async def not_found_exception_handler(request: Request, exc: NotFoundError):
    return JSONResponse(
        status_code=404,
        content={"detail": str(exc)},
    )


@app.exception_handler(ConflictError)
async def conflict_exception_handler(request: Request, exc: ConflictError):
    return JSONResponse(
        status_code=409,
        content={"detail": str(exc)},
    )


@app.exception_handler(BadRequestError)
async def bad_request_exception_handler(request: Request, exc: BadRequestError):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )


@app.exception_handler(UnauthorizedError)
async def unauthorized_exception_handler(request: Request, exc: UnauthorizedError):
    return JSONResponse(
        status_code=401,
        content={"detail": str(exc)},
    )


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc) or "An internal error occurred."},
    )
    
@app.exception_handler(Exception)
async def unexpected_exception_handler(request: Request, exc: Exception):
    logger = logging.getLogger(__name__)

    logger.exception(
        "Unhandled exception: %s",
        exc,
    )

    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred."},
    )
@app.get("/test-error")
async def test_error():
    raise RuntimeError("SECRET database failure")

app.include_router(jobs.router)
app.include_router(companies_router)
app.include_router(users_router)
app.include_router(auth_router)
app.include_router(application_router)
