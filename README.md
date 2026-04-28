# Blender Collab

**Collaborative Version Control for Blender**

A web-based Version Control System (VCS) for Blender, enabling teams to collaborate on 3D projects with granular version management. It replaces traditional file-based VCS by exporting individual Blender objects as JSON (with mesh data stored separately in S3), allowing efficient storage, content deduplication, and object-level version tracking.

## Documentation

| Document | Description |
|----------|-------------|
| [Storage & Versioning](./STORAGE.md) | File routing, object storage, deduplication, version management |
| [Architecture Diagrams](./ARCHITECTURE_DIAGRAMS.md) | Visual component relationships and data flows |
| [Deployment Guide](./DEPLOYMENT.md) | Production deployment (Railway + Vercel) and local Docker setup |
| [Download Guide](./DOWNLOAD_GUIDE.md) | Scripts for downloading Blender files from S3 |
| [Deliverables](./DELIVERABLES.md) | Internal project tracking and implementation summary |
| [Backend README](./backend/README.md) | Backend setup, API overview, environment variables |
| [Frontend README](./frontend/README.md) | Frontend setup and page structure |
| [Integration Guide](./backend/INTEGRATION_GUIDE.md) | Integrating storage into the commit workflow |
| [Storage Quick Reference](./backend/storage/QUICK_REFERENCE.md) | Storage API cheat sheet |
| [Blender Addon Install](./export/README.md) | Installing the BVCS Blender addon |
| [API Docs (local)](http://localhost:8000/docs) | Interactive Swagger docs (when running locally) |

## Quick Start (Docker Compose)

The easiest way to run the full stack locally.

### Prerequisites

- [Docker](https://www.docker.com/) and Docker Compose installed

### 1. Configure environment

Create a `.env` file in the project root:

```env
JWT_SECRET=<generate with: python -c "import secrets; print(secrets.token_urlsafe(32))">

# S3 / MinIO
S3_ACCESS_KEY=##################### or minioadmin for local MinIO
S3_SECRET_KEY=##################### or minioadmin for local MinIO

# SMTP (optional — if not set, email delivery fails closed; set EMAIL_DEBUG=true for local dev to print links to console)
SMTP_HOST=example.com
SMTP_PORT=####
SMTP_USER=your-email@example.com
SMTP_PASSWORD=your-smtp-password
SMTP_FROM=noreply@yourdomain.com
EMAIL_DEBUG=true
FRONTEND_URL=http://localhost:3000
```

### 2. Build and run

```bash
docker compose up --build
```

### 3. Access

| Service | URL |
|---------|-----|
| Frontend | [http://localhost:3000](http://localhost:3000) |
| Backend API Docs | [http://localhost:8000/docs](http://localhost:8000/docs) |
| MinIO Console | [http://localhost:9001](http://localhost:9001) |

### 4. Stop

```bash
docker compose down
```

## Features

### Authentication & Accounts
- JWT-based authentication with Bearer tokens
- Email verification on signup (link sent via SMTP or printed to console)
- Forgot / reset password flow with secure single-use tokens
- Account deletion with ownership transfer for shared projects

### Project Collaboration
- Create and manage Blender projects
- Invite collaborators by email with role-based permissions (owner / editor / viewer)
- Accept or decline project invitations
- Object-level locking to prevent conflicting edits

### Version Control
- Branch and commit history (timeline view)
- Object-level diffing and merge conflict detection
- Content deduplication via SHA-256 hashing
- Full `.blend` snapshots for recovery

### Blender Addon
- Export, commit, pull, and resolve conflicts from inside Blender
- See the [addon install guide](./export/README.md)

### Web Dashboard
- Project history and commit browser
- File uploads and downloads
- Storage statistics and version history

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend API | FastAPI (Python 3.11) |
| Database | PostgreSQL 15 |
| Object Storage | MinIO / AWS S3 |
| Frontend | Next.js 16, React 19, Tailwind CSS 4 |
| Authentication | JWT (python-jose + bcrypt) |
| Email | SMTP via smtplib (with console fallback) |
| Blender Addon | Python (bpy) |
| Containerization | Docker Compose |

## Environment Variables

All variables are set in the root `.env` file and injected into containers via `docker-compose.yml`.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `JWT_SECRET` | **Yes** | — | Secret key for signing JWT tokens |
| `DATABASE_URL` | No | Set in compose | PostgreSQL connection string |
| `S3_ENDPOINT` | No | `https://s3.us-east-1.amazonaws.com` | S3-compatible endpoint (use `http://minio:9000` for local MinIO) |
| `S3_ACCESS_KEY` | **Yes** | — | S3 access key |
| `S3_SECRET_KEY` | **Yes** | — | S3 secret key |
| `S3_SECURE` | No | `true` | Use HTTPS for S3 (`false` for local MinIO) |
| `S3_BUCKET` | No | `blender-vcs-prod` | S3 bucket name (`capstonebots` for local MinIO) |
| `S3_REGION` | No | `us-east-1` | S3 region |
| `SMTP_HOST` | No | — | SMTP server (required for email delivery; see `EMAIL_DEBUG`) |
| `SMTP_PORT` | No | `2525` | SMTP port |
| `SMTP_USER` | No | — | SMTP login |
| `SMTP_PASSWORD` | No | — | SMTP password |
| `SMTP_FROM` | No | `SMTP_USER` | From address for emails |
| `EMAIL_DEBUG` | No | `false` | Print verification/reset links to console when SMTP is not configured (local dev only) |
| `FRONTEND_URL` | No | `http://localhost:3000` | Base URL for email links |
| `INVITE_EXPIRY_DAYS` | No | `7` | Days before invitations expire |

## Manual Setup (Without Docker)

### Prerequisites

- Python 3.9+
- Node.js 20+ and npm
- PostgreSQL (running locally or accessible)
- MinIO (optional, for storage features)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Database Only (via Docker)

```bash
docker compose up -d db
```

## Testing

This project uses:

- Backend: pytest (unit + behavioral API tests)
- Frontend: Jest + React Testing Library (unit + behavioral UI tests)

The goal is to run one command before each commit and catch regressions in authentication, project collaboration, and core UI flows.

### Install / Setup

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install

# Optional for DB-backed behavioral tests
cd ..
docker compose up -d db
```

### Run All Tests (Single Command)

From repo root:

```bash
./tests/run_all_tests.sh
```

This runs backend core tests first, then frontend tests.
Storage integration tests that require MinIO/S3 are intentionally excluded from this command.

### What This Covers

- Unit tests: pure logic and boundary conditions (empty/invalid input, duplicate states, role checks)
- Behavioral tests: API and UI flows that mirror real user behavior
- Regression guard: invitation lifecycle, access control, and auth refresh behavior

### Test Location Pattern

- Backend tests: `backend/tests/test_*.py`
- Frontend tests: `frontend/tests/**/*.test.ts?(x)` and `frontend/src/__tests__/**/*.test.ts?(x)`

### Helpful Targeted Commands

```bash
# Backend — unit tests only
cd backend && .venv/bin/python -m pytest tests/test_unit_auth.py tests/test_unit_models.py tests/test_unit_schemas.py tests/test_unit_schemas_extended.py tests/test_unit_storage_utils.py -v

# Backend — behavioral tests only
cd backend && .venv/bin/python -m pytest tests/test_auth.py tests/test_projects.py tests/test_authorization.py tests/test_behavior_api.py tests/test_behavior_projects_auth.py tests/test_delete_account.py -v

# Frontend — unit tests only
cd frontend && npm test -- --testPathPattern="authApi|projectsApi" --watchAll=false

# Frontend — behavioral tests only
cd frontend && npm test -- --testPathPattern="AuthProvider|LoginPage|SignupPage|HomePage|CommitItem" --watchAll=false

# Backend — all core tests (unit + behavioral)
cd backend && .venv/bin/python -m pytest tests/ -v --ignore=tests/test_storage.py --ignore=tests/test_object_storage.py

# Frontend — all tests
cd frontend && npm test -- --watchAll=false

# Newly added milestone tests
cd backend && .venv/bin/python -m pytest tests/test_unit_project_utils.py tests/test_behavior_invitation_lifecycle.py -v
cd frontend && npm test -- tests/AuthProvider.behavior.test.tsx --runInBand

# Storage tests (mock-based, no MinIO/S3 needed)
cd backend && .venv/bin/python -m pytest tests/test_storage.py -v

# Object storage integration tests (requires live S3 — runs in CI)
cd backend && .venv/bin/python -m pytest tests/test_object_storage.py -v
```

### Troubleshooting

- If `./tests/run_all_tests.sh` fails immediately:
  - create backend virtualenv and install dependencies using setup commands above.
- If DB-backed behavioral tests are skipped:
  - start PostgreSQL with `docker compose up -d db`.
- If storage integration tests fail with connection errors:
  - ensure MinIO/S3 endpoint and credentials are configured, then run those tests separately.
- If frontend tests fail with missing packages:
  - run `cd frontend && npm install`.

## Project Structure

```
CapstoneBots/
├── backend/                 # FastAPI backend
│   ├── main.py              # App entry point
│   ├── models.py            # SQLAlchemy models
│   ├── schemas.py           # Pydantic schemas
│   ├── database.py          # DB connection
│   ├── routers/             # API route handlers
│   │   ├── users.py         # Auth, registration, password reset, verification
│   │   ├── projects.py      # Projects, branches, commits, collaboration
│   │   └── storage.py       # File upload/download, storage stats
│   ├── utils/               # Auth, email, permissions helpers
│   ├── storage/             # S3/MinIO service layer
│   ├── migrations/          # Database migrations
│   └── tests/               # pytest test suite
├── frontend/                # Next.js frontend
│   └── src/
│       ├── app/             # Pages (login, signup, projects, settings, etc.)
│       ├── components/      # Shared components (AuthProvider, etc.)
│       └── lib/             # API client functions
├── export/                  # Blender addon ZIP + install guide
├── blender_vcs/             # Blender addon source
├── docker-compose.yml       # Full local stack
└── .env                     # Environment variables (not committed)
```

## Authors

- Aarsh Patel — aarsh@email.sc.edu
- Alex Mesa — mesacora@email.sc.edu
- Paksh Patel — paksh@email.sc.edu
- Joseph Vann — jrvann@email.sc.edu
- Vraj Patel — vtpatel@email.sc.edu

---

**Last Updated**: February 2026
