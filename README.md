# 🚀 JobPilot — AI-Powered Job Discovery & Application Tracking Platform

> **JobPilot** is an enterprise-grade, high-performance job application tracking and AI discovery platform built with **FastAPI**, **PostgreSQL**, **Redis**, **React 18**, and **TypeScript**. Designed for modern job seekers, JobPilot integrates intelligent resume parsing, multi-provider job fetching, multi-tiered LLM match scoring, automated ATS feed ingestion, and a scalable 5-stage Kanban pipeline.

---

## 🌟 Key Features

### 🧠 1. AI Job Discovery & Multi-Stage Matching Engine
- **Resume Profile Parsing**: Automatically extracts technical skill vectors, experience levels, and primary job archetypes from uploaded resume PDFs.
- **Query Expansion Engine**: Generates targeted, role-specific query permutations across titles, core technologies, and domain keywords.
- **Multi-Provider Concurrent Ingestion**: Simultaneously aggregates job listings from external APIs (Adzuna), direct ATS job boards (Greenhouse, Lever), and local canonical company databases.
- **Multi-Tiered LLM Matching Pipeline**: High-throughput match scoring with a primary LLM (Groq), secondary API fallback (OpenRouter), and a deterministic heuristic fallback for uninterrupted service availability.
- **Non-Blocking Async Processing**: Asynchronous background search runs with real-time status polling, run histories, and structured breakdown of job-to-resume relevance.

### 📋 2. Scalable Paginated Applications Kanban Board
- **5-Stage Application Pipeline**: Track jobs across `Applied`, `Interviewing`, `Offered`, `Rejected`, and `Withdrawn`.
- **Per-Column Independent Pagination**: Optimized query fetching prevents interface lag and allows smooth navigation through thousands of stored applications.
- **Optimistic UI & Transaction Security**: Instant UI card updates with automatic rollback on network error, paired with database-level user isolation.
- **Glassmorphism UI System**: Modern Midnight Acrylic visual design with CSS design tokens and micro-animations.

### 🏢 3. Company Watch & Automated ATS Ingestion
- **150+ Pre-Configured Tech Employers**: Continuously monitors top engineering organizations and direct career portals.
- **Direct ATS Adapters**: Built-in support for Greenhouse, Lever, Ashby, Workday, SmartRecruiters, and structured web postings.
- **CLI Management & Background Polling**: Robust CLI tooling for company verification, automated discovery, seed migration, and source lease locks.

### 🌐 4. One-Click Job URL Scraper
- **Automated Metadata Extraction**: Scrapes job titles, company names, locations, and full posting text directly from URL inputs.
- **Headless Browser Fallback**: Resilient scraping fallback using headless browser automation for dynamic JavaScript-heavy job boards.

### 📊 5. Analytics & Security Dashboard
- **Application Funnel Analytics**: Visualized application distributions, interview conversion rates, and monthly activity metrics.
- **OWASP-Compliant Security**: JWT authentication with password hashing, request rate-limiting, CORS configuration, and DOM sanitization.

---

## 🏗️ Architecture & Infrastructure

### High-Level System Architecture

```
                                 ┌────────────────────────┐
                                 │   Users / Web Browser  │
                                 └───────────┬────────────┘
                                             │
                       ┌─────────────────────┴─────────────────────┐
                       │                                           │
                       ▼                                           ▼
             ┌───────────────────┐                       ┌───────────────────┐
             │ CloudFront CDN    │                       │  Application Load │
             └─────────┬─────────┘                       │   Balancer (ALB)  │
                       │                                 └─────────┬─────────┘
                       ▼                                           │
             ┌───────────────────┐                                 │ (Public Subnet)
             │  S3 Web Bucket    │                                 │
             │ (React Frontend)  │                                 ▼
             └───────────────────┘                       ┌───────────────────┐
                                                         │   EC2 Instance    │
                                                         │  (FastAPI Server) │
                                                         └─────────┬─────────┘
                                                                   │ (Private Subnet)
                                     ┌─────────────────────────────┼─────────────────────────────┐
                                     ▼                             ▼                             ▼
                           ┌───────────────────┐         ┌───────────────────┐         ┌───────────────────┐
                           │   RDS PostgreSQL  │         │ ElastiCache Redis │         │ AWS CloudWatch &  │
                           │(PgBouncer Pooled) │         │ (Caching & Queue) │         │  Parameter Store  │
                           └───────────────────┘         └───────────────────┘         └───────────────────┘
```

