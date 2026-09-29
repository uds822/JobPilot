"""Verified ATS sources and company discovery targets for India job search.

IMPORTANT:
- GREENHOUSE_BOARDS and LEVER_SITES are existing verified sources.
- ASHBY_BOARDS contains only boards we have positively identified.
- DIRECT / DISCOVERY lists are companies we want Company Watch to investigate.
  They must NOT be treated as Greenhouse/Lever/Ashby until their source is verified.
"""


# ============================================================
# GREENHOUSE — VERIFIED
# ============================================================

GREENHOUSE_BOARDS = (
    {"company": "GitLab", "board": "gitlab"},
    {"company": "Figma", "board": "figma"},
    {"company": "Coinbase", "board": "coinbase"},
    {"company": "Datadog", "board": "datadog"},
    {"company": "MongoDB", "board": "mongodb"},
    {"company": "Cloudflare", "board": "cloudflare"},
    {"company": "Elastic", "board": "elastic"},
    {"company": "Twilio", "board": "twilio"},
    {"company": "Okta", "board": "okta"},
    {"company": "Rubrik", "board": "rubrik"},
    {"company": "Samsara", "board": "samsara"},
    {"company": "Stripe", "board": "stripe"},
    {"company": "Airbnb", "board": "airbnb"},
    {"company": "Cockroach Labs", "board": "cockroachlabs"},
    {"company": "Grafana Labs", "board": "grafanalabs"},
    {"company": "Groww", "board": "groww"},
)


# ============================================================
# LEVER — VERIFIED
# ============================================================

LEVER_SITES = (
    {"company": "Zeta", "site": "zeta"},
    {"company": "Meesho", "site": "meesho"},
    {"company": "CRED", "site": "cred"},
    {"company": "FamPay", "site": "fampay"},
    {"company": "Mindtickle", "site": "mindtickle"},
)


# ============================================================
# ASHBY — VERIFIED / GOOD TEST BOARDS
# ============================================================

# Altimate currently exposes India/Bengaluru engineering roles on Ashby.
# Harvey also has a public Ashby board.
# Add more only after the board identifier has been verified.

ASHBY_BOARDS = (
    {"company": "Altimate AI", "board": "altimate"},
    {"company": "Harvey", "board": "harvey"},
)


# ============================================================
# BIG TECH / FAANG / MAANG
# Source must be discovered/verified independently.
# DO NOT assume Greenhouse/Lever/Ashby.
# ============================================================

BIG_TECH_COMPANIES = (
    {"company": "Google", "category": "big_tech"},
    {"company": "Amazon", "category": "big_tech"},
    {"company": "Microsoft", "category": "big_tech"},
    {"company": "Apple", "category": "big_tech"},
    {"company": "Meta", "category": "big_tech"},
    {"company": "Netflix", "category": "big_tech"},

    {"company": "NVIDIA", "category": "big_tech"},
    {"company": "Adobe", "category": "big_tech"},
    {"company": "Salesforce", "category": "big_tech"},
    {"company": "ServiceNow", "category": "big_tech"},
    {"company": "Oracle", "category": "big_tech"},
    {"company": "Cisco", "category": "big_tech"},
    {"company": "Atlassian", "category": "big_tech"},
    {"company": "Uber", "category": "big_tech"},
    {"company": "LinkedIn", "category": "big_tech"},
    {"company": "PayPal", "category": "big_tech"},
    {"company": "Intuit", "category": "big_tech"},
    {"company": "VMware", "category": "big_tech"},
    {"company": "SAP", "category": "big_tech"},
)


# ============================================================
# INDIAN PRODUCT / INTERNET COMPANIES
# ============================================================

