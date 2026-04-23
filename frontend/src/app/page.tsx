"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";

type Theme = "light" | "dark";

export default function Home() {
  const [theme, setTheme] = useState<Theme>("dark");
  const [mounted, setMounted] = useState(false);
  const { token, hydrated } = useAuth();

  useEffect(() => {
    const isDark = document.documentElement.classList.contains("dark");
    setTheme(isDark ? "dark" : "light");
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;
    document.documentElement.classList.toggle("dark", theme === "dark");
    try {
      localStorage.setItem("theme", theme);
    } catch {}
  }, [theme, mounted]);

  const loggedIn = hydrated && !!token;

  return (
    <main className="min-h-screen bg-white text-slate-900 transition-colors dark:bg-slate-950 dark:text-slate-100">
      <NavBar theme={theme} setTheme={setTheme} loggedIn={loggedIn} />
      <Hero loggedIn={loggedIn} />
      <Features />
      <HowItWorks />
      <DashboardSection />
      <DemoSection />
      <TeamSection />
      <Footer />
    </main>
  );
}

function NavBar({
  theme,
  setTheme,
  loggedIn,
}: {
  theme: Theme;
  setTheme: (t: Theme) => void;
  loggedIn: boolean;
}) {
  return (
    <header className="sticky top-0 z-40 border-b border-slate-200/70 bg-white/80 backdrop-blur-md dark:border-slate-800/70 dark:bg-slate-950/80">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
        <Link href="/" className="flex items-center gap-2">
          <LogoMark />
          <span className="font-semibold tracking-tight">Blender Collab</span>
        </Link>

        <nav className="hidden items-center gap-7 text-sm text-slate-600 md:flex dark:text-slate-300">
          <a href="#features" className="hover:text-sky-600 dark:hover:text-sky-400">
            Features
          </a>
          <a href="#how" className="hover:text-sky-600 dark:hover:text-sky-400">
            How it works
          </a>
          <a href="#demo" className="hover:text-sky-600 dark:hover:text-sky-400">
            Demo
          </a>
          <a href="#team" className="hover:text-sky-600 dark:hover:text-sky-400">
            Team
          </a>
        </nav>

        <div className="flex items-center gap-2">
          <ThemeToggle theme={theme} setTheme={setTheme} />
          {loggedIn ? (
            <Link
              href="/projects"
              className="rounded-lg bg-sky-600 px-3.5 py-1.5 text-sm font-semibold text-white shadow-sm transition hover:bg-sky-500"
            >
              Open app
            </Link>
          ) : (
            <>
              <Link
                href="/login"
                className="hidden rounded-lg px-3 py-1.5 text-sm text-slate-700 transition hover:bg-slate-100 sm:inline-block dark:text-slate-200 dark:hover:bg-slate-900"
              >
                Log in
              </Link>
              <Link
                href="/signup"
                className="rounded-lg bg-sky-600 px-3.5 py-1.5 text-sm font-semibold text-white shadow-sm transition hover:bg-sky-500"
              >
                Sign up
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

function ThemeToggle({
  theme,
  setTheme,
}: {
  theme: Theme;
  setTheme: (t: Theme) => void;
}) {
  const isDark = theme === "dark";
  return (
    <button
      type="button"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      className="rounded-lg border border-slate-200 p-1.5 text-slate-700 transition hover:border-sky-500 hover:text-sky-600 dark:border-slate-700 dark:text-slate-300 dark:hover:border-sky-400 dark:hover:text-sky-300"
    >
      {isDark ? <SunIcon /> : <MoonIcon />}
    </button>
  );
}

function Hero({ loggedIn }: { loggedIn: boolean }) {
  return (
    <section className="relative overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 -top-40 flex justify-center"
      >
        <div className="h-[520px] w-[1100px] rounded-full bg-gradient-to-br from-sky-300/50 via-cyan-200/30 to-indigo-300/40 blur-3xl dark:from-sky-500/20 dark:via-cyan-500/10 dark:to-indigo-500/20" />
      </div>

      <div className="relative mx-auto max-w-6xl px-4 pb-8 pt-20 text-center sm:px-6 sm:pt-28">
        <span className="inline-flex items-center gap-2 rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-medium text-sky-700 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-300">
          <SparkleIcon />
          Built for 3D teams that ship together
        </span>

        <h1 className="mx-auto mt-6 max-w-3xl text-4xl font-bold tracking-tight sm:text-5xl md:text-6xl">
          Version control your{" "}
          <span className="bg-gradient-to-r from-sky-500 to-indigo-500 bg-clip-text text-transparent">
            Blender
          </span>{" "}
          scenes.
        </h1>

        <p className="mx-auto mt-6 max-w-2xl text-base text-slate-600 dark:text-slate-300 sm:text-lg">
          Blender Collab gives your team Git-style workflows inside Blender —
          object-level commits, deduplicated mesh storage, and branches for
          experiments. No more <code className="rounded bg-slate-100 px-1 py-0.5 text-[0.85em] dark:bg-slate-800">scene_FINAL_v3_really.blend</code> chaos.
        </p>

        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link
            href={loggedIn ? "/projects" : "/signup"}
            className="inline-flex items-center gap-2 rounded-lg bg-sky-600 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-sky-600/20 transition hover:bg-sky-500"
          >
            {loggedIn ? "Open your dashboard" : "Get started — it's free"}
            <ArrowIcon />
          </Link>
          <a
            href="#demo"
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white/60 px-5 py-2.5 text-sm font-semibold text-slate-800 backdrop-blur transition hover:border-sky-500 hover:text-sky-700 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-100 dark:hover:border-sky-400 dark:hover:text-sky-300"
          >
            <PlayIcon />
            Watch 2-minute demo
          </a>
        </div>
        <DashboardMockup />
      </div>
    </section>
  );
}

const MOCK_PROJECTS = [
  {
    name: "Cyberpunk Street Scene",
    description:
      "Main environment for Act 2. 14 shared meshes across 4 collections, shared with 6 collaborators.",
    updated: "4/22/2026, 3:14:22 PM",
  },
  {
    name: "Character Rigs — Hero Cast",
    description:
      "Production rigs for Nia, Ryo, and Kade. Locked meshes, live armatures.",
    updated: "4/21/2026, 10:02:08 AM",
  },
  {
    name: "VFX Simulation Library",
    description:
      "Reusable procedural smoke and fire sims. Ships with preset nodes.",
    updated: "4/19/2026, 8:41:56 PM",
  },
  {
    name: "Product Turntables Q2",
    description:
      "Packshot turntables for the Q2 launch campaign — 12 SKUs.",
    updated: "4/15/2026, 9:30:15 AM",
  },
];

function DashboardMockup() {
  return (
    <div className="mt-14 sm:mt-20">
      <div className="mx-auto max-w-5xl overflow-hidden rounded-2xl border border-slate-200 bg-slate-900 shadow-2xl shadow-sky-500/10 ring-1 ring-black/5 dark:border-slate-800 dark:shadow-sky-500/5">
        <div className="flex items-center gap-2 border-b border-slate-800 bg-slate-900 px-4 py-2.5">
          <div className="flex gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-red-500/70" />
            <span className="h-2.5 w-2.5 rounded-full bg-yellow-500/70" />
            <span className="h-2.5 w-2.5 rounded-full bg-green-500/70" />
          </div>
          <div className="ml-3 flex-1 truncate rounded-md bg-slate-800 px-3 py-1 text-[11px] text-slate-400">
            blendercollab.pakshpatel.tech/projects
          </div>
        </div>

        <div className="bg-[#0f172a] px-6 py-8 text-left">
          <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-white">Projects</h2>
              <p className="mt-1 text-[11px] text-slate-400">
                Select a project to view its commits and object history.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-lg bg-sky-600 px-2.5 py-1 text-[10px] font-semibold text-white">
                + New Project
              </span>
              <span className="relative rounded-lg border border-slate-700 px-2.5 py-1 text-[10px] text-slate-300">
                Invitations
                <span className="absolute -right-1.5 -top-1.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-sky-500 text-[8px] font-bold text-white">
                  2
                </span>
              </span>
              <span className="rounded-lg border border-slate-700 px-2.5 py-1 text-[10px] text-slate-300">
                Settings
              </span>
              <span className="rounded-lg border border-slate-700 px-2.5 py-1 text-[10px] text-slate-300">
                Log out
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {MOCK_PROJECTS.map((p) => (
              <div
                key={p.name}
                className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 transition hover:border-sky-500/70"
              >
                <h3 className="text-sm font-semibold text-slate-50">
                  {p.name}
                </h3>
                <p className="mt-2 line-clamp-2 text-xs text-slate-400">
                  {p.description}
                </p>
                <p className="mt-3 text-[10px] text-slate-500">
                  Updated: {p.updated}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

const FEATURES = [
  {
    title: "Object-level versioning",
    body: "Commit individual Blender objects — not the entire .blend. Track history on the mesh, rig, or material that actually changed.",
    icon: <BranchIcon />,
  },
  {
    title: "Content-addressed mesh storage",
    body: "Mesh data is hashed and stored in S3. Identical geometry is stored once, no matter how many projects reference it.",
    icon: <CubeIcon />,
  },
  {
    title: "Native Blender add-on",
    body: "Commit, pull, and resolve right from Blender's sidebar. The add-on speaks directly to your project's collaboration server.",
    icon: <PuzzleIcon />,
  },
  {
    title: "Project-scoped invitations",
    body: "Invite collaborators by email. Role-based access per project. Ownership transfer handles the awkward handoff moments.",
    icon: <UsersIcon />,
  },
  {
    title: "Branches for experiments",
    body: "Spin up a branch, try the wild lighting idea, merge or toss it. Main stays clean while the team keeps exploring.",
    icon: <SplitIcon />,
  },
  {
    title: "Everything in the browser",
    body: "Browse commits, diff objects, and review contributions from any device — no Blender install required to audit work.",
    icon: <GlobeIcon />,
  },
];

function Features() {
  return (
    <section id="features" className="mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-28">
      <SectionHeader
        eyebrow="Features"
        title="The collaboration layer Blender never shipped with"
        subtitle="Purpose-built for 3D pipelines — not a repurposed text diffing tool."
      />

      <div className="mt-14 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map((f) => (
          <div
            key={f.title}
            className="group rounded-xl border border-slate-200 bg-white p-6 transition hover:-translate-y-0.5 hover:border-sky-400 hover:shadow-lg dark:border-slate-800 dark:bg-slate-900/50 dark:hover:border-sky-500"
          >
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-sky-100 text-sky-600 transition group-hover:bg-sky-500 group-hover:text-white dark:bg-sky-500/10 dark:text-sky-400">
              {f.icon}
            </div>
            <h3 className="mt-4 text-base font-semibold">{f.title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-400">
              {f.body}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

const STEPS = [
  {
    step: "01",
    title: "Install the Blender add-on",
    body: "Grab the BVCS add-on ZIP, drop it into Blender's preferences, and sign in. One-time setup per machine.",
  },
  {
    step: "02",
    title: "Commit from Blender",
    body: "Open the sidebar, pick the objects you changed, write a message, and commit. Mesh data is uploaded to S3, metadata to the API.",
  },
  {
    step: "03",
    title: "Collaborate in the dashboard",
    body: "Invite teammates, review commit history, branch for experiments, and merge back when it's ready.",
  },
];

function HowItWorks() {
  return (
    <section
      id="how"
      className="border-y border-slate-200 bg-slate-50 py-20 sm:py-28 dark:border-slate-800/80 dark:bg-slate-900/40"
    >
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <SectionHeader
          eyebrow="How it works"
          title="Three steps from chaos to a versioned pipeline"
          subtitle="If you've used Git before, you already know how this feels."
        />

        <ol className="mt-14 grid grid-cols-1 gap-6 md:grid-cols-3">
          {STEPS.map((s) => (
            <li
              key={s.step}
              className="relative rounded-xl border border-slate-200 bg-white p-6 dark:border-slate-800 dark:bg-slate-950/60"
            >
              <span className="text-xs font-mono font-semibold text-sky-600 dark:text-sky-400">
                STEP {s.step}
              </span>
              <h3 className="mt-2 text-lg font-semibold">{s.title}</h3>
              <p className="mt-3 text-sm leading-relaxed text-slate-600 dark:text-slate-400">
                {s.body}
              </p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function DashboardSection() {
  return (
    <section className="mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-28">
      <div className="grid items-center gap-10 lg:grid-cols-2">
        <div>
          <span className="text-xs font-mono font-semibold uppercase tracking-wider text-sky-600 dark:text-sky-400">
            The dashboard
          </span>
          <h2 className="mt-3 text-3xl font-bold tracking-tight sm:text-4xl">
            Everything your team&apos;s working on, in one place
          </h2>
          <p className="mt-4 text-slate-600 dark:text-slate-300">
            A clean home for every project. See who changed what, jump into
            branches, manage invitations — without digging through a shared
            drive at 2 AM.
          </p>
          <ul className="mt-6 space-y-3 text-sm">
            {[
              "Per-project commit history with object-level diffs",
              "Branch selector with one-click switching",
              "Pending invitations surface to project owners",
              "File previews without needing Blender open",
            ].map((t) => (
              <li key={t} className="flex items-start gap-2">
                <CheckIcon />
                <span className="text-slate-700 dark:text-slate-300">{t}</span>
              </li>
            ))}
          </ul>
          <Link
            href="/signup"
            className="mt-8 inline-flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-sky-500"
          >
            Try it free <ArrowIcon />
          </Link>
        </div>

        <div className="overflow-hidden rounded-xl border border-slate-200 bg-slate-900 shadow-xl dark:border-slate-800">
          <div className="flex items-center gap-2 border-b border-slate-800 bg-slate-900 px-3 py-2">
            <div className="flex gap-1.5">
              <span className="h-2 w-2 rounded-full bg-red-500/70" />
              <span className="h-2 w-2 rounded-full bg-yellow-500/70" />
              <span className="h-2 w-2 rounded-full bg-green-500/70" />
            </div>
            <div className="ml-2 text-[10px] text-slate-500">
              Cyberpunk Street Scene — commits
            </div>
          </div>
          <div className="space-y-2 bg-[#0f172a] p-4">
            {[
              {
                hash: "a4f2c91",
                msg: "Retopo the hero building facade",
                who: "Aarsh",
                when: "2h ago",
              },
              {
                hash: "9b31e05",
                msg: "Fix normals on neon sign geometry",
                who: "Paksh",
                when: "6h ago",
              },
              {
                hash: "1e82a70",
                msg: "Swap rain shader to volumetric v3",
                who: "Alex",
                when: "yesterday",
              },
              {
                hash: "c0a7d14",
                msg: "Add detail pass to side-alley meshes",
                who: "Joseph",
                when: "2 days ago",
              },
            ].map((c) => (
              <div
                key={c.hash}
                className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-sky-400">
                      {c.hash}
                    </span>
                    <span className="truncate text-xs text-slate-200">
                      {c.msg}
                    </span>
                  </div>
                </div>
                <div className="ml-3 shrink-0 text-[10px] text-slate-500">
                  {c.who} · {c.when}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function DemoSection() {
  return (
    <section
      id="demo"
      className="border-y border-slate-200 bg-slate-50 py-20 sm:py-28 dark:border-slate-800/80 dark:bg-slate-900/40"
    >
      <div className="mx-auto max-w-5xl px-4 sm:px-6">
        <SectionHeader
          eyebrow="Demo"
          title="See it in action"
          subtitle="A two-minute walkthrough of the full commit-to-dashboard loop."
        />

        <div className="mt-12 overflow-hidden rounded-2xl border border-slate-200 bg-slate-900 shadow-xl dark:border-slate-800">
          <div className="relative aspect-video w-full">
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-sky-500/20 ring-4 ring-sky-500/30">
                <PlayIconLarge />
              </div>
              <p className="mt-5 text-sm font-semibold text-white">
                Final Demo — coming with the 1.0 release
              </p>
              <p className="mt-1 text-xs text-slate-400">
                Placeholder while we cut the final video.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

const TEAM = [
  {
    name: "Aarsh Patel",
    initials: "AP",
    linkedin: "https://www.linkedin.com/",
  },
  {
    name: "Alex Mesa",
    initials: "AM",
    linkedin: "https://www.linkedin.com/",
  },
  {
    name: "Paksh Patel",
    initials: "PP",
    linkedin: "https://www.linkedin.com/",
  },
  {
    name: "Joseph Vann",
    initials: "JV",
    linkedin: "https://www.linkedin.com/",
  },
  {
    name: "Vraj Patel",
    initials: "VP",
    linkedin: "https://www.linkedin.com/",
  },
];

function TeamSection() {
  return (
    <section
      id="team"
      className="mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-28"
    >
      <SectionHeader
        eyebrow="About"
        title="Built by five students at the University of South Carolina"
        subtitle="Blender Collab is our senior capstone project. We built it because we lived the problem."
      />

      <div className="mt-14 grid grid-cols-2 gap-5 sm:grid-cols-3 lg:grid-cols-5">
        {TEAM.map((m) => (
          <div
            key={m.name}
            className="rounded-xl border border-slate-200 bg-white p-5 text-center transition hover:border-sky-400 hover:shadow-md dark:border-slate-800 dark:bg-slate-900/50 dark:hover:border-sky-500"
          >
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-sky-500 to-indigo-500 text-sm font-bold text-white">
              {m.initials}
            </div>
            <h3 className="mt-4 text-sm font-semibold">{m.name}</h3>
            <a
              href={m.linkedin}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-3 inline-flex items-center gap-1 text-xs text-sky-600 hover:text-sky-500 dark:text-sky-400"
            >
              <LinkedInIcon />
              LinkedIn
            </a>
          </div>
        ))}
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950">
      <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
        <div className="flex flex-col items-center justify-between gap-6 sm:flex-row">
          <div className="flex items-center gap-2">
            <LogoMark />
            <span className="text-sm font-semibold">Blender Collab</span>
            <span className="ml-3 text-xs text-slate-500">
              © 2026 USC Capstone Team
            </span>
          </div>
          <div className="flex items-center gap-5 text-sm">
            <Link
              href="/login"
              className="text-slate-600 hover:text-sky-600 dark:text-slate-300 dark:hover:text-sky-400"
            >
              Log in
            </Link>
            <Link
              href="/signup"
              className="text-slate-600 hover:text-sky-600 dark:text-slate-300 dark:hover:text-sky-400"
            >
              Sign up
            </Link>
          </div>
        </div>
      </div>
    </footer>
  );
}

function SectionHeader({
  eyebrow,
  title,
  subtitle,
}: {
  eyebrow: string;
  title: string;
  subtitle: string;
}) {
  return (
    <div className="mx-auto max-w-2xl text-center">
      <span className="text-xs font-mono font-semibold uppercase tracking-wider text-sky-600 dark:text-sky-400">
        {eyebrow}
      </span>
      <h2 className="mt-3 text-3xl font-bold tracking-tight sm:text-4xl">
        {title}
      </h2>
      <p className="mt-4 text-slate-600 dark:text-slate-300">{subtitle}</p>
    </div>
  );
}

function LogoMark() {
  return (
    <span className="inline-flex h-6 w-6 items-center justify-center rounded-md bg-gradient-to-br from-sky-500 to-indigo-500 shadow-sm">
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="white"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z" />
        <path d="M12 12l8-4.5" />
        <path d="M12 12v9" />
        <path d="M12 12L4 7.5" />
      </svg>
    </span>
  );
}

const iconProps = {
  width: 18,
  height: 18,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

function SunIcon() {
  return (
    <svg {...iconProps}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
  );
}
function MoonIcon() {
  return (
    <svg {...iconProps}>
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}
function ArrowIcon() {
  return (
    <svg {...iconProps} width={16} height={16}>
      <path d="M5 12h14M13 5l7 7-7 7" />
    </svg>
  );
}
function PlayIcon() {
  return (
    <svg {...iconProps} width={16} height={16}>
      <polygon points="6 4 20 12 6 20 6 4" fill="currentColor" stroke="none" />
    </svg>
  );
}
function PlayIconLarge() {
  return (
    <svg
      width="28"
      height="28"
      viewBox="0 0 24 24"
      fill="#38bdf8"
      stroke="#38bdf8"
      strokeWidth="1"
      strokeLinejoin="round"
    >
      <polygon points="6 4 20 12 6 20 6 4" />
    </svg>
  );
}
function SparkleIcon() {
  return (
    <svg {...iconProps} width={14} height={14}>
      <path d="M12 2l1.8 4.6L18 8l-4.2 1.4L12 14l-1.8-4.6L6 8l4.2-1.4z" />
      <path d="M18 14l.9 2.3L21 17l-2.1.7L18 20l-.9-2.3L15 17l2.1-.7z" />
    </svg>
  );
}
function CheckIcon() {
  return (
    <svg
      {...iconProps}
      width={18}
      height={18}
      className="mt-0.5 shrink-0 text-sky-500"
    >
      <path d="M20 6L9 17l-5-5" />
    </svg>
  );
}
function BranchIcon() {
  return (
    <svg {...iconProps}>
      <circle cx="6" cy="6" r="2" />
      <circle cx="6" cy="18" r="2" />
      <circle cx="18" cy="9" r="2" />
      <path d="M6 8v8M18 11a6 6 0 0 1-12 0" />
    </svg>
  );
}
function CubeIcon() {
  return (
    <svg {...iconProps}>
      <path d="M21 7.5L12 3 3 7.5l9 4.5 9-4.5z" />
      <path d="M3 7.5v9L12 21l9-4.5v-9" />
      <path d="M12 12v9" />
    </svg>
  );
}
function PuzzleIcon() {
  return (
    <svg {...iconProps}>
      <path d="M19 11h-4V7a2 2 0 1 0-4 0H7a2 2 0 0 0-2 2v4H3a2 2 0 1 0 0 4h2v4a2 2 0 0 0 2 2h4v-2a2 2 0 1 1 4 0v2h4a2 2 0 0 0 2-2v-4" />
    </svg>
  );
}
function UsersIcon() {
  return (
    <svg {...iconProps}>
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  );
}
function SplitIcon() {
  return (
    <svg {...iconProps}>
      <path d="M16 3h5v5M4 20L21 3M21 16v5h-5M15 15l6 6M4 4l5 5" />
    </svg>
  );
}
function GlobeIcon() {
  return (
    <svg {...iconProps}>
      <circle cx="12" cy="12" r="10" />
      <path d="M2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20" />
    </svg>
  );
}
function GitHubIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 .3a12 12 0 0 0-3.8 23.4c.6.1.8-.3.8-.6v-2c-3.3.7-4-1.4-4-1.4a3 3 0 0 0-1.3-1.7c-1-.7.1-.7.1-.7a2.5 2.5 0 0 1 1.8 1.3 2.6 2.6 0 0 0 3.5 1 2.6 2.6 0 0 1 .8-1.6c-2.6-.3-5.4-1.3-5.4-5.8a4.6 4.6 0 0 1 1.2-3.2 4.3 4.3 0 0 1 .1-3.2s1-.3 3.3 1.2a11.5 11.5 0 0 1 6 0c2.3-1.5 3.3-1.2 3.3-1.2a4.3 4.3 0 0 1 .1 3.2 4.6 4.6 0 0 1 1.2 3.2c0 4.5-2.8 5.5-5.4 5.8a2.9 2.9 0 0 1 .8 2.2v3.3c0 .3.2.7.8.6A12 12 0 0 0 12 .3" />
    </svg>
  );
}
function LinkedInIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
      <path d="M4.98 3.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5zM3 8.98h4V21H3zM9 9h3.8v1.7h.1a4.2 4.2 0 0 1 3.8-2.1c4 0 4.8 2.6 4.8 6.1V21h-4v-5.3c0-1.3 0-3-1.8-3s-2.1 1.4-2.1 2.9V21H9z" />
    </svg>
  );
}
