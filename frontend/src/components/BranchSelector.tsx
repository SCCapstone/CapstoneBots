"use client";

import { useState, useRef, useEffect } from "react";
import type { Branch } from "@/lib/projectsApi";
import {
  fetchBranches,
  createBranch,
  deleteBranch,
  mergeBranch,
} from "@/lib/projectsApi";

type BranchSelectorProps = {
  token: string;
  projectId: string;
  branches: Branch[];
  currentBranch: Branch | null;
  defaultBranchName?: string;
  onBranchChange: (branch: Branch) => void;
  onBranchesUpdated: (branches: Branch[]) => void;
};

export default function BranchSelector({
  token,
  projectId,
  branches,
  currentBranch,
  defaultBranchName = "main",
  onBranchChange,
  onBranchesUpdated,
}: BranchSelectorProps) {
  const [open, setOpen] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [showMerge, setShowMerge] = useState(false);
  const [newBranchName, setNewBranchName] = useState("");
  const [mergeSrcId, setMergeSrcId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setShowCreate(false);
        setShowMerge(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  async function refreshBranches() {
    const updated = await fetchBranches(token, projectId);
    onBranchesUpdated(updated);
    return updated;
  }

  async function handleCreate() {
    if (!newBranchName.trim()) return;
    setLoading(true);
    setError("");
    try {
      const branch = await createBranch(token, projectId, {
        branch_name: newBranchName.trim(),
        source_commit_id: currentBranch?.head_commit_id ?? undefined,
      });
      const updated = await refreshBranches();
      const created = updated.find((b) => b.branch_id === branch.branch_id);
      if (created) onBranchChange(created);
      setNewBranchName("");
      setShowCreate(false);
      setOpen(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to create branch");
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(branch: Branch) {
    if (!confirm(`Delete branch "${branch.branch_name}"? Commits will not be deleted.`))
      return;
    setLoading(true);
    setError("");
    try {
      await deleteBranch(token, projectId, branch.branch_id);
      const updated = await refreshBranches();
      // If we deleted the current branch, switch to default
      if (currentBranch?.branch_id === branch.branch_id) {
        const def = updated.find((b) => b.branch_name === defaultBranchName);
        if (def) onBranchChange(def);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to delete branch");
    } finally {
      setLoading(false);
    }
  }

  async function handleMerge() {
    if (!mergeSrcId || !currentBranch) return;
    setLoading(true);
    setError("");
    try {
      await mergeBranch(token, projectId, currentBranch.branch_id, {
        source_branch_id: mergeSrcId,
      });
      await refreshBranches();
      setShowMerge(false);
      setOpen(false);
      // Re-trigger branch change to refresh commits
      onBranchChange(currentBranch);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Merge failed");
    } finally {
      setLoading(false);
    }
  }

  const isDefault = (b: Branch) => b.branch_name === defaultBranchName;

  return (
    <div ref={ref} className="relative">
      {/* Trigger button */}
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800/80 px-3 py-1.5 text-sm text-slate-200 transition hover:border-sky-500/60 hover:bg-slate-800"
      >
        <svg
          className="h-4 w-4 text-sky-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"
          />
        </svg>
        <span className="font-medium">{currentBranch?.branch_name ?? "main"}</span>
        <svg
          className={`h-3 w-3 text-slate-400 transition ${open ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute left-0 z-50 mt-1 w-72 rounded-lg border border-slate-700 bg-slate-900 shadow-xl">
          {error && (
            <div className="border-b border-red-800 bg-red-900/30 px-3 py-2 text-xs text-red-300">
              {error}
            </div>
          )}

          {/* Branch list */}
          <div className="max-h-48 overflow-y-auto p-1">
            {branches.map((b) => (
              <div
                key={b.branch_id}
                className={`flex items-center justify-between rounded px-2.5 py-1.5 text-sm transition ${
                  b.branch_id === currentBranch?.branch_id
                    ? "bg-sky-900/30 text-sky-200"
                    : "text-slate-300 hover:bg-slate-800"
                }`}
              >
                <button
                  className="flex-1 text-left"
                  onClick={() => {
                    onBranchChange(b);
                    setOpen(false);
                  }}
                >
                  <span className="font-medium">{b.branch_name}</span>
                  {isDefault(b) && (
                    <span className="ml-1.5 text-[10px] text-slate-500">default</span>
                  )}
                </button>
                {!isDefault(b) && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(b);
                    }}
                    className="ml-2 rounded p-0.5 text-slate-500 hover:bg-red-900/30 hover:text-red-400"
                    title="Delete branch"
                  >
                    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                )}
              </div>
            ))}
          </div>

          {/* Actions */}
          <div className="border-t border-slate-800 p-2 space-y-1">
            {/* Create branch */}
            {showCreate ? (
              <div className="flex items-center gap-1.5">
                <input
                  autoFocus
                  value={newBranchName}
                  onChange={(e) => setNewBranchName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                  placeholder="Branch name..."
                  className="flex-1 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 placeholder-slate-500 focus:border-sky-500 focus:outline-none"
                />
                <button
                  onClick={handleCreate}
                  disabled={loading || !newBranchName.trim()}
                  className="rounded bg-sky-600 px-2 py-1 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
                >
                  {loading ? "..." : "Create"}
                </button>
              </div>
            ) : (
              <button
                onClick={() => {
                  setShowCreate(true);
                  setShowMerge(false);
                }}
                className="w-full rounded px-2.5 py-1.5 text-left text-xs text-sky-400 hover:bg-slate-800"
              >
                + New branch
              </button>
            )}

            {/* Merge branch */}
            {showMerge ? (
              <div className="flex items-center gap-1.5">
                <select
                  value={mergeSrcId}
                  onChange={(e) => setMergeSrcId(e.target.value)}
                  className="flex-1 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-purple-500 focus:outline-none"
                >
                  <option value="">Merge from...</option>
                  {branches
                    .filter((b) => b.branch_id !== currentBranch?.branch_id)
                    .map((b) => (
                      <option key={b.branch_id} value={b.branch_id}>
                        {b.branch_name}
                      </option>
                    ))}
                </select>
                <button
                  onClick={handleMerge}
                  disabled={loading || !mergeSrcId}
                  className="rounded bg-purple-600 px-2 py-1 text-xs font-medium text-white hover:bg-purple-500 disabled:opacity-50"
                >
                  {loading ? "..." : "Merge"}
                </button>
              </div>
            ) : (
              branches.length > 1 && (
                <button
                  onClick={() => {
                    setShowMerge(true);
                    setShowCreate(false);
                  }}
                  className="w-full rounded px-2.5 py-1.5 text-left text-xs text-purple-400 hover:bg-slate-800"
                >
                  ↗ Merge into {currentBranch?.branch_name ?? "current"}
                </button>
              )
            )}
          </div>
        </div>
      )}
    </div>
  );
}
