# Company Watch Discovery and Direct Ingestion

## Scope

Google direct ingestion, website-to-careers discovery and additional fetching adapters are included. This does not mean all 152 registered employers are fetchable.

Implemented fetching: Greenhouse, Lever, Ashby, Google public server-rendered India listings, Workday public CXS boards, SmartRecruiters public India postings, and Schema.org JobPosting records in HTML or JSON. Unknown HTML/API layouts require a site-specific adapter. No login, CAPTCHA bypass or JavaScript execution is performed.

Detection also recognizes iCIMS, Jobvite, Oracle Recruiting, SAP SuccessFactors and Eightfold. They remain `adapter_required` without a compatible fetching implementation. Google subsidiary listings are not relabeled as Google jobs.

## Architecture

```text
JSON/Python metadata -> existing employer identity + durable discovery state
careers URL, or evidenced careers links from the official website
  -> bounded public-page inspection -> canonical source + ownership evidence
  -> supported adapter feed validation, or adapter_required
  -> independently scheduled ingestion worker
  -> normalization -> technical India eligibility -> existing canonical UPSERT
  -> existing user city filtering, resume scoring and application state
```

Discovery evidence and attempt history are persisted. Canonical identities are global to the source, not company-scoped; conflicts never transfer source ownership. Existing trusted registry sources retain their IDs and activity/polling settings. Source and company claims use expiring five-minute leases with fenced writes and heartbeats. Failed sources do not abort other companies. Broken sources can re-enter discovery; unsupported sites are revisited weekly.

Adzuna remains supplementary and independent from direct company coverage. Adding a careers URL does not establish ownership, feed validation or successful ingestion by itself.

## Inventory Contract

All current adapters target the `india_technical_v1` inventory scope. Google and SmartRecruiters query India explicitly; Workday uses a discovered India country facet where available. A proven complete broader inventory can also establish this scope after the existing eligibility rules are applied. Country evidence never invents a city.

Adapters report normalized observations, raw counts, completeness, scope, pages fetched and partial errors. Unknown layouts, repeated posting identities, inconsistent pagination/counts, page limits and interrupted requests cannot produce a complete inventory. Some Workday tenants omit totals on subsequent pages; completion still requires the first-page total and the observed unique count to agree.

Valid partial observations update canonical postings and `last_observed_at`. They do not update `last_ingested_at`, `last_success_at` or `last_complete_scope`, and cannot increment missing polls. Complete inventories expire missing jobs only within the same source and scope, retaining the existing two-missing-poll rule. Reappearing observations reset missing counts.

Google stores the qualifications exposed on result cards. Workday/SmartRecruiters detail enrichment is bounded to eight postings per fetch; other postings can contain listing metadata without full descriptions. Structured-page extraction is always partial and checks the stated hiring organization. More detailed enrichment and site-specific parsing are future extensions, not implied capabilities.

## Budgets and Security

- Discovery: at most 12 HTTP requests, six pages, two link-following levels, four redirects per request and 90 seconds per company.
- Fetching: at most 45 HTTP requests, 20 listing pages (six for structured extraction), and a 90-second request-start budget per source. An in-flight request remains subject to the HTTP timeout.
- HTTP: 15-second timeout, five-second connection timeout and two concurrent requests per host in each worker. Decoded content is bounded to two megabytes for discovery/new paginated adapters, and 32 megabytes for established complete Greenhouse/Lever/Ashby feeds with descriptions.
- Discovery batches: at most 100 employers and ten concurrent companies; defaults are 20 and four.
- Only public HTTP(S) URLs without credentials and with standard ports are accepted. Private/loopback/link-local addresses and internal hostnames are blocked. Every redirect is checked; the connection uses a validated DNS address while retaining hostname-based TLS verification. Environment proxies are disabled.
- The isolated HTTP transport integration depends on httpx 0.28/httpcore 1.0; regression-test it when upgrading these dependencies.

## Commands

Run from `backend`, using the project virtual environment:

