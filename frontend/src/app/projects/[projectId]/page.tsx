"use client";

import {useEffect, useState} from "react";
import {useParams, useRouter} from "next/navigation";
import Link from "next/link";
import {useAuth} from "@/components/AuthProvider";
import type {Commit, Project} from "@/lib/projectsApi";
import {deleteProject, fetchCommits, fetchProjects} from "@/lib/projectsApi";
import {fetchCurrentUser} from "@/lib/authApi";

function formatCommitDate(dateString: string): string {
  const date = new Date(dateString);
  if (isNaN(date.getTime())) {
    return dateString; // fallback if backend sends unexpected format
  }
  return date.toLocaleString();
}

async function loadCommitsWithUsers(
  token: string,
  projectId: string
): Promise<Commit[]> {
  // Get all commits for this project/branch
  const rawCommits = await fetchCommits(token, projectId, "main");

  // Get the currently logged-in user once
  const me = await fetchCurrentUser(token);

  // Attach username to any commit authored by this user
  return rawCommits.map((c) => ({
    ...c,
    author_username:
      c.author_id === me.user_id ? me.username : "Unknown User",
  }));
}

type FileRow = {
  id: string;
  name: string;
  type: "folder" | "file";
  lastCommit: string;
  updatedAt: string;
};

// Temporary mock data – replace with real file API later
const mockFiles: FileRow[] = [
  {
    id: "1",
    name: "assets",
    type: "folder",
    lastCommit: '"Added new rock and tree models"',
    updatedAt: "1 day ago",
  },
  {
    id: "2",
    name: "scenes",
    type: "folder",
    lastCommit: '"Initial setup for the main scene"',
    updatedAt: "5 days ago",
  },
  {
    id: "3",
    name: "character_model.blend",
    type: "file",
    lastCommit: '"Fixed rigging issue on left arm"',
    updatedAt: "2 hours ago",
  },
  {
    id: "4",
    name: "uv_layout.png",
    type: "file",
    lastCommit: '"Updated UV map for character clothing"',
    updatedAt: "3 days ago",
  },
  {
    id: "5",
    name: "README.md",
    type: "file",
    lastCommit: '"Initial project description"',
    updatedAt: "1 week ago",
  },
];

