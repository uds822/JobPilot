# JobPilot — AWS Production Deployment Guide
> **Approach:** I will teach you each concept before you execute each step.
> You complete one step fully → confirm it works → then we move to the next.
> If something breaks, we debug together before moving forward. No skipping.

**AWS Credits:** $136.65 (expires Oct 30, 2026)
**Billing Alert:** Set $50 alert before touching anything else.
**Target:** Real production deployment with load test metrics for resume.

---

## How This Guide Works

Each step follows this pattern:
1. **I explain the concept** — what it is, why it exists, how it fits your app
2. **You execute** — follow the steps
3. **You verify** — confirm it works using the verification checklist
4. **We move on** — only after the step is confirmed working

If anything breaks, paste the error. We debug before proceeding.

---

## Overview — What We Are Building

```
Internet
    │
    ▼
CloudFront (CDN) ──── S3 (React frontend)
    │
    ▼
Route 53 (DNS) ─── custom domain (optional)
    │
    ▼
ALB (Application Load Balancer)
    │             │
    ▼             ▼
EC2 #1        EC2 #2          ← Gunicorn + Uvicorn workers (FastAPI)
    │             │
    └──────┬───────┘
           │
     PgBouncer (connection pooler)
           │
           ▼
    RDS PostgreSQL (private subnet)

    EC2 Worker ─── ElastiCache Redis ─── Background Job Queue (ARQ)
         │
         ▼
    Playwright Scraper (runs off request thread)

    CloudWatch ─── Logs, Metrics, Alarms
```

---

## Phase 0 — Prerequisites (Before Touching AWS)

> These must be done on your local machine before anything is deployed.

### Step 0.1 — Install AWS CLI
- [ ] Install AWS CLI v2 on Windows
- [ ] **Verify:** `aws --version` returns a version number

### Step 0.2 — Configure AWS CLI with your credentials
- [ ] Run `aws configure` with your access key, secret key, region
- [ ] **Verify:** `aws sts get-caller-identity` returns your account info

### Step 0.3 — Set billing alert
- [ ] Go to AWS Budgets → create a $50 cost alert with email notification
- [ ] **Verify:** Alert shows in Budgets dashboard

### Step 0.4 — Generate an SSH key pair
- [ ] Create an EC2 Key Pair in AWS Console (download the .pem file)
- [ ] Store it safely — you cannot download it again
- [ ] **Verify:** `.pem` file is on your machine

### Step 0.5 — Prepare your app for production
- [ ] Confirm `.env` file is in `.gitignore` (never commit secrets)
- [ ] Confirm `requirements.txt` is up to date: `pip freeze > requirements.txt`
- [ ] Confirm your app runs cleanly with `uvicorn main:app --port 8000`
- [ ] Push latest code to GitHub

### ✅ Phase 0 Checkpoint
- [ ] AWS CLI installed and configured
- [ ] Billing alert active
- [ ] SSH key pair downloaded and stored safely
- [ ] Latest code pushed to GitHub

---

## Phase 1 — Core Deployment: EC2 + RDS + App Live

> **Goal:** Something real is running on AWS. Ugly is fine. Working is required.

### Step 1.1 — Launch Your First EC2 Instance
- [ ] Launch `t3.small` EC2 with Amazon Linux 2023 AMI
- [ ] Attach the key pair from Step 0.4
- [ ] Configure Security Group:
  - SSH (port 22) → Your IP only
  - HTTP (port 80) → Anywhere
  - Custom TCP (port 8000) → Anywhere (temporary, for testing)
- [ ] **Verify:** Instance shows "Running" in EC2 console

### Step 1.2 — SSH Into EC2 and Set Up the Environment
- [ ] SSH into the instance: `ssh -i your-key.pem ec2-user@<public-ip>`
- [ ] Install Python 3.11, pip, git on the instance
- [ ] Clone your GitHub repo
- [ ] Create a `.env` file on the server (manually — never commit it)
- [ ] Install requirements: `pip install -r requirements.txt`
- [ ] Run the app manually: `uvicorn main:app --host 0.0.0.0 --port 8000`
- [ ] **Verify:** Hit `http://<ec2-public-ip>:8000/docs` from your browser and see Swagger UI

