"use client";

import { useEffect, useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";
import {
  fetchProjects,
  Project,
  createProject,
  ProjectCreatePayload,
  fetchPendingInvitations,
} from "@/lib/projectsApi";

export default function ProjectsPage() {
  const router = useRouter();
  const { token, isAuthenticated, logout } = useAuth();

  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Modal state
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [inviteCount, setInviteCount] = useState(0);

  // If not authenticated, send to /login
  useEffect(() => {
    if (!token) {
      if (!isAuthenticated) {
        router.replace("/login");
      }
      return;
    }

    (async () => {
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
      try {
        const invites = await fetchPendingInvitations(token);
        setInviteCount(invites.length);
      } catch { }
    })();

  }, [token, isAuthenticated, router]);

  if (!token && !isAuthenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#0f172a] text-sm text-slate-400">
        Redirecting to login...
      </div>
    );
  }

  const handleCreateProject = async (e: FormEvent) => {
    e.preventDefault();
    setCreateError("");

    if (!token) return;

    if (!newName.trim()) {
      setCreateError("Project name is required.");
      return;
    }

    setCreating(true);
    try {
      const payload: ProjectCreatePayload = {
        name: newName.trim(),
        description: newDescription.trim() || undefined,
        active: true,
      };

      const created = await createProject(token, payload);

      // Add new project to top of list
      setProjects((prev) => [created, ...prev]);

      // Reset + close modal
      setNewName("");
      setNewDescription("");
      setShowCreate(false);
    } catch (err: any) {
      setCreateError(err?.message || "Failed to create project.");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-[#0f172a] px-4">
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

          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                setCreateError("");
                setShowCreate(true);
              }}
              className="rounded-lg bg-sky-600 px-3 py-1 text-xs font-semibold text-white hover:bg-sky-500 transition"
            >
              + New Project
            </button>

            <Link
              href="/invitations"
              className="relative rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:border-sky-500 hover:text-sky-200 transition"
            >
              Invitations
              {inviteCount > 0 && (
                <span className="absolute -right-1.5 -top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-sky-500 text-[9px] font-bold text-white">
                  {inviteCount}
                </span>
              )}
            </Link>

            <Link
              href="/settings"
              className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:border-sky-500 hover:text-sky-200 transition"
            >
              Settings
            </Link>

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
        </div>

        {/* Loading / Error states */}
        {loading && (
          <p className="text-xs text-slate-400">Loading projects...</p>
        )}

        {error && (
          <p className="mb-3 text-xs text-red-400">{error}</p>
        )}

        {!loading && !error && projects.length === 0 && (
          <p className="text-xs text-slate-500">
            No projects found. Try creating one.
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

      {/* Create Project Overlay */}
      {showCreate && (
        <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-sm rounded-2xl border border-slate-700 bg-slate-900/90 p-6 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-white">
                Create New Project
              </h2>
              <button
                type="button"
                onClick={() => {
                  if (!creating) {
                    setShowCreate(false);
                    setCreateError("");
                  }
                }}
                className="text-xs text-slate-400 hover:text-slate-200"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateProject} className="space-y-4">
              <div className="text-left">
                <label className="mb-1 block text-[11px] font-medium text-slate-300">
                  Project Name
                </label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-100 outline-none focus:border-sky-500"
                  placeholder="Blender Environment v1"
                  required
                />
              </div>

              <div className="text-left">
                <label className="mb-1 block text-[11px] font-medium text-slate-300">
                  Description (optional)
                </label>
                <textarea
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-100 outline-none focus:border-sky-500"
                  rows={3}
                  placeholder="Short description of this Blender project..."
                />
              </div>

              {createError && (
                <p className="text-[11px] text-red-400">
                  {createError}
                </p>
              )}

              <div className="mt-2 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => {
                    if (!creating) {
                      setShowCreate(false);
                      setCreateError("");
                    }
                  }}
                  className="rounded-lg border border-slate-700 px-3 py-1 text-[11px] text-slate-300 hover:border-slate-500"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="rounded-lg bg-sky-600 px-3 py-1 text-[11px] font-semibold text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {creating ? "Creating..." : "Create Project"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
