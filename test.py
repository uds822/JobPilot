from app.services.job_parser import parse_job_page


html = """
<html>
<head>
<script type="application/ld+json">
{
    "@type": "JobPosting",
    "title": "Software Engineer",
    "hiringOrganization": {
        "name": "Microsoft"
    },
    "jobLocation": {
        "address": {
            "addressLocality": "Bangalore",
            "addressRegion": "Karnataka",
            "addressCountry": "India"
        }
    },
    "description": "Build backend services using Python and FastAPI."
}
</script>
</head>
</html>
"""


job = parse_job_page(html)

print(job)