export default function ProjectPage() {
  const router = useRouter();
  const params = useParams<{ projectId: string }>();
  const projectId = params.projectId;

  const { token } = useAuth();

  const [projectName, setProjectName] = useState<string>("");
  const [loadingProject, setLoadingProject] = useState(true);

  const [showConfirm, setShowConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");

  // 🔹 Commits overlay state
  const [showCommits, setShowCommits] = useState(false);
  const [commits, setCommits] = useState<Commit[]>([]);
  const [commitsLoading, setCommitsLoading] = useState(false);
  const [commitsError, setCommitsError] = useState("");
  const commitCount = commits.length; // will be 0 until we load

  // Load project name so we can show "Project Alpha" style headings
  useEffect(() => {
    if (!token || !projectId) return;

    const load = async () => {
      try {
        const projects = await fetchProjects(token);
        const current = projects.find(
          (p: Project) => p.project_id === projectId
        );
        if (current) {
          setProjectName(current.name);
        } else {
          setProjectName("Unknown Project");
        }
      } catch (err) {
        console.error("Failed to load project list for project page", err);
        setProjectName("Unknown Project");
      } finally {
        setLoadingProject(false);
      }
    };

    load();
  }, [token, projectId]);

  useEffect(() => {
    if (!token || !projectId) return;

    const loadCommits = async () => {
      setCommitsLoading(true);
      setCommitsError("");

      try {
        const data = await loadCommitsWithUsers(token, projectId);
        setCommits(data);
      } catch (err: any) {
        setCommitsError(err?.message || "Failed to load commits.");
      } finally {
        setCommitsLoading(false);
      }
    };

    loadCommits();
  }, [token, projectId]);

  const displayName =
    loadingProject ? "Loading…" : projectName || "Untitled Project";

  const handleDelete = async () => {
    if (!token) {
      setError("You must be logged in to delete a project.");
      return;
    }

    setDeleting(true);
    setError("");

    try {
      await deleteProject(token, projectId);

      setShowConfirm(false);
      router.replace("/projects");
    } catch (err: any) {
      setError(err?.message || "Failed to delete project.");
      setDeleting(false);
    }
  };

  // 🔹 When clicking the "X Commits" button
  const handleOpenCommits = () => {
    if (!token) return;
    setShowCommits(true);
  };

  return (
    <div className="relative min-h-screen bg-[#0f172a] flex items-center justify-center px-4">
      {/* Back Button */}
      <div className="absolute left-4 top-4">
        <Link
          href="/projects"
          className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-300 transition hover:border-sky-500 hover:text-sky-200"
        >
          ← Back to Projects
        </Link>
      </div>

      {/* Main content container */}
      <div className="w-full max-w-5xl space-y-5">
        {/* Header + actions */}
        <div className="flex items-center justify-between">
          <div>
            <p className="mb-1 text-xs text-slate-500">
              Projects /{" "}
              <span className="text-slate-300">{displayName}</span>
            </p>
            <h1 className="text-2xl font-semibold text-white">
              {displayName}
            </h1>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              className="rounded-lg border border-slate-700 px-3 py-1 text-[11px] text-slate-300 transition hover:border-slate-500"
            >
              Conflicts
            </button>
            <button
              type="button"
              onClick={handleOpenCommits}
              className="rounded-lg border border-slate-700 px-3 py-1 text-[11px] text-slate-300 transition hover:border-sky-500 hover:text-sky-200"
            >
              {commitCount} Commits
            </button>
            <button
              type="button"
              onClick={() => setShowConfirm(true)}
              className="rounded-lg border border-red-500/70 px-3 py-1 text-[11px] text-red-300 transition hover:bg-red-500/10"
            >
              Delete
            </button>
          </div>
        </div>

        {/* Branch / last commit bar */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-3 text-xs">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <button className="flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-950 px-2 py-1 text-[11px] text-slate-200 hover:border-slate-500">
                <span className="h-2 w-2 rounded-full bg-green-500" />
                <span>main</span>
              </button>

              {commits.length > 0 ? (
                <p className="text-slate-400">
                  <span className="font-medium text-slate-200">
                    {commits[0].author_username || "Unknown User"}
                  </span>{" "}
                  committed{" "}
                  <span className="text-sky-300">
                    &quot;{commits[0].commit_message}&quot;
                  </span>{" "}
                  · {formatCommitDate(commits[0].committed_at)}
                </p>
              ) : (
                <p className="text-slate-500">No commits yet</p>
              )}
            </div>
          </div>
        </div>

        {/* Files table only – no README, no New File */}
        <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60 text-xs">
          {/* Table header */}
          <div className="grid grid-cols-3 border-b border-slate-800 bg-slate-950 px-4 py-2 text-[11px] font-medium text-slate-400">
            <div className="text-left">NAME</div>
            <div className="text-left">LAST COMMIT</div>
            <div className="text-right">LAST UPDATED</div>
          </div>

          {/* Rows */}
          <div className="divide-y divide-slate-800">
            {mockFiles.map((file) => (
              <div
                key={file.id}
                className="grid grid-cols-3 items-center px-4 py-2 hover:bg-slate-900"
              >
                {/* Name + icon */}
                <div className="flex items-center gap-2 text-slate-100">
                  <span
                    className={`flex h-4 w-4 items-center justify-center rounded-sm ${
                      file.type === "folder"
                        ? "bg-yellow-500/20 text-yellow-300"
                        : "bg-slate-700/60 text-slate-300"
                    }`}
                  >
                    {file.type === "folder" ? "▣" : "▤"}
                  </span>
                  <span className="truncate">{file.name}</span>
                </div>

                {/* Last commit message */}
                <div className="truncate text-slate-400">
                  {file.lastCommit}
                </div>

                {/* Updated at */}
                <div className="text-right text-slate-500">
                  {file.updatedAt}
                </div>
              </div>
            ))}
          </div>
        </div>

        {error && (
          <p className="text-[11px] text-red-400">{error}</p>
        )}
      </div>

      {/* Confirm Delete Overlay */}
      {showConfirm && (
        <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-sm rounded-2xl border border-slate-700 bg-slate-900 p-6 shadow-xl">
            <h2 className="mb-2 text-sm font-semibold text-white">
              Delete project?
            </h2>
            <p className="mb-4 text-xs text-slate-400">
              This will permanently delete this project and its data. This
              action cannot be undone.
            </p>

            {error && (
              <p className="mb-3 text-[11px] text-red-400">{error}</p>
            )}

            <div className="mt-2 flex items-center justify-end gap-2">
              <button
                type="button"
                disabled={deleting}
                onClick={() => {
                  if (!deleting) {
                    setShowConfirm(false);
                    setError("");
                  }
                }}
                className="rounded-lg border border-slate-700 px-3 py-1 text-[11px] text-slate-300 hover:border-slate-500 disabled:opacity-60"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDelete}
                disabled={deleting}
                className="rounded-lg bg-red-600 px-3 py-1 text-[11px] font-semibold text-white hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-70"
              >
                {deleting ? "Deleting..." : "Delete Project"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 🔹 Commits Overlay */}
      {showCommits && (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-2xl rounded-2xl border border-slate-700 bg-slate-900 p-6 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-white">
                Commits for {displayName}
              </h2>
              <button
                type="button"
                onClick={() => {
                  setShowCommits(false);
                  setCommitsError("");
                }}
                className="text-xs text-slate-400 hover:text-slate-100"
              >
                ✕
              </button>
            </div>

            {commitsLoading && (
              <p className="text-xs text-slate-400">
                Loading commits...
              </p>
            )}

            {commitsError && (
              <p className="mb-2 text-xs text-red-400">
                {commitsError}
              </p>
            )}

            {!commitsLoading && !commitsError && commits.length === 0 && (
              <p className="text-xs text-slate-400">
                No commits yet for this project.
              </p>
            )}

            {!commitsLoading && !commitsError && commits.length > 0 && (
              <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
                {commits.map((c) => {
                  const date = new Date(c.committed_at);
                  const formatted = isNaN(date.getTime())
                    ? c.committed_at
                    : date.toLocaleString();
                  const shortHash = c.commit_hash.slice(0, 7);

                  return (
                    <div
                      key={c.commit_id}
                      className="flex items-start justify-between rounded-lg border border-slate-800 bg-slate-900/70 px-3 py-2 text-xs hover:border-sky-500/60 hover:bg-slate-900"
                    >
                      <div className="flex-1 pr-3">
                        <p className="font-medium text-slate-100">
                          {c.commit_message || "(no message)"}
                        </p>
                        <p className="mt-1 text-[11px] text-slate-500">
                          <span className="inline-flex items-center gap-1">
                            <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-300">
                              {shortHash}
                            </span>
                            <span>{formatted}</span>
                          </span>
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