INDIAN_PRODUCT_COMPANIES = (
    {"company": "Flipkart", "category": "product"},
    {"company": "PhonePe", "category": "fintech"},
    {"company": "Razorpay", "category": "fintech"},
    {"company": "Swiggy", "category": "consumer_internet"},
    {"company": "Zomato", "category": "consumer_internet"},
    {"company": "Dream11", "category": "consumer_internet"},
    {"company": "BrowserStack", "category": "saas"},
    {"company": "Freshworks", "category": "saas"},
    {"company": "Zoho", "category": "saas"},
    {"company": "Paytm", "category": "fintech"},
    {"company": "Groww", "category": "fintech"},
    {"company": "CRED", "category": "fintech"},
    {"company": "Meesho", "category": "ecommerce"},
    {"company": "Zeta", "category": "fintech"},
    {"company": "Mindtickle", "category": "saas"},
    {"company": "Postman", "category": "developer_tools"},
    {"company": "InMobi", "category": "adtech"},
    {"company": "Ola", "category": "mobility"},
    {"company": "OYO", "category": "travel"},
    {"company": "Juspay", "category": "fintech"},
    {"company": "Chargebee", "category": "saas"},
    {"company": "Whatfix", "category": "saas"},
    {"company": "Darwinbox", "category": "saas"},
    {"company": "HighRadius", "category": "saas"},
    {"company": "Hasura", "category": "developer_tools"},
    {"company": "Innovaccer", "category": "healthtech"},
    {"company": "OfBusiness", "category": "b2b"},
    {"company": "Pine Labs", "category": "fintech"},
    {"company": "Policybazaar", "category": "fintech"},
    {"company": "MakeMyTrip", "category": "travel"},
    {"company": "Cleartrip", "category": "travel"},
    {"company": "Myntra", "category": "ecommerce"},
    {"company": "Nykaa", "category": "ecommerce"},
    {"company": "Zepto", "category": "consumer_internet"},
    {"company": "Urban Company", "category": "consumer_internet"},
    {"company": "Practo", "category": "healthtech"},
)


# ============================================================
# AI / ML / GENAI COMPANIES
# ============================================================

AI_ML_COMPANIES = (
    {"company": "Sarvam AI", "category": "ai_ml"},
    {"company": "Krutrim", "category": "ai_ml"},
    {"company": "Yellow.ai", "category": "ai_ml"},
    {"company": "Observe.AI", "category": "ai_ml"},
    {"company": "Haptik", "category": "ai_ml"},
    {"company": "SigTuple", "category": "ai_ml"},
    {"company": "Qure.ai", "category": "ai_ml"},
    {"company": "Mad Street Den", "category": "ai_ml"},
    {"company": "Uniphore", "category": "ai_ml"},
    {"company": "Fractal Analytics", "category": "ai_ml"},
    {"company": "Tredence", "category": "ai_ml"},
    {"company": "Altimate AI", "category": "ai_ml"},
    {"company": "Harvey", "category": "ai_ml"},
)


# ============================================================
# GLOBAL SaaS / PRODUCT / DEVELOPER TOOLS
# ============================================================

GLOBAL_PRODUCT_COMPANIES = (
    {"company": "Snowflake", "category": "data_cloud"},
    {"company": "Databricks", "category": "data_ai"},
    {"company": "Confluent", "category": "data_infrastructure"},
    {"company": "HashiCorp", "category": "cloud_infra"},
    {"company": "MongoDB", "category": "database"},
    {"company": "Elastic", "category": "search"},
    {"company": "Datadog", "category": "observability"},
    {"company": "Cloudflare", "category": "cloud_infra"},
    {"company": "Twilio", "category": "cloud_communications"},
    {"company": "Okta", "category": "cybersecurity"},
    {"company": "CrowdStrike", "category": "cybersecurity"},
    {"company": "Palo Alto Networks", "category": "cybersecurity"},
    {"company": "Zscaler", "category": "cybersecurity"},
    {"company": "Rubrik", "category": "cloud_security"},
    {"company": "Samsara", "category": "iot"},
    {"company": "Stripe", "category": "fintech"},
    {"company": "Airbnb", "category": "consumer_internet"},
    {"company": "Figma", "category": "saas"},
    {"company": "GitHub", "category": "developer_tools"},
    {"company": "GitLab", "category": "developer_tools"},
    {"company": "Docker", "category": "developer_tools"},
    {"company": "Grafana Labs", "category": "observability"},
    {"company": "Cockroach Labs", "category": "database"},
    {"company": "Canonical", "category": "cloud_linux"},
    {"company": "Red Hat", "category": "enterprise_software"},
    {"company": "JetBrains", "category": "developer_tools"},
    {"company": "CloudBees", "category": "devops"},
)


# ============================================================
# GCC / BANKING / FINANCIAL / ENTERPRISE TECH
# ============================================================

