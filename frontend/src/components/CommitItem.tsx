// src/components/CommitItem.tsx
"use client";

import type { Commit } from "@/lib/projectsApi";

type CommitItemProps = {
  commit: Commit;
};

export default function CommitItem({ commit }: CommitItemProps) {
  const date = new Date(commit.committed_at);
  const formatted = isNaN(date.getTime())
    ? commit.committed_at
    : date.toLocaleString();

  const shortHash = commit.commit_hash.slice(0, 7);

  return (
    <div className="flex items-start justify-between rounded-lg border border-slate-800 bg-slate-900/70 px-3 py-2 text-xs hover:border-sky-500/60 hover:bg-slate-900">
      <div className="flex-1 pr-3">
        <p className="font-medium text-slate-100">
          {commit.commit_message || "(no message)"}
        </p>
        <p className="mt-1 text-[11px] text-slate-500">
          <span className="inline-flex items-center gap-1">
            <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-300">
              {shortHash}
            </span>
            <span>· {formatted}</span>
          </span>
        </p>
      </div>
    </div>
  );
}