### Step 1.3 — Launch RDS PostgreSQL
- [ ] Launch `db.t3.micro` RDS PostgreSQL instance
- [ ] Place it in the **same VPC** as your EC2
- [ ] Security Group: Allow port 5432 **only from your EC2's security group** (not open to internet)
- [ ] Note down the RDS endpoint URL
- [ ] Update `.env` on EC2 with the new `DATABASE_URL` pointing to RDS
- [ ] Run Alembic migrations from EC2: `python -m alembic upgrade head`
- [ ] **Verify:** App connects to RDS. Test an API endpoint that reads/writes data.

### Step 1.4 — Move Secrets Into AWS Parameter Store
- [ ] Create an IAM Role for EC2 with `AmazonSSMReadOnlyAccess` policy
- [ ] Attach the IAM Role to your EC2 instance
- [ ] Store your secrets in AWS Systems Manager Parameter Store:
  - `DATABASE_URL`
  - `SECRET_KEY` (JWT)
- [ ] Update your app to read secrets from Parameter Store using `boto3`
- [ ] Remove the `.env` file from the server
- [ ] **Verify:** App still starts and works without a `.env` file on the server

### Step 1.5 — Make the App Survive Reboots with systemd
- [ ] Create a `systemd` service unit file for your FastAPI app
- [ ] Enable the service: `sudo systemctl enable jobpilot`
- [ ] Start it: `sudo systemctl start jobpilot`
- [ ] **Verify:** Reboot the EC2 instance. App comes back up automatically without SSH.

### Step 1.6 — Add HTTPS with Nginx + ACM
- [ ] Install Nginx on EC2
- [ ] Configure Nginx as a reverse proxy: port 80 → port 8000 (internally)
- [ ] Request a free SSL certificate from AWS Certificate Manager (ACM)
- [ ] Configure Nginx for HTTPS using the certificate
- [ ] **Verify:** App is accessible via `https://`

### ✅ Phase 1 Checkpoint
- [ ] App is live on EC2, accessible via HTTPS
- [ ] Data is stored in RDS PostgreSQL (not SQLite)
- [ ] Secrets are in Parameter Store (no `.env` on server)
- [ ] App survives reboots automatically
- [ ] **Write down:** What broke? How did you fix it? — capture this now, it's your interview story

---

## Phase 2 — Redis + Background Workers + Gunicorn

> **Goal:** Production-grade app server. Move from a single `uvicorn` process to a real multi-worker setup.

### Step 2.1 — Launch ElastiCache Redis
- [ ] Launch `cache.t3.micro` ElastiCache Redis cluster
- [ ] Place it in the **same VPC** as EC2
- [ ] Security Group: Allow port 6379 from EC2's security group only
- [ ] Note the Redis endpoint URL
- [ ] **Verify:** From EC2, run `redis-cli -h <endpoint> -p 6379 ping` → returns `PONG`

### Step 2.2 — Wire Up Redis Caching in Your App
- [ ] Install `redis[asyncio]` in requirements
- [ ] Implement cache-aside pattern for `/applications/kanban` endpoint:
  - Check Redis first → return cached data if found (cache hit)
  - On cache miss → query DB → store result in Redis with TTL
  - On PATCH/DELETE → explicitly invalidate the cache key
- [ ] **Verify:** Hit kanban endpoint twice. Second call is faster. Check Redis with `redis-cli` to confirm key exists.

### Step 2.3 — Move Scraper to Background Worker
- [ ] Install `arq` (ARQ task queue library, Redis-backed)
- [ ] Convert the Playwright scraping flow into an ARQ background task
- [ ] `POST /applications/url/preview` → puts job in Redis queue → returns `job_id` immediately
- [ ] New endpoint: `GET /jobs/{job_id}/status` → client polls for completion
- [ ] Run ARQ worker process as a separate systemd service on EC2
- [ ] **Verify:** Submit a scrape URL. API returns immediately with `job_id`. Poll status endpoint and watch it go `pending` → `complete`.

### Step 2.4 — Switch to Gunicorn Multi-Worker
- [ ] Install `gunicorn`
- [ ] Update systemd service command to: `gunicorn -k uvicorn.workers.UvicornWorker -w 4 main:app`
- [ ] Worker count formula: `(2 × CPU cores) + 1`. For `t3.small` (2 vCPU) = 5 workers
- [ ] **Verify:** `ps aux | grep gunicorn` shows multiple worker processes running

### Step 2.5 — Set Up CloudWatch Logs
- [ ] Install CloudWatch Agent on EC2
- [ ] Ship FastAPI app logs to a CloudWatch Log Group
- [ ] Create one CloudWatch Alarm: CPU > 80% → sends email alert
- [ ] **Verify:** Make a few API calls, then check CloudWatch Logs console and confirm logs appear

