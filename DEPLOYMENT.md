# Deployment Guide

## Local Development (Docker Compose)

The recommended way to run all services locally.

### Services

| Service | Container | Port |
|---------|-----------|------|
| PostgreSQL 15 | `capstonebots-db` | 5432 |
| FastAPI Backend | `capstonebots-backend` | 8000 |
| Next.js Frontend | `capstonebots-frontend` | 3000 |
| MinIO (S3) | `minio` | 9000 (API), 9001 (Console) |

### Setup

1. Create a `.env` file in the project root with the required variables (see [README.md](./README.md#environment-variables)).

2. Build and start:
   ```bash
   docker compose up --build
   ```

3. Access:
   - Frontend: http://localhost:3000
   - Backend API Docs: http://localhost:8000/docs
   - MinIO Console: http://localhost:9001 (login: `minioadmin` / `minioadmin`)

4. Stop:
   ```bash
   docker compose down
   ```

> **Note**: When SMTP is not configured, email verification and password reset links are printed to the backend console logs instead of being sent via email.

---

## Production Deployment

### Railway (Backend + Database)

#### Environment Variables

Set these in the Railway dashboard under **Variables**:

| Variable | Notes |
|----------|-------|
| `JWT_SECRET` | **Required.** Generate with: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `DATABASE_URL` | Auto-provided by Railway Postgres plugin |
| `S3_ENDPOINT` | Your S3 endpoint (e.g., `https://s3.us-east-1.amazonaws.com`) |
| `S3_ACCESS_KEY` | S3 access key |
| `S3_SECRET_KEY` | S3 secret key |
| `S3_SECURE` | `true` for HTTPS |
| `S3_BUCKET` | `blender-vcs-prod` |
| `SMTP_HOST` | SMTP server (e.g., `smtp-pulse.com`) |
| `SMTP_PORT` | SMTP port (e.g., `2525`) |
| `SMTP_USER` | SMTP login email |
| `SMTP_PASSWORD` | SMTP password |
| `SMTP_FROM` | From address for emails |
| `FRONTEND_URL` | Your Vercel frontend URL (e.g., `https://your-app.vercel.app`) |
| `INVITE_EXPIRY_DAYS` | Days before invitations expire (default: `7`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT lifetime in minutes (default: `60`) |
| `ENVIRONMENT` | Set to `production` |

#### Setup Steps

1. Create a new project in Railway
2. Add a Postgres database (Railway auto-injects `DATABASE_URL`)
3. Deploy the backend from GitHub
4. Set all environment variables listed above
5. Verify the health endpoint: `https://your-app.railway.app/api/health`

### Vercel (Frontend)

#### Environment Variables

| Variable | Value |
|----------|-------|
| `NEXT_PUBLIC_BACKEND_URL` | Your Railway backend URL (e.g., `https://your-app.railway.app`) |

#### Setup Steps

1. Import the project from GitHub
2. Set framework preset to **Next.js**
3. Set root directory to `frontend`
4. Add the environment variable above
5. Deploy

---

## Security Checklist

- [ ] `JWT_SECRET` is set to a strong random value (not a default)
- [ ] CORS origins in `backend/main.py` are updated for your production domain
- [ ] HTTPS is enabled (Railway and Vercel provide this by default)
- [ ] Database connection uses SSL (Railway Postgres includes this)
- [ ] Token expiration is reasonable (60–120 minutes)
- [ ] SMTP credentials are set so email verification and password reset work
- [ ] S3 credentials have minimal required permissions

## Post-Deployment Verification

1. `curl https://your-backend.railway.app/api/health` — health check
2. Register a new user — verify email verification flow works
3. Log in — verify JWT token is issued
4. Create a project and invite a collaborator — verify invitation email
5. Test forgot/reset password flow
6. Check Railway logs for errors
7. Verify CORS from the Vercel frontend

## Common Issues

| Issue | Solution |
|-------|----------|
| `JWT_SECRET environment variable is not set` | Set `JWT_SECRET` in Railway environment variables |
| CORS errors from frontend | Add your Vercel domain to `allow_origins` in `backend/main.py` |
| Database connection errors | Verify `DATABASE_URL` is set and Postgres plugin is active |
| `Invalid or expired token` | Ensure `JWT_SECRET` is consistent across instances; check token expiry |
| Email not sending | Verify `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` are correct |
| Verification link goes to wrong URL | Set `FRONTEND_URL` to your production frontend URL |

## Rollback

1. **Railway**: Revert to a previous deployment from the dashboard
2. **Vercel**: Revert to a previous deployment or redeploy from Git
3. Check that environment variables haven't changed
4. Review recent commits for breaking changes

---

**Last Updated**: February 2026
