# Company Watch Discovery and Direct Ingestion

## Scope

Google and Amazon direct ingestion, website-to-careers discovery and additional fetching adapters are included. The registry currently contains 204 employers, including 52 newly added Indian product/startup and GCC targets; registration does not mean every employer is fetchable.

Implemented fetching: Greenhouse, Lever, Ashby, Amazon public India search JSON, Google public server-rendered India listings, Workday public CXS boards, Oracle Recruiting Candidate Experience, Eightfold public search, SmartRecruiters public India postings, and Schema.org JobPosting records in HTML or JSON. Unknown HTML/API layouts require a site-specific adapter. No login, CAPTCHA bypass or JavaScript execution is performed.

Detection also recognizes iCIMS, Jobvite and SAP SuccessFactors; these remain `adapter_required` without compatible fetching implementations. Google subsidiary listings are not relabeled as Google jobs.

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
- Fetching: at most 45 HTTP requests, 20 listing pages by default (44 for Eightfold's ten-result pages and six for structured extraction), and a 90-second request-start budget per source. An in-flight request remains subject to the HTTP timeout.
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

## Experience Qualification

An explicit user experience range enables strict recommendation filtering. `Top Matches` and `For You` require a verified total-experience match from a full description and no high-confidence seniority conflict. `Newly Fetched` contains active jobs first seen in the latest completed search, regardless of experience status or score; `All Unapplied` keeps matched, mismatched, and unknown jobs across searches. These views intentionally overlap, while saved and applied state is unchanged. A title such as `Lead` is a seniority signal, not an invented years requirement. Skill-specific years and preferred years do not establish a hard total requirement. A short Adzuna snippet cannot confirm a positive match, even if it mentions matching years.

Adzuna full-description enrichment is separate from the user search. It makes at most 3 requests per job, reads at most 600 KB per response, follows at most 2 redirects, and accepts only a larger structured `JobPosting` description whose title and employer match. It tries no more than 30 jobs concurrently capped at 3, and a failed attempt is retried no sooner than the next day. No generic page scraping or LLM call is used. An unavailable full description remains `unknown`; a later provider snippet cannot replace an enriched full description. Run from `backend`:

```powershell
..\.venv\Scripts\python.exe -m app.ai_job_search.enrichment --limit 20 --concurrency 3
..\.venv\Scripts\python.exe -m app.ai_job_search.enrichment --job-ids 8616 8617 --limit 2
```

To schedule it outside FastAPI, add a third Task Scheduler task alongside discovery and ingestion, with the same `$python`, `$backend`, `$trigger`, and `$settings` variables shown above:

```powershell
$enrichment = New-ScheduledTaskAction -Execute $python -WorkingDirectory $backend -Argument '-m app.ai_job_search.enrichment --limit 20 --concurrency 3'
Register-ScheduledTask -TaskName 'JobAuto Description Enrichment' -Action $enrichment -Trigger $trigger -Settings $settings
```

The experience tests use stored-style snippets and a structured-page fixture; those tests demonstrate filtering and extraction capability, not live Adzuna full-description coverage. Check `description_enrichment_status` and `description_completeness` in the database for actual coverage. A new user search is needed to associate previously unscored canonical jobs with that user's `All Unapplied` view.

## Coverage Evidence

`coverage` reports live database observations, distinct employers, supported/validated sources, complete ingestions, partial observations and active job counts by provider/source. Registration, detection, ownership, feed validation and successful ingestion are separate counts; categories can overlap. It excludes Adzuna and does not claim continuous health from one successful run.

Live pilots on 2026-09-29: Google direct ingestion saved 151 technical India jobs; Amazon saved 733; NVIDIA Eightfold saved 214; PayPal Eightfold saved 7; Qualcomm Eightfold persisted 372 technical observations from a partial inventory; JPMorgan Oracle persisted 83 observations from a partial inventory. Druva, Zenoti, 3M, Airbus, Coca-Cola and NXP Semiconductors were also ingested through Greenhouse/Workday. Qualcomm's endpoint reports 596 India results, above the adapter's 440-result cap, so it is intentionally partial. JPMorgan's India search includes a non-India row, so the adapter preserves valid observations but does not claim a complete refresh. ServiceNow returned HTTP 403 and is reported as failed, not covered.

At the latest live database snapshot, 204 companies were registered; 38 had feed-validated/fetchable sources, 36 were healthy, 34 had ingested, 2 had partial observations, 10 were adapter-required and 47 had discovery failures. There were 111 discovery-pending companies. The live source inventory had 1,795 active direct-source jobs across Greenhouse (220), Workday (353), Google (151), Amazon (733), Eightfold (593), Oracle (83), Lever (33) and Ashby (8). Counts overlap by employer category, exclude Adzuna, and do not mean every registered company is covered.

The focused Company Watch discovery/registry suite passed 71 tests after the Eightfold and registry updates. Fixtures cover Eightfold ISO country codes, explicit India query scope, conflicting-country rejection and partial page-budget behavior, plus website discovery, source ownership, pagination and partial persistence. Passing fixtures are not live company coverage. Use `coverage` for current database totals.

## Focused Company Search

The Company Jobs tab accepts any active registered employer. It scores verified Company Watch inventory when available. If that inventory is empty, it makes a bounded Adzuna company-keyword search (at most three locations and two pages per location), then accepts only postings whose employer name exactly matches the registered name or an alias after removing legal suffixes. A keyword hit alone never establishes employer ownership. Directory postings keep their Adzuna provenance and short descriptions, so experience may remain `unknown` and cannot enter strict Strong Fits on a high score alone.

Directory results are partial third-party coverage, not a complete employer inventory. A successful search returning zero means no matching listings were found in the checked sources, not that the employer has no vacancies. Company Watch discovery/ingestion still needs the external scheduling commands above to expand direct coverage. As of 2026-10-01, 204 employers were registered and 38 had verified fetchable Company Watch sources; all 204 are selectable for the on-demand directory fallback when Adzuna credentials are configured. A live exact-employer Ather Energy query returned one India posting, while direct requests to its official careers site received HTTP 403. Its official careers URL is registered as `https://careers.atherenergy.com/jobs`, but no complete Ather-specific feed adapter has been verified.
