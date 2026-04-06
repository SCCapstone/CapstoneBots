# Blender Collab — Backend

FastAPI backend for the Blender Collab project. Provides REST API endpoints for authentication, project management, collaboration, and S3-based file storage.

## Features

- **Authentication**: JWT-based login, registration, email verification, password reset
- **Projects**: CRUD operations, branching, commits, version history
- **Collaboration**: Invite members by email, role-based permissions (owner / editor / viewer)
- **Storage**: S3/MinIO integration for Blender object uploads, downloads, and deduplication
- **Email**: SMTP support for verification and password reset (falls back to console output when SMTP is not configured)

## Setup

### Prerequisites

- Python 3.9+
- PostgreSQL database
- S3-compatible storage (MinIO or AWS S3) for file operations

### Installation

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file in this directory (or set via Docker Compose):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | **Yes** | — | PostgreSQL async connection string |
| `JWT_SECRET` | **Yes** | — | Secret for signing JWT tokens |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `60` | JWT token lifetime |
| `S3_ENDPOINT` | No | `https://s3.us-east-1.amazonaws.com` | S3-compatible endpoint (use `http://minio:9000` for local MinIO) |
| `S3_ACCESS_KEY` | **Yes** | — | S3 access key |
| `S3_SECRET_KEY` | **Yes** | — | S3 secret key |
| `S3_SECURE` | No | `true` | Use HTTPS for S3 (`false` for local MinIO) |
| `S3_BUCKET` | No | `blender-vcs-prod` | S3 bucket name (`capstonebots` for local MinIO) |
| `S3_REGION` | No | `us-east-1` | S3 region |
| `SMTP_HOST` | No | — | SMTP server (required for email delivery; see `EMAIL_DEBUG`) |
| `SMTP_PORT` | No | `587` | SMTP port |
| `SMTP_USER` | No | — | SMTP login |
| `SMTP_PASSWORD` | No | — | SMTP password |
| `SMTP_FROM` | No | `SMTP_USER` | From address for outgoing emails |
| `EMAIL_DEBUG` | No | `false` | Print verification/reset links to console when SMTP is not configured (local dev only) |
| `FRONTEND_URL` | No | `http://localhost:3000` | Base URL used in email links |
| `INVITE_EXPIRY_DAYS` | No | `7` | Days before project invitations expire |

### Running the Server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API documentation: [http://localhost:8000/docs](http://localhost:8000/docs)

## API Overview

### Auth (`/api/auth`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/register` | Create a new account |
| POST | `/login` | Authenticate and receive JWT |
| GET | `/me` | Get current user info |
| POST | `/verify-email` | Verify email with token |
| POST | `/resend-verification` | Resend verification email |
| POST | `/forgot-password` | Request password reset email |
| POST | `/reset-password` | Reset password with token |
| DELETE | `/account` | Delete account (with password confirmation) |

### Projects (`/api/projects`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | List user's projects |
| POST | `/` | Create a new project |
| GET | `/{id}` | Get project details |
| PUT | `/{id}` | Update project |
| DELETE | `/{id}` | Delete project |
| POST | `/{id}/commits` | Create a commit |
| GET | `/{id}/commits` | List commits |
| POST | `/{id}/branches` | Create a branch |
| GET | `/{id}/branches` | List branches |
| POST | `/{id}/members` | Invite a collaborator |
| GET | `/{id}/members` | List project members |

### Storage (`/api/projects`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/{id}/objects/upload` | Upload Blender object |
| GET | `/{id}/commits/{cid}/download` | Download full commit |
| GET | `/{id}/versions` | Version history |
| GET | `/{id}/storage-stats` | Storage usage stats |

## Database Migrations

Migrations live in `migrations/versions/` and are applied automatically on startup. To add a new migration, create a numbered file following the existing pattern (e.g., `006_your_migration.py`).

Current migrations:
1. `001_initial.py` — Base tables
2. `002_nullable_author_for_account_deletion.py`
3. `003_add_invitations_and_roles.py`
4. `004_add_password_changed_at.py`
5. `005_add_email_verification.py`

## Testing

Tests use **pytest** and live in `tests/`.

```bash
source .venv/bin/activate
pip install -r requirements.txt

# Run all tests (integration tests auto-skip when DB is not available)
pytest tests/ -v --ignore=tests/test_storage.py

# Run only unit tests (no external services needed)
pytest tests/test_unit_auth.py tests/test_unit_models.py tests/test_unit_schemas.py tests/test_unit_schemas_extended.py tests/test_unit_storage_utils.py -v
```

**Unit tests** (no database or services required):
- `tests/test_unit_auth.py` — Password hashing, JWT token creation/validation (28 tests)
- `tests/test_unit_models.py` — Role hierarchy, invitation status, member role parsing (14 tests)
- `tests/test_unit_schemas.py` — Core Pydantic schema validation (4 tests)
- `tests/test_unit_schemas_extended.py` — Extended schema validation with edge cases (36 tests)
- `tests/test_unit_storage_utils.py` — Content hashing, path parsing, file size formatting, JSON validation (40 tests)

**Behavioral / integration tests** (require PostgreSQL — auto-skip when unavailable):
- `tests/test_auth.py` — Authentication flows (4 tests)
- `tests/test_behavior_api.py` — API endpoint flows: auth, projects, health check (23 tests)
- `tests/test_behavior_projects_auth.py` — Project access control and collaboration (15 tests)
- `tests/test_delete_account.py` — Account deletion with cleanup (3 tests)
- `tests/test_storage.py` — S3/MinIO storage operations (requires MinIO)

## Related Documentation

- [Storage & Versioning](../STORAGE.md) — Complete storage system guide
- [Integration Guide](./INTEGRATION_GUIDE.md) — Adding storage to commit workflows
- [Storage Quick Reference](./storage/QUICK_REFERENCE.md) — API cheat sheet
- [Architecture Diagrams](../ARCHITECTURE_DIAGRAMS.md) — Visual data flows

---

**Last Updated**: February 2026
