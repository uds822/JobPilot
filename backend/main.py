from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
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
from app.services.job_scraper import close_http_client
from app.database.database import engine
from fastapi.middleware.cors import CORSMiddleware
import logging

logger = logging.getLogger(__name__)

setup_logging()


# ─────────────────────────────────────────────────────────────────────────────
# LIFESPAN — App Startup & Shutdown
#
# `lifespan` is a FastAPI concept for managing resources that live for the
# entire duration of the app (not per-request).
#
# Structure:
#   Everything BEFORE yield  → runs once at startup
#   yield                    → the app is alive and serving requests here
#   Everything AFTER yield   → runs once at shutdown (even if an error occurs)
#
# Why not @app.on_event("startup")?
#   That older pattern is deprecated. Lifespan is the modern replacement.
#   It also guarantees shutdown code runs even if startup partially fails.
# ─────────────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── STARTUP ──────────────────────────────────────────────────────────
    # Nothing to pre-warm right now.
    # The httpx AsyncClient is created lazily on first request (_get_http_client).
    # The database engine is also created at module import time.
    logger.info("JobTracker API starting up...")

    yield   # ← App is live. All requests are handled here.

    # ── SHUTDOWN ─────────────────────────────────────────────────────────
    # These run when the server receives a stop signal (Ctrl+C, SIGTERM, etc.)

    # 1. Close the shared httpx AsyncClient
    #    Releases all open TCP connections back to the OS immediately.
    #    Without this: connections leak and you get ResourceWarning in logs.
    logger.info("Closing HTTP client...")
    await close_http_client()

    # 2. Dispose the async SQLAlchemy engine
    #    Closes all pooled database connections gracefully.
    #    Without this: PostgreSQL may log "unexpected EOF on client connection".
    logger.info("Disposing database engine...")
    await engine.dispose()

    logger.info("JobTracker API shut down cleanly.")

app = FastAPI(
    # Wire the lifespan context manager so FastAPI calls startup/shutdown
    # automatically when the server starts and stops.
    lifespan=lifespan,
)


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



@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        loc = err.get("loc", [])
        field = loc[-1] if loc else "field"
        field_name = str(field).capitalize()
        err_type = err.get("type", "")
        ctx = err.get("ctx", {})

        if err_type == "string_too_short" and "min_length" in ctx:
            errors.append(f"{field_name} must be at least {ctx['min_length']} characters long.")
        elif err_type == "string_too_long" and "max_length" in ctx:
            errors.append(f"{field_name} cannot exceed {ctx['max_length']} characters.")
        elif "email" in err_type or str(field).lower() == "email":
            errors.append("Please enter a valid email address.")
        else:
            msg = err.get("msg", "Invalid value")
            errors.append(f"{field_name}: {msg}")

    message = "; ".join(errors) if errors else "Validation failed."
    return JSONResponse(
        status_code=422,
        content={"detail": message},
    )


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
