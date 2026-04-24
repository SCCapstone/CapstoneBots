"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";
import CommitItem from "@/components/CommitItem";
import BranchSelector from "@/components/BranchSelector";
import type { Commit, Project, Branch } from "@/lib/projectsApi";
import {
  fetchCommits,
  fetchProjects,
  fetchBranches,
} from "@/lib/projectsApi";
import { fetchCurrentUser } from "@/lib/authApi";

async function loadCommitsWithUsers(
  token: string,
  projectId: string,
  branchName?: string
): Promise<Commit[]> {
  const rawCommits = await fetchCommits(token, projectId, branchName ? { branchName } : undefined);
  const me = await fetchCurrentUser(token);
  return rawCommits.map((c) => ({
    ...c,
    author_username: c.author_id === me.user_id ? me.username : "Unknown User",
  }));
}

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

function dayLabel(dateIso: string): string {
  const d = new Date(dateIso);
  if (isNaN(d.getTime())) return "Unknown date";
  const today = startOfDay(new Date());
  const day = startOfDay(d);
  const diffDays = Math.round((today - day) / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  return d.toLocaleDateString(undefined, {
    weekday: "long",
    month: "short",
    day: "numeric",
    year: d.getFullYear() === new Date().getFullYear() ? undefined : "numeric",
  });
}

function groupByDay(commits: Commit[]): Array<{ label: string; items: Commit[] }> {
  const groups = new Map<string, Commit[]>();
  for (const c of commits) {
    const key = dayLabel(c.committed_at);
    const bucket = groups.get(key);
    if (bucket) bucket.push(c);
    else groups.set(key, [c]);
  }
  return Array.from(groups.entries()).map(([label, items]) => ({ label, items }));
}

export default function CommitsHistoryPage() {
  const params = useParams<{ projectId: string }>();
  const projectId = params.projectId;
  const { token } = useAuth();

  const [projectName, setProjectName] = useState<string>("");
  const [loadingProject, setLoadingProject] = useState(true);

  const [branches, setBranches] = useState<Branch[]>([]);
  const [currentBranch, setCurrentBranch] = useState<Branch | null>(null);

  const [commits, setCommits] = useState<Commit[]>([]);
  const [commitsLoading, setCommitsLoading] = useState(false);
  const [commitsError, setCommitsError] = useState("");

  // Load project name
  useEffect(() => {
    if (!token || !projectId) return;
    (async () => {
      try {
        const projects = await fetchProjects(token);
        const current = projects.find((p: Project) => p.project_id === projectId);
        setProjectName(current ? current.name : "Unknown Project");
      } catch {
        setProjectName("Unknown Project");
      } finally {
        setLoadingProject(false);
      }
    })();
  }, [token, projectId]);

  // Load branches
  useEffect(() => {
    if (!token || !projectId) return;
    (async () => {
      try {
        const branchList = await fetchBranches(token, projectId);
        setBranches(branchList);
        const main = branchList.find((b) => b.branch_name === "main") ?? branchList[0] ?? null;
        setCurrentBranch(main);
      } catch { }
    })();
  }, [token, projectId]);

  // Load commits when branch changes
  useEffect(() => {
    if (!token || !projectId || !currentBranch) return;
    const load = async () => {
      setCommitsLoading(true);
      setCommitsError("");
      try {
        const data = await loadCommitsWithUsers(token, projectId, currentBranch.branch_name);
        setCommits(data);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : "Failed to load commits.";
        setCommitsError(message);
        setCommits([]);
      } finally {
        setCommitsLoading(false);
      }
    };
    load();
  }, [token, projectId, currentBranch]);

  const displayName = loadingProject ? "Loading…" : projectName || "Untitled Project";
  const groups = groupByDay(commits);

  return (
    <div className="relative min-h-screen bg-[#0f172a] px-4 py-12">
      {/* Back Button */}
      <div className="absolute left-4 top-4">
        <Link
          href={`/projects/${projectId}`}
          className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-300 transition hover:border-sky-500 hover:text-sky-200"
        >
          ← Back to Project
        </Link>
      </div>

      <div className="mx-auto max-w-4xl space-y-5 pt-8">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <p className="mb-1 text-xs text-slate-500">
              Projects /{" "}
              <Link href={`/projects/${projectId}`} className="text-slate-300 hover:text-sky-300">
                {displayName}
              </Link>{" "}
              / <span className="text-slate-300">Commits</span>
            </p>
            <h1 className="text-2xl font-semibold text-white">Commit history</h1>
          </div>
          {token && (
            <BranchSelector
              token={token}
              projectId={projectId}
              branches={branches}
              currentBranch={currentBranch}
              onBranchChange={(b) => setCurrentBranch(b)}
              onBranchesUpdated={(updated) => setBranches(updated)}
            />
          )}
        </div>

        {/* Summary bar */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-3 text-xs text-slate-400">
          <span className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-950 px-2 py-1 text-[11px] text-slate-200">
              <span className="h-2 w-2 rounded-full bg-green-500" />
              <span>{currentBranch?.branch_name ?? "main"}</span>
            </span>
            <span>
              {commitsLoading
                ? "Loading commits…"
                : `${commits.length} commit${commits.length === 1 ? "" : "s"}`}
            </span>
          </span>
        </div>

        {/* Commit list grouped by day */}
        <div className="space-y-6">
          {commitsError && (
            <div className="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-xs text-red-300">
              {commitsError}
            </div>
          )}

          {!commitsLoading && !commitsError && commits.length === 0 && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-8 text-center text-xs text-slate-500">
              No commits yet for this branch. Push from Blender to add commits.
            </div>
          )}

          {groups.map((group) => (
            <section key={group.label}>
              <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Commits on {group.label}
              </h2>
              <div className="space-y-2">
                {group.items.map((c) => (
                  <CommitItem
                    key={c.commit_id}
                    commit={c}
                    projectId={projectId}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
