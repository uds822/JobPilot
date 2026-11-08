# 🚀 JobPilot — DevOps, Docker & CI/CD Quick Guide

> **Prepared for Your Interview**: Simple, clear, human-readable explanation of the Docker, Redis, Background Worker, and CI/CD setup implemented in this project. Use this cheat-sheet to confidently speak about your DevOps workflow.

---

## 📌 1. What Was Implemented (At a Glance)

1. **Backend Multi-Stage Dockerfile** (`backend/Dockerfile`):
   - Python 3.12-slim base image.
   - Stage 1 compiles dependencies; Stage 2 creates a clean, lightweight runtime.
   - Non-root user (`appuser`) for security.
   - Custom entrypoint script (`docker-entrypoint.sh`) that waits for PostgreSQL to be ready and automatically runs `alembic upgrade head` before booting FastAPI.
2. **Frontend Multi-Stage Dockerfile** (`frontend/Dockerfile` + `nginx.conf`):
   - Stage 1 uses Node 20 to compile TypeScript and bundle Vite assets.
   - Stage 2 copies the `/dist` build into an ultra-lean Nginx container.
   - `nginx.conf` serves static HTML/JS/CSS and acts as a **reverse proxy** forwarding `/api/`, `/applications`, etc. to the backend container, eliminating CORS issues.
3. **Standalone Background Worker** (`backend/app/worker.py`):
   - Reuses the backend image to run ATS job discovery and ingestion cycles in the background.
   - Keeps heavy scraping tasks off the main web request thread (12-Factor App methodology).
4. **Local Multi-Service Orchestration** (`docker-compose.yml`):
   - One command launches all 5 services: **PostgreSQL 16**, **Redis 7**, **FastAPI Backend**, **Background Worker**, and **Nginx/React Frontend**.
   - Includes automatic healthchecks and volume persistence for database and cache.
5. **Automated CI/CD Pipeline** (`.github/workflows/`):
   - `ci.yml`: On every Push or Pull Request, spins up live Postgres & Redis containers in GitHub Actions, runs Alembic migrations, executes unit tests, checks Vite compilation, and verifies Docker image builds.
   - `cd.yml`: On push to `main`, builds and tags release containers for the GitHub Container Registry (GHCR).

---

## 💬 2. Interview Q&A Cheat-Sheet

Here are the exact questions interviewers ask when you say you know Docker and CI/CD, and the authentic answers for this project:

### Q1: *"Why did you use Docker in this project?"*
> **Answer**:  
> *"To ensure a consistent development and deployment environment. Our application depends on multiple services: PostgreSQL, Redis for rate limiting, a FastAPI API, a background worker for scraping ATS boards, and an Nginx server for our React frontend. With Docker and Docker Compose, any developer can spin up the complete environment with a single `docker compose up --build` command without manual dependency installations."*

### Q2: *"Can you explain what a multi-stage Docker build is and why you used it?"*
> **Answer**:  
> *"In a single-stage build, build tools like gcc, pip caches, or node_modules remain in the final image, making it 1GB+ in size and increasing security attack surfaces.  
> We used multi-stage builds:  
> - In the **frontend**, Node.js compiles the Vite assets in stage 1, and stage 2 copies only the compiled static HTML/CSS/JS into a tiny 25MB Nginx image.  
> - In the **backend**, build tools compile dependencies in stage 1, and only the installed packages are copied to a slim Python runtime in stage 2."*

### Q3: *"How do you handle database migrations when running in containers?"*
> **Answer**:  
> *"We use a container entrypoint script (`docker-entrypoint.sh`). When the backend container starts, it first checks that PostgreSQL is healthy, runs `alembic upgrade head` to apply any pending schema migrations, and then launches the Uvicorn web server. This ensures the database schema is always in sync with the codebase before handling traffic."*

### Q4: *"Where and why did you use Redis?"*
> **Answer**:  
> *"We use Redis for two core things:  
> 1. **Atomic Sliding-Window Rate Limiting**: On our job scraping preview endpoints, we execute a Lua script in Redis (`INCR` + `EXPIRE`) to prevent abuse from external requests.  
> 2. **Distributed Leases**: In our ATS ingestion workers, Redis prevents multiple worker instances from scraping the same career portal simultaneously."*

### Q5: *"Why is the Worker a separate service from the Backend?"*
> **Answer**:  
> *"Following 12-factor application design, web servers should remain stateless and responsive to HTTP requests. Scraping and polling 200+ employer portals can take minutes and consume memory. By separating the web API and the background worker into two containers that share the same database and Redis, heavy background ingestion never blocks user interactions on the website."*

### Q6: *"How does your CI/CD pipeline work?"*
> **Answer**:  
> *"We use GitHub Actions. On every pull request or push:  
> 1. It spins up live PostgreSQL 16 and Redis 7 service containers in the GitHub runner.  
> 2. It runs Alembic migrations and our Pytest test suite.  
> 3. It checks frontend TypeScript compilation (`npm run build`).  
> 4. Finally, it tests that both Dockerfiles build cleanly.  
> If anything fails, the PR is blocked, preventing broken code from reaching production."*

---

## 🛠️ 3. Useful Commands to Know / Demo

If the interviewer asks you to run or show Docker in your terminal:

```bash
# 1. Start the entire application stack in the background
docker compose up -d --build

# 2. Check the health status of all 5 services
docker compose ps

# 3. View live logs from the backend or worker
docker compose logs -f backend
docker compose logs -f worker

# 4. Stop everything cleanly
docker compose down
```

---

## ✅ 4. What You Need to Do Today

1. **Commit and Push to GitHub**:
   Push the new files (`Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`) to your GitHub repository.
2. **Check the GitHub Actions tab**:
   Go to your repository on `github.com` and click the **Actions** tab. You will see your automated workflow run and produce a **Green Checkmark**!
3. **Keep this file open**:
   Review the Q&A section above right before your interview tomorrow so the terms (multi-stage build, entrypoint migration, reverse proxy, Redis rate limiting) are fresh in your mind.