### ✅ Phase 2 Checkpoint
- [ ] Redis is running in ElastiCache and connected to app
- [ ] At least one endpoint is cached with TTL + cache invalidation on writes
- [ ] Scraper runs in background (API request returns immediately with `job_id`)
- [ ] Gunicorn is running with multiple worker processes
- [ ] CloudWatch logs are flowing in
- [ ] **Draw your architecture diagram and save it** (draw.io / Excalidraw / hand-drawn + photo)

---

## Phase 3 — PgBouncer + Load Balancer + Horizontal Scaling

> **Goal:** Highest resume-value phase. This is what separates you from 95% of junior developers.

### Step 3.1 — Install and Configure PgBouncer
- [ ] Install PgBouncer on the EC2 instance (or a dedicated `t3.micro` instance)
- [ ] Configure it to sit between your app and RDS:
  - App connects to `localhost:5432` (PgBouncer)
  - PgBouncer manages the real connection pool to RDS
- [ ] Set `pool_mode = transaction`, `max_client_conn = 200`, `default_pool_size = 20`
- [ ] Update `DATABASE_URL` in Parameter Store to point to PgBouncer
- [ ] **Verify:** App still connects. Check PgBouncer stats: `psql -h localhost -p 5432 -U pgbouncer pgbouncer -c "SHOW POOLS;"`

### Step 3.2 — Baseline Load Test (Before Scaling)
- [ ] Install k6 on your local machine
- [ ] Write a k6 test script that simulates:
  - Login → get JWT token
  - Fetch kanban board
  - Fetch paginated applications
  - Ramp from 50 → 200 virtual users
- [ ] Run the test against the **current single-instance setup**
- [ ] **Record and save:** req/s, p95 latency, error rate at saturation point
- [ ] **Verify:** Saved baseline benchmark file with real numbers

### Step 3.3 — Launch Second EC2 Instance
- [ ] Create an AMI (Amazon Machine Image) from your current working EC2
- [ ] Launch a second `t3.small` from that AMI
- [ ] Confirm the second instance connects to the same RDS and Redis
- [ ] **Verify:** Both EC2 instances respond correctly at their individual public IPs

### Step 3.4 — Set Up Application Load Balancer (ALB)
- [ ] Create an ALB in the same VPC
- [ ] Create a Target Group with both EC2 instances as targets
- [ ] Configure health check on `GET /health` endpoint (add a simple health endpoint to your app if missing)
- [ ] Update Security Groups: EC2 instances only accept HTTP traffic from ALB (not directly from internet)
- [ ] **Verify:** ALB DNS name responds and traffic routes to both instances (check logs on both EC2s)

### Step 3.5 — Load Test After Horizontal Scaling
- [ ] Run the same k6 test from Step 3.2 — this time against the **ALB DNS name**
- [ ] **Record and save:** new req/s, p95 latency, error rate
- [ ] Compare against baseline numbers from Step 3.2
- [ ] (Optional) Add a 3rd EC2 instance and re-run for full scaling curve
- [ ] **Verify:** You have before/after numbers showing clear measurable improvement

### ✅ Phase 3 Checkpoint — Your Resume Metric is Now Real
- [ ] PgBouncer is handling DB connection pooling
- [ ] ALB distributes traffic across 2+ EC2 instances
- [ ] Load test results documented:
  - Baseline (single instance, no caching): `___ req/s`
  - After Redis caching + PgBouncer: `___ req/s`
  - After horizontal scaling (2+ EC2 behind ALB): `___ req/s`
- [ ] **Save the k6 output files** — you cannot regenerate real metrics later

---

## Phase 4 — Frontend + CDN + Monitoring Polish

> **Goal:** Complete the architecture end to end. Make it look like a real production system.

### Step 4.1 — Deploy React Frontend to S3
- [ ] Run `npm run build` in your frontend directory
- [ ] Create an S3 bucket with public static website hosting enabled
- [ ] Upload the `dist/` folder contents to S3
- [ ] **Verify:** S3 website endpoint serves your React app in a browser

### Step 4.2 — Put CloudFront in Front of S3
- [ ] Create a CloudFront distribution with the S3 bucket as origin
- [ ] Set default root object to `index.html`
- [ ] Configure error page: 404 → `index.html` (required for React Router to work)
- [ ] Attach your ACM certificate to CloudFront for HTTPS
- [ ] **Verify:** CloudFront URL serves the React app over HTTPS

