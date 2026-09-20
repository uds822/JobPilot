from playwright.sync_api import sync_playwright


def fetch_dynamic_page(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        page = browser.new_page()

        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=30000
        )

        html = page.content()

        browser.close()

        return html