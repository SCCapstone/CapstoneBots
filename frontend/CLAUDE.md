# Frontend — Claude Code Instructions

## Overview

Next.js 16 frontend for the Blender Collab web dashboard. Uses React 19, Tailwind CSS 4, and TypeScript. Communicates with the FastAPI backend via REST API.

## Architecture

```
frontend/
├── src/
│   ├── app/                # Next.js App Router pages
│   │   ├── layout.tsx      # Root layout
│   │   ├── page.tsx        # Landing / home page
│   │   ├── globals.css     # Global styles (Tailwind directives)
│   │   ├── login/          # Login page
│   │   ├── signup/         # Registration page
│   │   ├── verify-email/   # Email verification page
│   │   ├── projects/       # Project dashboard, detail, history views
│   │   ├── settings/       # User settings / account management
│   │   └── invitations/    # Invitation accept/decline
│   ├── components/         # Shared components
│   │   ├── AuthProvider.tsx # JWT auth context (client component)
│   │   ├── Protected.tsx   # Route protection wrapper
│   │   ├── Navbar.tsx      # Navigation bar
│   │   ├── ProjectCard.tsx # Project card component
│   │   ├── CommitItem.tsx  # Commit history item
│   │   ├── FilePreview.tsx # File preview component
│   │   └── LoadingSpinner.tsx
│   └── lib/                # API client layer
│       ├── authApi.ts      # Auth API calls (login, register, verify, reset)
│       └── projectsApi.ts  # Projects API calls (CRUD, commits, members, storage)
├── public/                 # Static assets
├── package.json            # Dependencies
├── tsconfig.json           # TypeScript config
├── next.config.ts          # Next.js config
├── eslint.config.mjs       # ESLint config
└── postcss.config.mjs      # PostCSS (Tailwind)
```

## Development Commands

```bash
npm run dev      # Start dev server (port 3000)
npm run build    # Production build
npm run start    # Start production server
npm run lint     # ESLint
```

## Coding Conventions

### Next.js 16 App Router
- Use the App Router (`src/app/`) — no Pages Router
- Default to Server Components — only add `"use client"` when the component needs browser APIs, hooks, or event handlers
- Use `layout.tsx` for shared layouts, `page.tsx` for route pages
- Use `loading.tsx` and `error.tsx` for route-level loading/error states
- Use Next.js `<Link>` for client-side navigation — never use `<a>` for internal links
- Use `next/image` for optimized images
- Use route groups `(group)` to organize routes without affecting URL structure

### React 19 Patterns
- Use Server Components by default — push `"use client"` to leaf components
- Use `Suspense` boundaries for async data loading
- Use `useActionState` for form handling where appropriate
- Keep state as close to where it's used as possible
- Avoid prop drilling — use context (like `AuthProvider`) for cross-cutting concerns

### TypeScript
- Strict mode is enabled — never use `any` type
- Define interfaces for all API response types in the API client files
- Use `type` for unions/intersections, `interface` for object shapes
- All component props must be typed — no implicit `any`
- Use `as const` for constant arrays/objects

### Tailwind CSS 4
- Use Tailwind utility classes — avoid custom CSS unless absolutely necessary
- Maintain consistent spacing, colors, and typography via Tailwind's design system
- Use `@apply` sparingly — prefer utility classes in JSX
- Responsive design: mobile-first with `sm:`, `md:`, `lg:` breakpoints
- Dark mode: use `dark:` variant if implementing theme support

### API Client Layer (`lib/`)
- All API calls go through `lib/authApi.ts` or `lib/projectsApi.ts`
- Always include JWT token in `Authorization: Bearer <token>` header
- Handle errors consistently — check response status, parse error details
- Use `fetch()` with proper error handling — do not swallow errors
- API base URL from `NEXT_PUBLIC_BACKEND_URL` env var (or `NEXT_PUBLIC_API_BASE_URL` in Docker)

### Component Architecture
- Shared/reusable components in `src/components/`
- Page-specific components co-located with their route in `src/app/`
- `AuthProvider` wraps the app for JWT token management
- `Protected` component guards authenticated routes
- Keep components small and focused — extract when a component exceeds ~150 lines

## Security Rules

1. **No secrets in client code** — only `NEXT_PUBLIC_*` env vars are exposed to the browser. Never use server-side secrets
2. **XSS prevention** — React auto-escapes by default. Never use `dangerouslySetInnerHTML` without sanitization
3. **CSRF** — use `SameSite` cookie attributes. JWT in `Authorization` header is CSRF-safe
4. **Auth token storage** — store JWT in memory (context) or `localStorage`. Clear on logout
5. **Input validation** — validate user input on the client side before sending to API. Server validates too
6. **Sensitive routes** — wrap with `<Protected>` component. Check auth state before rendering

## Testing Guidelines

Testing is not yet set up but should follow these patterns when implemented:

- **Unit tests**: Use Jest + React Testing Library for component testing
- **Integration tests**: Test page-level behavior with mocked API responses
- **E2E tests**: Use Playwright for critical user flows (login → create project → commit)
- **Test file naming**: `*.test.tsx` co-located with components, or in `__tests__/` directory
- **Mock API calls**: Use MSW (Mock Service Worker) for consistent API mocking
- **Key flows to test**: authentication, project CRUD, file upload, invitation flow

## Performance

- Use Next.js automatic code splitting — don't manually split unless needed
- Lazy load heavy components with `dynamic()` from `next/dynamic`
- Use `loading.tsx` for route-level loading states
- Optimize images with `next/image`
- Avoid large client-side bundles — keep `"use client"` components small
- Use `React.memo()` only when profiling shows unnecessary re-renders

## Accessibility

- Use semantic HTML (`<nav>`, `<main>`, `<section>`, `<button>`, etc.)
- All interactive elements must be keyboard accessible
- Add `aria-label` to icon-only buttons
- Use proper heading hierarchy (`h1` → `h2` → `h3`)
- Form inputs must have associated `<label>` elements
- Color contrast must meet WCAG AA standards

## Deployment (Vercel)

- Auto-deploys from GitHub
- Root directory set to `frontend` in Vercel dashboard
- Framework preset: Next.js
- Environment variable: `NEXT_PUBLIC_BACKEND_URL` = Railway backend URL
- Preview deployments for PRs — test before merging
- Production URL: `https://capstone-bots.vercel.app`
