# Blender Collab — Frontend

Next.js web application for the Blender Collab project. Provides the user interface for authentication, project management, collaboration, and file browsing.

## Tech Stack

- **Framework**: Next.js 16 (App Router)
- **UI**: React 19, Tailwind CSS 4
- **Language**: TypeScript
- **Auth**: JWT tokens stored in localStorage via `AuthProvider` context

## Pages

| Route | Description |
|-------|-------------|
| `/` | Landing page |
| `/login` | Log in with email and password |
| `/signup` | Create a new account |
| `/verify-email?token=...` | Email verification (from signup email link) |
| `/login/forgot-password` | Request a password reset email |
| `/login/reset-password?token=...` | Set a new password (from reset email link) |
| `/projects` | Projects dashboard — list, create, manage projects |
| `/projects/[projectId]` | Project detail — commits, branches, files, members |
| `/invitations` | View and respond to project invitations |
| `/settings` | Account settings and account deletion |

## Setup

### Prerequisites

- Node.js 20+
- npm

### Install and run

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### Environment Variables

Create a `.env` file in this directory:

```env
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

When running via Docker Compose, this is set automatically to `http://backend:8000`.

## Project Structure

```
src/
├── app/                          # Next.js App Router pages
│   ├── layout.tsx                # Root layout with AuthProvider
│   ├── page.tsx                  # Landing page
│   ├── globals.css               # Global styles
│   ├── login/
│   │   ├── page.tsx              # Login page
│   │   ├── forgot-password/      # Forgot password page
│   │   └── reset-password/       # Reset password page
│   ├── signup/                   # Signup page
│   ├── verify-email/             # Email verification page
│   ├── projects/
│   │   ├── page.tsx              # Projects dashboard
│   │   └── [projectId]/          # Project detail page
│   ├── invitations/              # Invitations page
│   └── settings/                 # Account settings page
├── components/
│   └── AuthProvider.tsx          # JWT auth context provider
└── lib/
    ├── authApi.ts                # Auth API client (login, signup, verify, reset, etc.)
    └── projectsApi.ts            # Projects API client (CRUD, invitations, files)
```

## Deployment

For production deployment to Vercel, see the [Deployment Guide](../DEPLOYMENT.md).

---

**Last Updated**: February 2026
