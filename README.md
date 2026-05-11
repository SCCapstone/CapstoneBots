# Blender Collab

> **Collaborative version control for Blender — a web app + Blender add-on that brings Git-style commits, branches, and merge-conflict resolution to 3D scenes by tracking individual Blender objects (not whole `.blend` files) for efficient, deduplicated, object-level history.**

---

## Service Status

> ### NOT LIVE — Hosted service taken offline on **2026-05-05**
>
> The hosted Blender Collab service (DigitalOcean Hosting + S3 storage) has been **shut down as of May 5, 2026** because of ongoing hosting / object-storage costs.
>
> **What this means for you:**
> - The link `https://blendercollab.pakshpatel.tech` will no longer respond.
> - The Blender add-on cannot push or pull from the hosted backend.
> - Account signups, password resets, and project invites no longer work against the hosted instance.
>
> **What's planned (possibly):**
> - A slimmed-down version of the app may eventually be redeployed at lower cost. No firm timeline.
>
> **What you can still do:**
> - Clone this repository and run the entire stack locally with Docker Compose. Everything — frontend, backend, database, MinIO object storage, and the Blender add-on — works end-to-end on a single machine. See [Quick Start](#quick-start-run-it-locally) below.

---

## What's in this Repo

| Component | Description |
|-----------|-------------|
| **Web App** (`backend/` + `frontend/`) | FastAPI + Postgres backend and a Next.js / React dashboard for browsing projects, commits, members, and per-object version history. |
| **Blender Add-on** (`blender_vcs/`) | A native Blender add-on (Python / `bpy`) that exports each object as JSON + glTF, hashes mesh blobs, and pushes/pulls commits against the backend from inside Blender's UI. |
| **Local Stack** (`docker-compose.yml`) | One-command Docker Compose stack that brings up Postgres, MinIO, the FastAPI API, and the Next.js frontend together. |

## Features

### Authentication & Accounts
- JWT-based auth with bearer tokens
- Email verification on signup (SMTP or console fallback for local dev)
- Forgot / reset password flow with single-use tokens
- Account deletion with ownership transfer for shared projects

### Project Collaboration
- Create and manage Blender projects
- Invite collaborators by email with role-based permissions (owner / editor / viewer)
- Accept or decline project invitations from the dashboard
- Object-level locking to prevent conflicting edits

### Version Control
- Branch and commit history with a timeline view
- Object-level diffing and merge-conflict detection
- Content deduplication via SHA-256 hashing of mesh blobs
- Full `.blend` snapshot uploads for recovery

### Blender Add-on
- Stage, commit, push, and pull from inside Blender
- Per-object diff and conflict resolution UI
- See [`export/README.md`](./export/README.md) for install steps

### Web Dashboard
- Project history and commit browser
- File uploads and downloads
- Storage statistics and per-object version history

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend API | FastAPI (Python 3.11), async SQLAlchemy |
| Database | PostgreSQL 15 (+ Alembic migrations) |
| Object Storage | MinIO (local) / AWS S3 (was production) |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS 4 |
| Auth | JWT (python-jose + bcrypt) |
| Email | SMTP via smtplib (with console fallback for dev) |
| Blender Add-on | Python (`bpy`) — single distributable folder |
| Local Dev | Docker Compose |

## Quick Start (Run It Locally)

The easiest way to run the full stack on your own machine.

### Prerequisites
- [Docker](https://www.docker.com/) and Docker Compose

### 1. Configure environment

Create a `.env` file in the project root:

```env
JWT_SECRET=<generate with: python -c "import secrets; print(secrets.token_urlsafe(32))">

# S3 / MinIO (use minioadmin / minioadmin to talk to the bundled MinIO container)
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_ENDPOINT=http://minio:9000
S3_BUCKET=capstonebots
S3_SECURE=false

# SMTP — leave blank and set EMAIL_DEBUG=true to print verification links to the backend console
EMAIL_DEBUG=true
FRONTEND_URL=http://localhost:3000
```

See [`.env.example`](./.env.example) for the full list of variables.

### 2. Build and run

```bash
docker compose up --build
```

### 3. Access

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API docs | http://localhost:8000/docs |
| MinIO console | http://localhost:9001 |

### 4. Stop

```bash
docker compose down
```

## Install the Blender Add-on

1. Grab `export/blender_vcs.zip` (or zip the `blender_vcs/` folder yourself — the ZIP must contain a top-level folder named `blender_vcs/` with `__init__.py` inside).
2. In Blender: **Edit → Preferences → Add-ons → Install from Disk** and pick the ZIP.
3. Enable **BVCS** in the add-ons list.
4. Press **N** in the 3D viewport and switch to the **BVCS** tab.
5. In the add-on preferences, point the backend URL at your local instance (`http://localhost:8000`) and log in with an account you created on the local frontend.

Full step-by-step instructions: [`export/README.md`](./export/README.md).

## Manual Setup (Without Docker)

### Prerequisites
- Python 3.11+
- Node.js 20+
- PostgreSQL running locally
- (Optional) MinIO for storage features

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Database only (via Docker)

```bash
docker compose up -d db
```

## Environment Variables

For local Docker Compose, everything lives in a single root `.env` file and is injected into containers by `docker-compose.yml`. For deployed environments (the original setup ran both apps on DigitalOcean App Platform), set the same variables in your platform's dashboard.

### Backend

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `JWT_SECRET` | **Yes** | — | Secret key for signing JWT tokens |
| `DATABASE_URL` | **Yes** (deploy) | Set in compose | PostgreSQL connection string. Auto-injected by Docker Compose locally; set explicitly in production. |
| `S3_ENDPOINT` | **Yes** | `https://s3.us-east-1.amazonaws.com` | S3-compatible endpoint (`http://minio:9000` for local MinIO) |
| `S3_ACCESS_KEY` | **Yes** | — | S3 access key |
| `S3_SECRET_KEY` | **Yes** | — | S3 secret key |
| `S3_BUCKET` | **Yes** | `blender-vcs-prod` | S3 bucket name (`capstonebots` for local MinIO) |
| `S3_REGION` | No | `us-east-1` | S3 region |
| `S3_SECURE` | No | `true` | Use HTTPS for S3 (`false` for local MinIO) |
| `SMTP_HOST` | No | — | SMTP server (required for live email delivery — original deploy used `smtp-pulse.com`) |
| `SMTP_PORT` | No | `2525` | SMTP port |
| `SMTP_USER` | No | — | SMTP login |
| `SMTP_PASSWORD` | No | — | SMTP password |
| `SMTP_FROM` | No | `SMTP_USER` | From address for outbound mail (e.g. `noreply@yourdomain.com`) |
| `EMAIL_DEBUG` | No | `false` | Print verification / reset links to console instead of sending (local dev only) |
| `FRONTEND_URL` | No | `http://localhost:3000` | Base URL for links embedded in emails. On DigitalOcean App Platform this was bound to the frontend component via `${capstone-deploy-frontend.PUBLIC_URL}` |
| `INVITE_EXPIRY_DAYS` | No | `7` | Days before a project invitation expires |

### Frontend

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NEXT_PUBLIC_BACKEND_URL` | **Yes** | `http://localhost:8000` | Base URL the browser uses to call the backend API. Must be set at build time because Next.js inlines `NEXT_PUBLIC_*` vars into the client bundle. |
| `DATABASE_URL` | No | — | Used during build / SSR if the frontend needs a direct DB read. Not required for the standard hosted setup. |

### Reference: original DigitalOcean App Platform setup

For anyone redeploying this on DigitalOcean App Platform (or a similar PaaS), here's the exact set of env vars the production deploy used. Values are redacted; supply your own.

**Frontend component** (`capstone-deploy-frontend`):

```env
NEXT_PUBLIC_BACKEND_URL=<backend component PUBLIC_URL>
DATABASE_URL=<postgres connection string>
```

**Backend component** (`capstone-deploy-backend`):

```env
DATABASE_URL=<postgres connection string>
JWT_SECRET=<generate with python -c "import secrets; print(secrets.token_urlsafe(32))">
S3_ACCESS_KEY=<s3 access key>
S3_SECRET_KEY=<s3 secret key>
S3_BUCKET=<bucket name>
S3_ENDPOINT=<s3 endpoint URL>
S3_REGION=us-east-1
S3_SECURE=true
SMTP_HOST=smtp-pulse.com
SMTP_PORT=2525
SMTP_USER=<smtp user>
SMTP_PASSWORD=<smtp password>
SMTP_FROM=noreply@yourdomain.com
FRONTEND_URL=${capstone-deploy-frontend.PUBLIC_URL}
```

The `${capstone-deploy-frontend.PUBLIC_URL}` syntax is DigitalOcean's component-binding feature — it auto-substitutes the frontend component's public URL at deploy time, so the backend always builds correct email links without hard-coding a domain.

## Testing

Backend uses `pytest`; frontend uses `Jest` + React Testing Library.

```bash
# Run everything (from repo root, requires backend/.venv to exist)
./tests/run_all_tests.sh

# Backend only
cd backend && .venv/bin/python -m pytest tests/ -v --ignore=tests/test_storage.py --ignore=tests/test_object_storage.py

# Frontend only
cd frontend && npm test -- --watchAll=false
```

Storage integration tests (`tests/test_object_storage.py`) require a live S3 / MinIO instance and are excluded from the default run.

## Project Structure

```
CapstoneBots/
├── backend/                 # FastAPI backend
│   ├── main.py              # App entry, CORS, lifespan
│   ├── models.py            # SQLAlchemy models
│   ├── schemas.py           # Pydantic schemas
│   ├── database.py          # Async DB engine + session
│   ├── routers/             # users.py, projects.py, storage.py
│   ├── utils/               # auth, email, permissions, s3 cleanup
│   ├── storage/             # S3 / MinIO service layer
│   ├── migrations/          # Alembic migrations
│   └── tests/               # pytest suite
├── frontend/                # Next.js dashboard
│   └── src/
│       ├── app/             # Pages (login, signup, projects, settings, ...)
│       ├── components/      # Shared React components
│       └── lib/             # API client functions
├── blender_vcs/             # Blender add-on source
├── export/                  # Pre-built add-on ZIP + install guide
├── tests/run_all_tests.sh   # One-shot test runner
├── docker-compose.yml       # Full local stack (db + minio + api + web)
└── .env.example             # Environment variable template
```

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture Diagrams](./ARCHITECTURE_DIAGRAMS.md) | Component relationships and data flow |
| [Backend README](./backend/README.md) | Backend setup, API overview, env vars |
| [Frontend README](./frontend/README.md) | Frontend setup and page structure |
| [Storage Integration Guide](./backend/INTEGRATION_GUIDE.md) | How storage ties into the commit workflow |
| [Storage Quick Reference](./backend/storage/QUICK_REFERENCE.md) | Storage API cheat sheet |
| [Blender Add-on Install](./export/README.md) | Installing the BVCS add-on |
| API Docs (local) | http://localhost:8000/docs (when running locally) |

## Authors

- Aarsh Patel — aarsh@email.sc.edu
- Alex Mesa — mesacora@email.sc.edu
- Paksh Patel — paksh@email.sc.edu
- Joseph Vann — jrvann@email.sc.edu
- Vraj Patel — vtpatel@email.sc.edu

---

**Status**: Hosted service offline since 2026-05-05 — local Docker Compose deploy fully supported.
**Last Updated:** 2026-05-10
