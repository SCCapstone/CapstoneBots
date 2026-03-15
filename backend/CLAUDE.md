# Backend — Claude Code Instructions

## Overview

FastAPI backend serving the Blender Collab REST API. Uses async PostgreSQL (SQLAlchemy + asyncpg), JWT authentication, and S3-compatible object storage (MinIO locally, AWS S3 in production).

## Architecture

```
backend/
├── main.py              # FastAPI app, CORS, lifespan (init_db/close_db)
├── models.py            # SQLAlchemy ORM models (User, Project, Branch, Commit, etc.)
├── schemas.py           # Pydantic v2 schemas for request/response validation
├── database.py          # Async engine, session factory, init_db(), close_db()
├── routers/
│   ├── users.py         # Auth: login, register, verify-email, forgot/reset-password, /me
│   ├── projects.py      # Projects, branches, commits, members, invitations, locking
│   └── storage.py       # File upload/download, storage stats, S3 operations
├── utils/
│   ├── auth.py          # JWT creation/verification, password hashing (bcrypt), get_current_user
│   ├── email.py         # SMTP email sending, EMAIL_DEBUG console fallback
│   ├── permissions.py   # Role-based access control (owner/editor/viewer)
│   ├── project_utils.py # Project helper functions
│   └── s3_cleanup.py    # S3 object cleanup on project/account deletion
├── storage/
│   ├── storage_service.py  # High-level S3 operations (upload, download, list, delete)
│   ├── storage_utils.py    # SHA-256 hashing, path helpers
│   └── examples.py         # Usage examples
├── migrations/          # Alembic migrations
└── tests/               # pytest test suite
```

## Development Commands

```bash
# Run locally
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Run tests
pytest -v
pytest tests/test_auth.py -v          # specific test file
pytest -k "test_login" -v             # specific test

# Migrations
alembic upgrade head
alembic revision --autogenerate -m "description"
alembic downgrade -1

# Type checking (if added)
mypy . --ignore-missing-imports
```

## Coding Conventions

### FastAPI Patterns
- All route handlers MUST be `async def`
- Use dependency injection for auth: `current_user: User = Depends(get_current_user)`
- Group routes by domain in `routers/` — do not add routes to `main.py`
- Use `APIRouter` with appropriate prefix and tags
- Return Pydantic response models with explicit status codes
- Use `status_code=` parameter on route decorators for creation endpoints (201)

### Database (SQLAlchemy + Alembic)
- Always use `async with get_db_session() as session:` — never create sessions manually
- Use `session.execute(select(...))` with SQLAlchemy 2.0 style queries — no legacy `session.query()`
- Every model change requires an Alembic migration — never modify tables directly
- Use `server_default` for database-level defaults, not Python-side defaults
- Always `await session.commit()` explicitly after mutations
- Use `selectinload()` / `joinedload()` to avoid N+1 queries

### Pydantic Schemas
- Use Pydantic v2 `model_config = ConfigDict(from_attributes=True)`
- Separate `Create`, `Update`, and `Response` schemas (e.g., `ProjectCreate`, `ProjectResponse`)
- Use `Field()` with descriptions for API documentation
- Validate emails with `EmailStr`, constrain strings with `min_length`/`max_length`

### Error Handling
- Raise `HTTPException` with specific status codes — never return raw error dicts
- 400 for validation errors, 401 for auth failures, 403 for permission denied, 404 for not found, 409 for conflicts
- Include actionable error messages in `detail`
- Log errors with `logger.error()` before raising

## Security Rules

1. **Authentication**: All protected endpoints use `Depends(get_current_user)` which validates the JWT Bearer token
2. **Password hashing**: Always use `passlib[bcrypt]` via `utils/auth.py` — never store plaintext passwords
3. **JWT tokens**: Signed with `JWT_SECRET` env var. Include `sub` (user_id) and `exp` claims. Default expiry: 60 minutes
4. **Input validation**: Pydantic schemas validate all request bodies automatically. Add extra validation for path/query params
5. **SQL injection**: use parameterized queries via SQLAlchemy — never use f-strings in SQL
6. **CORS**: Origins whitelist in `main.py`. Add new production domains explicitly — never use `allow_origins=["*"]` in production
7. **S3 credentials**: Read from env vars only — never hardcode. Use minimal IAM permissions
8. **Rate limiting**: Consider adding rate limiting for auth endpoints (login, register, password reset)
9. **Email verification**: Required before account is active. Tokens are single-use
10. **Secrets in responses**: Never return password hashes, JWT secrets, or S3 keys in API responses

## Testing Rules

- Test files go in `tests/` directory, named `test_*.py`
- Use `pytest` + `httpx.AsyncClient` for async API testing
- Use test fixtures for database setup/teardown — tests must not depend on each other
- Mock external services (S3, SMTP) in unit tests
- Test both success and error paths for every endpoint
- Test permission boundaries: ensure viewers can't edit, non-members can't access
- Integration tests that need MinIO should be skippable with `@pytest.mark.skipif`

## Scalability Considerations

- Database connection pooling is configured in `database.py` — tune `pool_size` and `max_overflow` for production
- S3 operations should be non-blocking — use `boto3` in thread pool executor for CPU-bound operations
- Content deduplication via SHA-256 reduces storage costs — always hash before uploading
- Paginate list endpoints that could return many results (projects, commits, members)
- Use database indexes on frequently queried columns (user_id, project_id, email)

## Deployment (Railway)

- Deployed via `Procfile`: `web: uvicorn main:app --host 0.0.0.0 --port $PORT`
- `DATABASE_URL` is auto-injected by Railway's Postgres plugin
- Health check: `GET /api/health` returns `{"status": "ok"}`
- All env vars set in Railway dashboard — see `DEPLOYMENT.md`
- Root path is `/capstone-deploy-backend` (set in `main.py`)