---

## 🛠️ Technology Stack

| Layer | Technology | Key Usage |
| :--- | :--- | :--- |
| **Backend Framework** | **FastAPI (Python 3.11+)** | Asynchronous RESTful API services, Pydantic v2 validation |
| **Database** | **PostgreSQL 15+** | Relational storage, multi-table schema, index optimization |
| **ORM & Migrations** | **SQLAlchemy 2.0 (Async) + Alembic** | Schema migrations, transaction safety, user-level isolation |
| **Caching & Ingestion** | **Redis + ARQ** | Rate limiting, async background search jobs, feed polling locks |
| **AI & Match Engine** | **Groq & OpenRouter APIs** | Multi-tier LLM match scoring, prompt engineering, resume parsing |
| **Frontend Framework** | **React 18 + TypeScript + Vite** | SPA architecture, custom hooks, type safety, modular components |
| **Styling & UI** | **Vanilla CSS + Glassmorphism Tokens** | Custom dark mode palette, smooth micro-interactions, responsive grid |
| **Web Scraping** | **Playwright & BeautifulSoup4** | Headless browser rendering, HTML parsing, ATS feed adapters |
| **Authentication** | **JWT & Argon2 / Bcrypt** | Secure password hashing, stateless token verification |
| **Cloud & DevOps** | **AWS (EC2, RDS, ElastiCache, ALB, S3, CloudFront)** | Multi-AZ cloud topology, SSL termination, static hosting |
| **Containers & CI/CD** | **Docker & GitHub Actions** | Multi-stage image builds, automated test pipelines, cloud deployment |

---

## 📂 Repository Structure

```
jobtracker/
├── backend/
│   ├── alembic/                  # Alembic database migration scripts
│   ├── app/
│   │   ├── ai/                   # AI discovery pipeline, prompt engine, score matchers
│   │   ├── company_watch/        # Automated ATS adapters, CLI verifier & ingester
│   │   ├── core/                 # App configuration, security context & environment setup
│   │   ├── database/             # Async DB session factory & engine setup
│   │   ├── middleware/           # Rate limiting & request logging middleware
│   │   ├── models/               # SQLAlchemy ORM schemas (Users, Jobs, Applications, AI Matches)
│   │   ├── routers/              # FastAPI REST routers (auth, applications, AI, jobs, companies)
│   │   ├── schemas/              # Pydantic v2 data models & response DTOs
│   │   ├── security/             # Password hashing, JWT token creation & verification
│   │   └── services/             # Core business logic & scraping integrations
│   ├── alembic.ini               # Alembic database configuration
│   ├── main.py                   # FastAPI main application entrypoint
│   └── requirements.txt          # Python backend dependencies
└── frontend/
    ├── src/
    │   ├── api/                  # Axios HTTP client & API route bindings
    │   ├── components/           # React UI components (Kanban, AIDiscovery, Analytics, Security)
    │   ├── data/                 # Local demo datasets & mock fallbacks
    │   ├── security/             # DOM sanitization utilities
    │   ├── App.tsx               # Root component & tab navigation state
    │   └── main.tsx              # React entry point
    ├── package.json              # Frontend package dependencies
    └── vite.config.ts            # Vite bundler configuration
```

---

## 🔌 Comprehensive API Reference

JobPilot exposes **25+ RESTful API endpoints** categorized by domain:

### 🔑 Authentication & Users
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/auth/login` | Authenticate user & receive JWT access token |
| `POST` | `/users/register` | Register a new job seeker account |
| `GET` | `/users/me` | Retrieve current authenticated user profile |

### 🤖 AI Job Discovery Engine
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/ai/resume` | Upload resume PDF, extract profile archetype & skill vector |
| `GET` | `/ai/profile` | Retrieve active user's AI resume profile |
| `POST` | `/ai/search` | Trigger non-blocking async job discovery search run |
| `GET` | `/ai/search/{run_id}` | Poll progress and status of an active search run |
| `GET` | `/ai/matches` | List scored job matches filtered by minimum match score |
| `GET` | `/ai/runs` | Fetch historical AI search run logs |
| `GET` | `/ai/canonical/{job_id}` | View canonical job metadata and scoring details |

