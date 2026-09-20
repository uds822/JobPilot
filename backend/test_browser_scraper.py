from app.services.browser_scraper import fetch_dynamic_page

html = fetch_dynamic_page(
    "https://www.amazon.jobs/en/jobs/10525641/sde-1-ftc"
)

print("HTML LENGTH:", len(html))
print(html[:500])