GCC_ENTERPRISE_COMPANIES = (
    {"company": "Walmart Global Tech", "category": "gcc"},
    {"company": "JPMorgan Chase", "category": "banking"},
    {"company": "Goldman Sachs", "category": "banking"},
    {"company": "Morgan Stanley", "category": "banking"},
    {"company": "American Express", "category": "fintech"},
    {"company": "Visa", "category": "payments"},
    {"company": "Mastercard", "category": "payments"},
    {"company": "Wells Fargo", "category": "banking"},
    {"company": "Bank of America", "category": "banking"},
    {"company": "Barclays", "category": "banking"},
    {"company": "Deutsche Bank", "category": "banking"},
    {"company": "UBS", "category": "banking"},
    {"company": "HSBC", "category": "banking"},
    {"company": "Standard Chartered", "category": "banking"},
    {"company": "BNY", "category": "banking"},
    {"company": "Fidelity Investments", "category": "fintech"},
    {"company": "BlackRock", "category": "fintech"},
    {"company": "Capital One", "category": "fintech"},

    {"company": "Target", "category": "gcc"},
    {"company": "Lowe's", "category": "gcc"},
    {"company": "Tesco", "category": "gcc"},
    {"company": "IKEA", "category": "gcc"},
    {"company": "Wayfair", "category": "ecommerce"},
)


# ============================================================
# SEMICONDUCTOR / HARDWARE / TELECOM
# ============================================================

SEMICONDUCTOR_HARDWARE_COMPANIES = (
    {"company": "NVIDIA", "category": "semiconductor"},
    {"company": "AMD", "category": "semiconductor"},
    {"company": "Intel", "category": "semiconductor"},
    {"company": "Qualcomm", "category": "semiconductor"},
    {"company": "Broadcom", "category": "semiconductor"},
    {"company": "Texas Instruments", "category": "semiconductor"},
    {"company": "Micron", "category": "semiconductor"},
    {"company": "Applied Materials", "category": "semiconductor"},
    {"company": "Synopsys", "category": "semiconductor"},
    {"company": "Cadence", "category": "semiconductor"},
    {"company": "Arm", "category": "semiconductor"},
    {"company": "Samsung", "category": "hardware"},
    {"company": "Dell Technologies", "category": "hardware"},
    {"company": "HP", "category": "hardware"},
    {"company": "Cisco", "category": "networking"},
    {"company": "Ericsson", "category": "telecom"},
    {"company": "Nokia", "category": "telecom"},
)


# ============================================================
# SERVICES / CONSULTING
# ============================================================

SERVICE_CONSULTING_COMPANIES = (
    {"company": "Accenture", "category": "consulting"},
    {"company": "Deloitte", "category": "consulting"},
    {"company": "PwC", "category": "consulting"},
    {"company": "EY", "category": "consulting"},
    {"company": "KPMG", "category": "consulting"},
    {"company": "McKinsey & Company", "category": "consulting"},
    {"company": "BCG", "category": "consulting"},
    {"company": "Bain & Company", "category": "consulting"},

    {"company": "TCS", "category": "it_services"},
    {"company": "Infosys", "category": "it_services"},
    {"company": "Wipro", "category": "it_services"},
    {"company": "HCLTech", "category": "it_services"},
    {"company": "Tech Mahindra", "category": "it_services"},
    {"company": "Cognizant", "category": "it_services"},
    {"company": "Capgemini", "category": "it_services"},
    {"company": "LTIMindtree", "category": "it_services"},
    {"company": "Persistent Systems", "category": "it_services"},
)


# ============================================================
# SOURCE-DISCOVERY TARGETS
#
# Company Watch should detect/verify the career source for these.
# Do NOT assume an ATS from the company name.
# ============================================================

SOURCE_DISCOVERY_COMPANIES = (
    *BIG_TECH_COMPANIES,
    *INDIAN_PRODUCT_COMPANIES,
    *AI_ML_COMPANIES,
    *GLOBAL_PRODUCT_COMPANIES,
    *GCC_ENTERPRISE_COMPANIES,
    *SEMICONDUCTOR_HARDWARE_COMPANIES,
    *SERVICE_CONSULTING_COMPANIES,
)


# ============================================================
# OPTIONAL: ALL KNOWN FETCHABLE ATS SOURCES
# ============================================================

VERIFIED_ATS_SOURCES = {
    "greenhouse": GREENHOUSE_BOARDS,
    "lever": LEVER_SITES,
    "ashby": ASHBY_BOARDS,
}