### 📋 Applications Pipeline (Kanban)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/applications/kanban` | Fetch initial 5-column Kanban board layout with pagination metadata |
| `GET` | `/applications` | Fetch paginated application list by status filter |
| `POST` | `/applications/url/preview` | Scrape job details preview from an external URL |
| `POST` | `/applications/url/confirm` | Confirm scraped job details & save application |
| `POST` | `/applications/manual` | Create a new application entry manually |
| `PATCH` | `/applications/{id}` | Update application details, interview stage, or notes |
| `PATCH` | `/applications/{id}/status` | Move application card between pipeline stages |
| `DELETE` | `/applications/{id}` | Remove application entry |

### 🏢 Jobs Directory & Company Watch
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/jobs` | Search public canonical job directory |
| `GET` | `/jobs/{id}` | Retrieve specific job details |
| `GET` | `/companies` | List registered target companies and career portals |
| `GET` | `/companies/{id}` | Fetch company profile and verified ATS sources |

### 📊 Analytics & Health
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/analytics/summary` | Aggregate conversion funnel metrics and status breakdowns |
| `GET` | `/health` | System readiness check, database ping, and service status |

---

## ⚡ Local Setup & Development

### Prerequisites
- **Python**: `v3.11+`
- **Node.js**: `v18+`
- **PostgreSQL**: `v15+` running locally or via cloud instance
- **Redis**: Running locally or via cloud instance

---

### 🗄️ 1. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create and activate virtual environment
python -m venv .venv

# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file with appropriate settings
# DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/jobpilot
# REDIS_URL=redis://localhost:6379/0
# SECRET_KEY=your_secure_jwt_secret_key
# GROQ_API_KEY=your_groq_api_key
# OPENROUTER_API_KEY=your_openrouter_api_key

# Run database migrations
python -m alembic upgrade head

# Start development server
uvicorn main:app --reload --port 8000
```

Backend server will run at `http://localhost:8000`. API documentation is automatically accessible via Swagger UI at `http://localhost:8000/docs`.

---

### 💻 2. Frontend Setup

```bash
# Open terminal and navigate to frontend directory
cd frontend

# Install Node dependencies
npm install

# Start Vite development server
npm run dev
```

Frontend application will launch at `http://localhost:5173`.

---

### 🏢 3. Company Watch CLI Operations

The Company Watch module manages canonical employer targets and direct ATS feeds:

```bash
cd backend

# Seed default company registry and ATS sources
python -m app.company_watch.cli seed

# Verify connectivity to target ATS feeds
python -m app.company_watch.cli verify --limit 50 --concurrency 10

# Discover career source portals automatically
python -m app.company_watch.cli discover --limit 20 --concurrency 4

# Ingest active job postings into canonical storage
python -m app.company_watch.cli ingest --limit 50 --concurrency 10

# Check ingestion status and feed health coverage
python -m app.company_watch.cli status
```

---

## 🐳 Containerization & CI/CD

JobPilot supports containerized execution and automated testing workflows:

### Container Build
```bash
# Build backend application container
docker build -t jobpilot-backend ./backend

# Run application container with environment context
docker run -p 8000:8000 --env-file ./backend/.env jobpilot-backend
```

### Automated CI/CD Workflow
The project includes automated pipelines for:
- **Linting & Code Formatting**: Static analysis and type checking.
- **Automated Integration Testing**: Execution of test suite against isolated test databases.
- **Container Registry Push**: Automated building and publishing of Docker images on repository push.
- **Cloud Deployment**: Automated container rollout to production infrastructure.

---

## 🧪 Testing & Verification

Run automated backend API integration and pipeline tests:

```bash
cd backend
pytest
```

Verify production frontend build compilation:

```bash
cd frontend
npm run build
```

---

## 📜 License

Distributed under the MIT License. See `LICENSE` for details.