```powershell
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m app.company_watch.cli seed
..\.venv\Scripts\python.exe -m app.company_watch.cli verify --limit 50 --concurrency 10
..\.venv\Scripts\python.exe -m app.company_watch.cli discover --limit 20 --concurrency 4
..\.venv\Scripts\python.exe -m app.company_watch.cli ingest --limit 20 --concurrency 4
..\.venv\Scripts\python.exe -m app.company_watch.cli coverage
..\.venv\Scripts\python.exe -m app.company_watch.cli status --json
```

Use repeatable `--company` arguments for exact registered employer names. `--force` ignores the due time, not ownership, adapter support, activity flags or worker claims:

```powershell
..\.venv\Scripts\python.exe -m app.company_watch.cli discover --company Google --force
..\.venv\Scripts\python.exe -m app.company_watch.cli ingest --company Google --force
```

## External Scheduling

No scheduler runs inside FastAPI. Create separate discovery and ingestion tasks. The following Windows commands are examples to run from the repository root; implementation does not install tasks automatically:

```powershell
$python = (Resolve-Path .\.venv\Scripts\python.exe).Path
$backend = (Resolve-Path .\backend).Path
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 30)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1) -Hidden
$discovery = New-ScheduledTaskAction -Execute $python -WorkingDirectory $backend -Argument '-m app.company_watch.cli discover --limit 20 --concurrency 4'
$ingestion = New-ScheduledTaskAction -Execute $python -WorkingDirectory $backend -Argument '-m app.company_watch.cli ingest --limit 20 --concurrency 4'
Register-ScheduledTask -TaskName 'JobAuto Discovery' -Action $discovery -Trigger $trigger -Settings $settings
Register-ScheduledTask -TaskName 'JobAuto Ingestion' -Action $ingestion -Trigger $trigger -Settings $settings
```

Configure the task's account and logged-out execution policy in Task Scheduler as needed. The working directory is required for local configuration. Database evidence/check history persists even without console output. For Linux, adapt the absolute paths and use separate cron entries:

```cron
*/30 * * * * cd /srv/jobtracker/backend && /srv/jobtracker/.venv/bin/python -m app.company_watch.cli discover --limit 20 --concurrency 4 >> /var/log/jobauto-discovery.log 2>&1
*/30 * * * * cd /srv/jobtracker/backend && /srv/jobtracker/.venv/bin/python -m app.company_watch.cli ingest --limit 20 --concurrency 4 >> /var/log/jobauto-ingestion.log 2>&1
```

## Coverage Evidence

`coverage` reports live database observations, distinct employers, supported/validated sources, complete ingestions, partial observations and active job counts by provider/source. Registration, detection, ownership, feed validation and successful ingestion are separate counts; categories can overlap. It excludes Adzuna and does not claim continuous health from one successful run.

Live pilots on 2026-09-29: Google discovery/validation/ingestion saved 151 technical India jobs; Visa's Workday saved 50; Freshworks' SmartRecruiters saved 16. A subsequent live regression check validated all 26 supported sources (the original 23 plus these three), with no failures. ServiceNow returned HTTP 403 and is reported as failed, not covered. NVIDIA's official page currently links a custom/Eightfold careers experience, so a separately reachable Workday board is not automatically assumed to be its current source. SigTuple remains `needs_careers_url` after bounded website inspection found no evidenced careers page.

The focused suite passed 101 tests after implementation. Fixture tests cover the named platform detectors, website-to-careers-to-supported-source ingestion, unsupported sources and ownership conflicts, safe redirects and DNS pinning, response/request budgets, compressed pages, retries/concurrent/expired claims, Google/Workday/SmartRecruiters parsing and pagination, structured employer validation, partial persistence, scoped expiration, missing URLs and broken-source rediscovery. Passing fixtures are not live company coverage. Website discovery and structured extraction were fixture-validated; the successful live pilots above used registered careers URLs. Use `coverage` for current database totals.
