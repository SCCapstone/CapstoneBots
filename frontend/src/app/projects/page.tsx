"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";
import { fetchProjects, Project } from "@/lib/projectsApi";

export default function ProjectsPage() {
  const router = useRouter();
  const { token, isAuthenticated, logout } = useAuth();

  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // If not authenticated, send to /login
  useEffect(() => {
    if (!token) {
      // let AuthProvider hydrate first before redirecting
      if (!isAuthenticated) {
        router.replace("/login");
      }
      return;
    }

    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const data = await fetchProjects(token);
        setProjects(data);
      } catch (err: any) {
        setError(err?.message || "Failed to load projects.");
      } finally {
        setLoading(false);
      }
    };

    load();
  }, [token, isAuthenticated, router]);

  if (!token && !isAuthenticated) {
    // tiny placeholder while redirect runs
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#0f172a] text-sm text-slate-400">
        Redirecting to login...
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0f172a] px-4">
      <div className="w-full max-w-3xl">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-white">
              Projects
            </h1>
            <p className="mt-1 text-xs text-slate-400">
              Select a project to view its commits and object history.
            </p>
          </div>
          <button
            onClick={() => {
              logout();
              router.replace("/login");
            }}
            className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:border-sky-500 hover:text-sky-200 transition"
          >
            Log out
          </button>
        </div>

        {/* Loading / Error states */}
        {loading && (
          <p className="text-xs text-slate-400">Loading projects...</p>
        )}

        {error && (
          <p className="text-xs text-red-400 mb-3">{error}</p>
        )}

        {!loading && !error && projects.length === 0 && (
          <p className="text-xs text-slate-500">
            No projects found. Try creating one in the backend.
          </p>
        )}

        {/* Project list */}
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {projects.map((project) => (
            <Link
              key={project.project_id}
              href={`/projects/${project.project_id}`}
              className="group rounded-xl border border-slate-800 bg-slate-900/60 p-4 transition hover:border-sky-500/70 hover:bg-slate-900"
            >
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-sm font-semibold text-slate-50 group-hover:text-sky-200">
                  {project.name}
                </h2>
                {project.default_branch && (
                  <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] uppercase tracking-wide text-slate-400">
                    {project.default_branch}
                  </span>
                )}
              </div>

              {project.description && (
                <p className="mt-2 line-clamp-2 text-xs text-slate-400">
                  {project.description}
                </p>
              )}

              {project.updated_at && (
                <p className="mt-3 text-[10px] text-slate-500">
                  Updated:{" "}
                  {new Date(project.updated_at).toLocaleString()}
                </p>
              )}
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
