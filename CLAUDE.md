# Blender Collab — Claude Code Instructions

## Project Overview

Blender Collab is a web-based Version Control System (VCS) for Blender. It enables teams to collaborate on 3D projects with object-level version management. Individual Blender objects are exported as JSON with mesh data stored in S3, allowing efficient storage, content deduplication, and granular version tracking.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend API | FastAPI (Python 3.11), async |
| Database | PostgreSQL 15 (SQLAlchemy + Alembic) |
| Object Storage | MinIO (local) / AWS S3 (prod) |
| Frontend | Next.js 16, React 19, Tailwind CSS 4, TypeScript |
| Auth | JWT (python-jose + bcrypt) |
| Blender Addon | Python (bpy), single-file `blender_vcs/__init__.py` |
| Deploy | Railway (backend) + Vercel (frontend) |
| Local Dev | Docker Compose |

## Project Structure

```
CapstoneBots/
├── backend/           # FastAPI backend (see backend/CLAUDE.md)
│   ├── main.py        # App entry point, CORS, lifespan
│   ├── models.py      # SQLAlchemy ORM models
│   ├── schemas.py     # Pydantic request/response schemas
│   ├── database.py    # Async DB connection + session management
│   ├── routers/       # API routes: users.py, projects.py, storage.py
│   ├── utils/         # auth.py, email.py, permissions.py, s3_cleanup.py
│   ├── storage/       # S3/MinIO service layer (storage_service.py, minio_client.py)
│   ├── migrations/    # Alembic database migrations
│   └── tests/         # pytest test suite
├── frontend/          # Next.js frontend (see frontend/CLAUDE.md)
│   └── src/
│       ├── app/       # Pages: login, signup, projects, settings, invitations
│       ├── components/# AuthProvider, Navbar, ProjectCard, etc.
│       └── lib/       # API client: authApi.ts, projectsApi.ts
├── blender_vcs/       # Blender addon source (see blender_vcs/CLAUDE.md)
│   └── __init__.py    # Single-file addon (~1800 lines)
├── export/            # Packaged addon ZIP for distribution
└── docker-compose.yml # Full local stack (db, backend, frontend, minio)
```

## Key Commands

```bash
# Local development (full stack)
docker compose up --build
docker compose down

# Backend only
cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Frontend only
cd frontend && npm run dev

# Run backend tests
cd backend && pytest -v

# Database only
docker compose up -d db

# Alembic migrations
cd backend && alembic upgrade head
cd backend && alembic revision --autogenerate -m "description"
```

## API Routes

- `POST /api/auth/login` — JWT login
- `POST /api/auth/register` — register + email verification
- `GET  /api/auth/me` — current user
- `GET  /api/projects` — list projects
- `POST /api/projects` — create project
- `GET  /api/projects/{id}/commits` — commit history
- `POST /api/projects/{id}/commits` — create commit
- `GET  /api/projects/{id}/members` — list members
- `POST /api/projects/{id}/invite` — invite collaborator
- `/api/projects/{id}/storage/*` — file upload/download/stats
- `GET  /api/health` — health check

## Environment Variables

Required: `JWT_SECRET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`
See root `README.md` for the full environment variable reference.

## Deployment

- **Backend**: Railway (auto-deploys from GitHub, Postgres plugin, env vars in dashboard)
- **Frontend**: Vercel (root dir = `frontend`, `NEXT_PUBLIC_BACKEND_URL` env var)
- **CORS origins**: defined in `backend/main.py` — must include production domains
- **Production URLs**: `https://capstone-bots.vercel.app`, `https://capstonebots-production.up.railway.app`

## Cross-Cutting Rules

1. **Never commit secrets** — `.env` files are gitignored. Never hardcode API keys, JWT secrets, or S3 credentials.
2. **Type safety** — use Pydantic models for all API request/response bodies in backend. Use TypeScript strict mode in frontend.
3. **Async everywhere** — backend uses async SQLAlchemy sessions and async route handlers. Do not use synchronous DB calls.
4. **Error handling** — use FastAPI `HTTPException` with appropriate status codes. Return meaningful error messages.
5. **S3 cleanup** — when deleting projects or accounts, always clean up associated S3 objects. See `backend/utils/s3_cleanup.py`.
6. **Migrations** — any model changes require an Alembic migration. Never modify the DB schema without one.
7. **Test coverage** — write tests for new backend endpoints using pytest + httpx AsyncClient.
8. **Git workflow** — write clear commit messages. Keep PRs focused on a single concern.