### Step 4.3 — Connect Frontend to ALB Backend
- [ ] Update the API base URL in your React app to point to the ALB DNS
- [ ] Rebuild and re-upload to S3
- [ ] Run CloudFront cache invalidation: `aws cloudfront create-invalidation --paths "/*"`
- [ ] **Verify:** Full end-to-end flow works: Browser → CloudFront → S3 (React) + ALB → FastAPI → RDS/Redis

### Step 4.4 — (Optional) Custom Domain with Route 53
- [ ] If you own a domain, create a hosted zone in Route 53
- [ ] Point frontend subdomain (e.g., `app.yourdomain.com`) → CloudFront
- [ ] Point API subdomain (e.g., `api.yourdomain.com`) → ALB
- [ ] **Verify:** App accessible via custom domain with valid HTTPS certificate

### Step 4.5 — CloudWatch Monitoring Dashboard
- [ ] Create a CloudWatch Dashboard with these widgets:
  - EC2 CPU utilization (both instances)
  - ALB request count per minute
  - ALB HTTP 5xx error rate
  - RDS CPU and active connections
  - ElastiCache cache hit rate
- [ ] **Screenshot the dashboard** — this is portfolio evidence, save it permanently
- [ ] **Verify:** Dashboard shows live data from all services

### Step 4.6 — IAM Security Review
- [ ] Review all IAM roles and policies created during the deployment
- [ ] Remove any wildcard `*` permissions added out of convenience
- [ ] Principle of least privilege: each service only has what it specifically needs
- [ ] **Verify:** App still works correctly after tightening IAM permissions

### Step 4.7 — Final Stress Test
- [ ] Run one final k6 load test with the complete setup (CloudFront + ALB + Redis caching + PgBouncer + 2 EC2)
- [ ] Save the final numbers to your load test report
- [ ] **Verify:** Results are captured and committed to your repo

### ✅ Phase 4 Checkpoint
- [ ] React app served via CloudFront (HTTPS, globally fast)
- [ ] Frontend connects to backend via ALB
- [ ] CloudWatch dashboard screenshot saved to repo
- [ ] Final load test numbers saved
- [ ] IAM reviewed and tightened

---

## Phase 5 — Document, Capture Evidence, Pause Cleanly

> **Goal:** Convert the deployment into a permanent portfolio artifact. Then shut everything down safely.

### Step 5.1 — Write Load Test Report
- [ ] Create `docs/load-test-report.md` in your repo with:
  - Test setup (k6 config, virtual users, endpoints tested)
  - Baseline numbers (single instance, no cache)
  - After-caching + PgBouncer numbers
  - After-horizontal-scaling numbers
  - What broke, what improved, and why
- [ ] **Verify:** Report committed and pushed to GitHub

### Step 5.2 — Write Architecture Decision Records (ADR)
- [ ] Create `docs/architecture-decisions.md` with short explanations for:
  - Why ElastiCache over self-hosted Redis
  - Why PgBouncer over app-level connection pooling
  - Why ALB over Nginx as load balancer
  - Why ARQ over Celery for background jobs
- [ ] **Verify:** Document committed to GitHub

### Step 5.3 — Write Deployment Runbook
- [ ] Create `docs/deploy-runbook.md` with exact commands to reproduce the full deployment from scratch
- [ ] Goal: anyone with AWS credentials should be able to follow it and get the app running
- [ ] **Verify:** Do a mental walkthrough — would a stranger understand it without help?

### Step 5.4 — (Optional) Partial Terraform / IaC
- [ ] Write Terraform resource definitions for at least:
  - EC2 instance
  - RDS instance
  - Security Groups
