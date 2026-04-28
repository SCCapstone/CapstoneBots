// src/components/CommitItem.tsx
"use client";

import Link from "next/link";
import type { Commit } from "@/lib/projectsApi";
import { formatApiDateTime } from "@/lib/datetime";

type CommitItemProps = {
  commit: Commit;
  projectId: string;
  objectCount?: number;
};

export default function CommitItem({ commit, projectId, objectCount }: CommitItemProps) {
  const formatted = formatApiDateTime(commit.committed_at);

  const shortHash = commit.commit_hash.slice(0, 7);

  return (
    <Link
      href={`/projects/${projectId}/${commit.commit_hash}`}
      className="group flex items-start justify-between rounded-lg border border-slate-800 bg-slate-900/70 px-3 py-2 text-xs transition hover:border-sky-500/60 hover:bg-slate-900"
    >
      <div className="flex-1 pr-3">
        <p className="font-medium text-slate-100 group-hover:text-sky-200">
          {commit.commit_message || "(no message)"}
        </p>
        <p className="mt-1 text-[11px] text-slate-500">
          <span className="inline-flex items-center gap-1.5 flex-wrap">
            <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-300">
              {shortHash}
            </span>
            {commit.branch_name && (
              <span className="rounded bg-sky-900/50 px-1.5 py-0.5 text-[10px] text-sky-300 border border-sky-700/40">
                {commit.branch_name}
              </span>
            )}
            {commit.merge_commit && (
              <span className="rounded bg-purple-900/50 px-1.5 py-0.5 text-[10px] text-purple-300 border border-purple-700/40">
                merge
              </span>
            )}
            <span>· {formatted}</span>
            {commit.author_username && (
              <span>· {commit.author_username}</span>
            )}
          </span>
        </p>
      </div>
      {objectCount !== undefined && (
        <div className="flex shrink-0 items-center gap-1 rounded-full border border-slate-700 bg-slate-800/60 px-2 py-0.5 text-[10px] text-slate-400">
          <span>⬡</span>
          <span>{objectCount}</span>
        </div>
      )}
    </Link>
  );
}
