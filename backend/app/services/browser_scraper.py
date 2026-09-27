from playwright.async_api import async_playwright

# ─────────────────────────────────────────────────────────────────────────────
# WHY ASYNC PLAYWRIGHT?
#
# The old code used sync_playwright which BLOCKS the event loop entirely while:
#   - Launching the Chromium browser process
#   - Loading the web page (could take 5–30 seconds)
#   - Reading the DOM
#
# During those 30 seconds, NO other request could be handled by the server.
#
# async_playwright solves this: each await call yields control back to the
# event loop, so other requests can be served while Playwright is working.
#
# NOTE: Playwright is only used as a fallback when regular HTTP scraping
# fails to find the job title or company (see job_scraper_service.py).
# ─────────────────────────────────────────────────────────────────────────────


async def fetch_dynamic_page(url: str) -> str:
    """
    Launch a headless Chromium browser, load the URL, and return the page HTML.

    Used as a fallback when the regular httpx scraper cannot extract the
    job title or company name (e.g., JavaScript-rendered pages).

    ── Why `async with`? ─────────────────────────────────────────────────────
    async_playwright() is an async context manager — it launches and tears down
    the Playwright engine. The `async with` ensures the engine is always closed
    even if an exception occurs inside, preventing resource leaks.
    ──────────────────────────────────────────────────────────────────────────

    Args:
        url: The job posting URL to visit.

    Returns:
        The full HTML content of the page after JavaScript has rendered.
    """
    async with async_playwright() as p:
        # await: Playwright starts the Chromium process (OS-level, takes ~1–2s)
        browser = await p.chromium.launch(headless=True)

        # await: Creates a new browser tab (in-process, fast)
        page = await browser.new_page()

        # await: Navigates to the URL and waits for the DOM to load
        # wait_until="domcontentloaded" means: wait until the HTML is parsed
        # but DON'T wait for images/fonts/etc. (faster)
        # timeout=30000ms = 30 seconds max (JS-heavy job sites can be slow)
        await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=30000,
        )

        # await: Reads the fully-rendered DOM as an HTML string
        html = await page.content()

        # await: Shuts down the Chromium process cleanly
        await browser.close()

        return html