import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from app.core.request_context import request_id_context
from fastapi import Request

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request, call_next):
        request_id = str(uuid.uuid4())

        request.state.request_id = request_id
        request_id_context.set(request_id)

        start_time = time.perf_counter()

        response = await call_next(request)

        duration = time.perf_counter() - start_time
        duration_ms = duration * 1000

        logger.info(
            "%s %s | status=%s | duration=%.2fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )

        response.headers["X-Request-ID"] = request_id

        return response
