import logging
import httpx

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# WHY A SHARED CLIENT?
#
# Opening a TCP + SSL connection takes ~200–500ms (handshake, certificates, etc.)
# If we create a new httpx.AsyncClient() for every scrape request, we pay that
# cost every single time.
#
# By sharing ONE client for the app's entire lifetime, we:
#   ✅ Reuse existing TCP connections (connection pooling)
#   ✅ Avoid redundant SSL handshakes
#   ✅ Respect per-host connection limits automatically
#
# This variable starts as None and is created on first use (lazy initialization).
# It is closed gracefully on app shutdown via close_http_client().
# ─────────────────────────────────────────────────────────────────────────────
_http_client: httpx.AsyncClient | None = None


async def _get_http_client() -> httpx.AsyncClient:
    """
    Return the shared async HTTP client, creating it on first call.

    Uses a module-level global so the same client instance is reused across
    all requests — this is what gives us connection pooling.
    """
    global _http_client

    if _http_client is None:
        _http_client = httpx.AsyncClient(
            # ── Timeout breakdown ──────────────────────────────────────────
            # connect: max time to establish the TCP connection
            # read:    max time to wait for the server to send a response
            # write:   max time to send our request body
            # pool:    max time to wait for a free connection from the pool
            timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=2.0),

            # Automatically follow HTTP 301/302 redirects (job sites do this often)
            follow_redirects=True,

            # Mimic a real browser so job sites don't block us with a 403
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/151.0.0.0 Safari/537.36"
                )
            },
        )

    return _http_client


async def close_http_client() -> None:
    """
    Gracefully close the shared HTTP client on app shutdown.

    This releases all open TCP connections back to the OS.
    Called from FastAPI's lifespan shutdown event in main.py.

    Without this, connections may be left open and cause resource warnings.
    """
    global _http_client

    if _http_client is not None:
        await _http_client.aclose()   # aclose() = async version of close()
        _http_client = None
        logger.info("HTTP client closed.")


async def fetch_job_page(url: str) -> str:
    """
    Fetch a job posting page via async HTTP GET.

    ── Why async? ────────────────────────────────────────────────────────────
    httpx.get() (sync) blocks the entire event loop while waiting for the
    server to respond (could be 3–8 seconds for job sites).

    With await client.get() (async), the event loop is FREE to handle other
    incoming requests while we wait for the job site to respond.
    ──────────────────────────────────────────────────────────────────────────

    Raises:
        httpx.HTTPStatusError: If the server returns 4xx or 5xx response.
        httpx.TimeoutException: If the request exceeds our configured timeout.
    """
    client = await _get_http_client()

    logger.debug("Fetching job page: %s", url)
    response = await client.get(url)   # await: event loop is free while waiting

    # Raises httpx.HTTPStatusError for 4xx/5xx — caller handles this
    response.raise_for_status()

    logger.debug("Fetched %s — status %d", url, response.status_code)
    return response.text