- [ ] Store in `infra/terraform/` directory
- [ ] **Verify:** `terraform plan` runs without errors (you don't need to `apply` it)

### Step 5.5 — Take Screenshots and Capture Evidence
- [ ] CloudWatch dashboard (full screenshot)
- [ ] ALB target group showing both instances healthy (green)
- [ ] RDS Monitoring tab with metrics graph
- [ ] ElastiCache metrics
- [ ] AWS Billing dashboard showing total cost
- [ ] Save all screenshots in `docs/screenshots/` and commit to GitHub

### Step 5.6 — Record a Demo Video
- [ ] Record a 3–5 minute screen capture showing:
  - Architecture diagram walkthrough
  - Live app working end-to-end
  - CloudWatch dashboard with real metrics
  - Load test results comparison
- [ ] Upload to YouTube (unlisted) or save as a file
- [ ] Link it in your GitHub README

### Step 5.7 — Update Resume and README
- [ ] Fill in the resume bullet template with your real numbers:
  > *Deployed FastAPI backend to AWS (EC2, RDS, ElastiCache, ALB) with Gunicorn multi-worker processes and PgBouncer connection pooling. Load tested with k6: single instance saturated at ~___ req/s; after Redis caching + PgBouncer, throughput improved to ~___ req/s; horizontal scaling to ___ EC2 instances behind ALB achieved ~___ req/s. Deployment documented with runbook and architecture decision records.*
- [ ] Update GitHub README with architecture diagram and link to demo video
- [ ] **Verify:** README tells the full story without you needing to explain it verbally

### Step 5.8 — Pause Everything (Kill Order Matters)
> Kill services in this exact order to minimize final charges:
- [ ] **1st: Delete ALB** — bills hourly even when completely idle
- [ ] **2nd: Terminate EC2 instances** — stopping still bills for EBS storage; terminate unless you need them again
- [ ] **3rd: Take RDS snapshot → then delete RDS** (snapshot is your recovery option)
- [ ] **4th: Delete ElastiCache cluster**
- [ ] **5th: Empty and delete S3 buckets** (or set lifecycle rules to auto-expire)
- [ ] **6th: Verify in AWS Billing Dashboard** — confirm $0 ongoing charges

### ✅ Phase 5 Checkpoint — Done
- [ ] Load test report committed
- [ ] Architecture decision records written
- [ ] Deploy runbook written
- [ ] All screenshots saved in repo
- [ ] Demo video recorded and linked in README
- [ ] Resume bullet filled with real numbers
- [ ] All AWS resources terminated
- [ ] Billing dashboard shows $0 ongoing charges

---

## Interview Preparation Lines

**"Can I see it live?"**
> "It's currently paused since I was running it on AWS credits — I have the full deployment documented with load test results and can walk you through the architecture, or spin it back up in about 10–15 minutes if you'd like to see it live."

**"Why PgBouncer instead of just increasing connection pool size in SQLAlchemy?"**
> *(Answer from your ADR document — you wrote this)*

**"What broke during deployment and how did you fix it?"**
> *(Answer from your Phase 1 and Phase 2 checkpoint notes — capture this while it's fresh)*

**"How would you scale this further beyond what you built?"**
> Read replicas for analytics queries, SQS for more durable job queues, ECS/Fargate to replace manual EC2 management, Aurora Serverless for auto-scaling DB, WAF in front of ALB for security.

---

## Non-Negotiables

1. **Set $50 billing alert before touching anything.** Non-negotiable.
2. **Never commit secrets to GitHub.** Everything goes in Parameter Store.
3. **Capture screenshots BEFORE teardown.** You cannot recreate CloudWatch graphs after deletion.
4. **Debug and fix before moving to the next step.** No skipping broken steps.
5. **Push to GitHub regularly.** Commits with real timestamps are evidence of genuine sustained work.
6. **Verify before proceeding.** Do not skip the verification checklist on any step.

---

## Quick Reference — AWS Services and Their Purpose

| AWS Service | What It Does in This Project |
|---|---|
| **EC2** | Runs your FastAPI app (Gunicorn + Uvicorn workers) |
| **RDS** | Managed PostgreSQL — your production database |
| **ElastiCache** | Managed Redis — caching + ARQ background job queue |
| **ALB** | Distributes traffic across multiple EC2 instances |
| **S3** | Hosts your React production build (static files) |
| **CloudFront** | CDN — serves React globally with HTTPS and low latency |
| **ACM** | Free SSL/TLS certificates for HTTPS |
| **IAM** | Controls who/what can access which AWS services |
| **Parameter Store** | Stores secrets (DB password, JWT key) securely |
| **CloudWatch** | Logs, metrics, alarms, and monitoring dashboards |
| **Route 53** | DNS — points your domain to ALB and CloudFront |
| **PgBouncer** | Connection pooler — sits between app and RDS |
| **Gunicorn** | Process manager — runs multiple Uvicorn worker processes |
| **k6** | Load testing tool — generates the resume metrics |

---

*This guide is executed part by part, step by step.*
*Each concept will be taught before you execute it.*
*Do not proceed to the next step until the current one is verified and working.*
