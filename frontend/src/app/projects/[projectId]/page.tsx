"use client";

import { useState } from "react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";
import { deleteProject } from "@/lib/projectsApi";

export default function ProjectPage() {
  const router = useRouter();
  const params = useParams<{ projectId: string }>();
  const projectId = params.projectId;

  const { token } = useAuth();

  const [showConfirm, setShowConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");

  const handleDelete = async () => {
    if (!token) {
      setError("You must be logged in to delete a project.");
      return;
    }

    setDeleting(true);
    setError("");

    try {
      await deleteProject(token, projectId);

      // Close overlay before navigating
      setShowConfirm(false);

      // Navigate back to project list
      router.push("/projects");
    } catch (err: any) {
      setError(err?.message || "Failed to delete project.");
      setDeleting(false);
    }
  };

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-[#0f172a] px-4">
      {/* Back Button */}
      <div className="absolute left-4 top-4">
        <Link
          href="/projects"
          className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:border-sky-500 hover:text-sky-200 transition"
        >
          ← Back to Projects
        </Link>
      </div>

      {/* Content */}
      <div className="w-full max-w-md text-center">
        <div className="mb-4 flex items-center justify-between">
          <h1 className="text-xl font-semibold text-white">
            Project: {projectId}
          </h1>
          <button
            onClick={() => setShowConfirm(true)}
            className="rounded-lg border border-red-500/70 px-3 py-1 text-xs text-red-300 hover:bg-red-500/10 transition"
          >
            Delete
          </button>
        </div>

        <p className="mb-6 text-sm text-slate-400">
          Commit list will appear here (not implemented yet).
        </p>

        <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-6">
          <p className="text-xs text-slate-400">
            This page will show commit history for this project.
          </p>
          {error && (
            <p className="mt-3 text-[11px] text-red-400">{error}</p>
          )}
        </div>
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
    </div>
  );
}
