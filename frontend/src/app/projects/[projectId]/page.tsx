"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";
import type { Commit, Project } from "@/lib/projectsApi";
import {
  // addProjectMember,
  deleteProject,
  fetchCommits,
  fetchProjects,
  fetchCommitObjects,
} from "@/lib/projectsApi";
import { fetchCurrentUser } from "@/lib/authApi";

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
  s3Path?: string;
};

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

  // 🔹 Files state (real data)
  const [files, setFiles] = useState<FileRow[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);

  // const [memberEmail, setMemberEmail] = useState("");
  // const [addingMember, setAddingMember] = useState(false);
  // const [memberMessage, setMemberMessage] = useState("");


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

  useEffect(() => {
    if (!token || !projectId) return;

    const loadCommitsAndFiles = async () => {
      setCommitsLoading(true);
      setCommitsError("");
      setFilesLoading(true);

      try {
        // 1) Load commits (with usernames)
        const data = await loadCommitsWithUsers(token, projectId);
        setCommits(data);

        // 2) If we have at least one commit, fetch its objects as "files"
        if (data.length > 0) {
          const latest = data[0]; // newest commit (API already orders newest first:contentReference[oaicite:1]{index=1})
          const objects = await fetchCommitObjects(
            token,
            projectId,
            latest.commit_id
          );

          const rows: FileRow[] = objects.map((obj) => {
            let s3Path: string | undefined;

            // Only the BLEND_FILE represents the full .blend in S3
            // @ts-ignore
            if (obj.object_type === "BLEND_FILE" && obj.json_data_path) {
              // @ts-ignore
              const raw = obj.json_data_path as string;

              // Example raw:
              // "s3://blender-vcs-prod/a5deedcc-.../Untitled.blend"
              const prefix = "s3://blender-vcs-prod/";
              if (raw.startsWith(prefix)) {
                s3Path = raw.slice(prefix.length); // -> "a5deedcc-.../Untitled.blend"
              } else {
                // fallback if backend ever changes format
                s3Path = raw;
              }
            }

            return {
              id: obj.object_id,
              name: obj.object_name,
              type: obj.object_type === "COLLECTION" ? "folder" : "file",
              lastCommit: `"${latest.commit_message}"`,
              updatedAt: formatCommitDate(latest.committed_at),
              s3Path, // 👈 store it
            };
          });

          setFiles(rows);
        } else {
          // No commits => no files
          setFiles([]);
        }
      } catch (err: any) {
        setCommitsError(err?.message || "Failed to load commits.");
        setFiles([]);
      } finally {
        setCommitsLoading(false);
        setFilesLoading(false);
      }
    };

    loadCommitsAndFiles();
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

  const API_BASE =
    process.env.NEXT_PUBLIC_BACKEND_URL;

  const handleDownloadFile = async (file: FileRow) => {
    if (!token) {
      console.error("You must be logged in to download files.");
      return;
    }

    if (!file.s3Path) {
      console.warn("No S3 path for this file; nothing to download.");
      return;
    }

    try {
      const res = await fetch(
        `${API_BASE}/api/projects/${projectId}/files/download?path=${encodeURIComponent(
          file.s3Path
        )}`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!res.ok) {
        console.error("Failed to get signed URL", await res.text());
        return;
      }

      const data = (await res.json()) as { url: string };
      if (data.url) {
        window.open(data.url, "_blank");
      }
    } catch (e) {
      console.error("Error downloading file", e);
    }
  };

  // 🔹 When clicking the "X Commits" button
  const handleOpenCommits = () => {
    if (!token) return;
    setShowCommits(true);
  };

  // const handleAddMember = async (event: FormEvent<HTMLFormElement>) => {
  //   event.preventDefault();
  //
  //   if (!token) {
  //     setMemberMessage("You must be logged in to add a member.");
  //     return;
  //   }
  //
  //   if (!memberEmail.trim()) {
  //     setMemberMessage("Please enter an email address.");
  //     return;
  //   }
  //
  //   setAddingMember(true);
  //   setMemberMessage("");
  //
  //   try {
  //     const result = await addProjectMember(token, projectId, {
  //       email: memberEmail.trim(),
  //     });
  //
  //     setMemberEmail("");
  //     setMemberMessage(`Added ${result.email} to this project.`);
  //   } catch (err: any) {
  //     setMemberMessage(err?.message || "Failed to add member.");
  //   } finally {
  //     setAddingMember(false);
  //   }
  // };

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
              // onClick={() => setShowConfirm(true)}
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

        {/* Add member section (commented out for frontend reference) */}
        {/*
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-3 text-xs">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-[11px] text-slate-400">Add member by email</p>
              <p className="text-[11px] text-slate-500">
                Enter an email address to grant immediate access to this project.
              </p>
            </div>
            <form
              onSubmit={handleAddMember}
              className="flex w-full max-w-md items-center gap-2"
            >
              <input
                type="email"
                value={memberEmail}
                onChange={(event) => setMemberEmail(event.target.value)}
                placeholder="teammate@example.com"
                className="flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-[11px] text-slate-200 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
                required
              />
              <button
                type="submit"
                disabled={addingMember}
                className="rounded-lg border border-slate-700 px-3 py-2 text-[11px] text-slate-200 transition hover:border-sky-500 hover:text-sky-200 disabled:opacity-60"
              >
                {addingMember ? "Adding..." : "Add Member"}
              </button>
            </form>
          </div>
          {memberMessage && (
            <p className="mt-2 text-[11px] text-slate-300">{memberMessage}</p>
          )}
        </div>
        */}

        {/* Files table only – no README, no New File */}
        <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60 text-xs">
          {/* Table header */}
          <div className="grid grid-cols-4 border-b border-slate-800 bg-slate-950 px-4 py-2 text-[11px] font-medium text-slate-400">
            <div className="text-left">NAME</div>
            <div className="text-left">LAST COMMIT</div>
            <div className="text-right">LAST UPDATED</div>
            <div className="text-right">ACTIONS</div>
          </div>

          {/* Rows */}
          <div className="divide-y divide-slate-800">
            {filesLoading ? (
              <div className="px-4 py-3 text-xs text-slate-400">
                Loading files...
              </div>
            ) : files.length === 0 ? (
              <div className="px-4 py-3 text-xs text-slate-500">
                No files yet for this project.
              </div>
            ) : (
              files.map((file) => (
                <div
                  key={file.id}
                  className="grid grid-cols-4 items-center px-4 py-2 hover:bg-slate-900"
                >
                  {/* Name + icon */}
                  <div className="flex items-center gap-2 text-slate-100">
                    <span
                      className={`flex h-4 w-4 items-center justify-center rounded-sm ${file.type === "folder"
                        ? "bg-yellow-500/20 text-yellow-300"
                        : "bg-slate-700/60 text-slate-300"
                        }`}
                    >
                      {file.type === "folder" ? "▣" : "▤"}
                    </span>
                    <span className="truncate">{file.name}</span>
                  </div>

                  {/* Last commit message */}
                  <div className="truncate text-slate-400">{file.lastCommit}</div>

                  {/* Updated at */}
                  <div className="text-right text-slate-500">{file.updatedAt}</div>

                  {/* Actions */}
                  <div className="text-right">
                    {file.s3Path ? (
                      <button
                        type="button"
                        onClick={() => handleDownloadFile(file)}
                        className="rounded border border-sky-500 px-2 py-0.5 text-[11px] text-sky-300 hover:bg-sky-500/10"
                      >
                        Download
                      </button>
                    ) : (
                      <span className="text-[11px] text-slate-600">—</span>
                    )}
                  </div>
                </div>
              ))
            )}
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
    </div>
  );
}
