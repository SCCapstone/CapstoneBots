"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";
import ObjectTypeIcon from "@/components/ObjectTypeIcon";
import type {
  Commit,
  BlenderObject,
  ObjectDiffEntry,
} from "@/lib/projectsApi";
import {
  fetchCommits,
  fetchCommitObjects,
  fetchObjectDownloadUrl,
  computeObjectDiff,
} from "@/lib/projectsApi";

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  added: { label: "+", color: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/30" },
  modified: { label: "M", color: "text-amber-400", bg: "bg-amber-500/10 border-amber-500/30" },
  deleted: { label: "−", color: "text-red-400", bg: "bg-red-500/10 border-red-500/30" },
  unchanged: { label: "=", color: "text-slate-500", bg: "bg-slate-500/5 border-slate-700" },
};

export default function CommitDetailPage() {
  const params = useParams<{ projectId: string; commitId: string }>();
  const { projectId, commitId } = params;
  const { token } = useAuth();

  const [commit, setCommit] = useState<Commit | null>(null);
  const [objects, setObjects] = useState<BlenderObject[]>([]);
  const [parentObjects, setParentObjects] = useState<BlenderObject[]>([]);
  const [diffEntries, setDiffEntries] = useState<ObjectDiffEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Filter state
  const [showUnchanged, setShowUnchanged] = useState(false);

  useEffect(() => {
    if (!token || !projectId || !commitId) return;

    const load = async () => {
      setLoading(true);
      setError("");
      try {
        // Fetch commit objects
        const objs = await fetchCommitObjects(token, projectId, commitId);
        setObjects(objs);

        // Find the commit metadata from the commits list
        const allCommits = await fetchCommits(token, projectId, "main");
        const thisCommit = allCommits.find((c) => c.commit_id === commitId);
        setCommit(thisCommit || null);

        // If there's a parent commit, fetch its objects for diff
        if (thisCommit?.parent_commit_id) {
          try {
            const parentObjs = await fetchCommitObjects(
              token,
              projectId,
              thisCommit.parent_commit_id
            );
            setParentObjects(parentObjs);
            setDiffEntries(computeObjectDiff(objs, parentObjs));
          } catch {
            // Parent commit objects may not be accessible
            setParentObjects([]);
            setDiffEntries([]);
          }
        } else {
          // First commit — all objects are "added"
          setParentObjects([]);
          setDiffEntries(
            objs.map((o) => ({
              object_name: o.object_name,
              object_type: o.object_type,
              status: "added" as const,
              blob_hash: o.blob_hash,
            }))
          );
        }
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : "Failed to load commit.";
        setError(message);
      } finally {
        setLoading(false);
      }
    };

    load();
  }, [token, projectId, commitId]);

  const handleDownload = async (path: string) => {
    if (!token) return;
    try {
      const data = await fetchObjectDownloadUrl(token, projectId, path);
      if (data.url) window.open(data.url, "_blank");
    } catch { }
  };

  // Build a map of objects by name for quick lookup
  const objectsByName = new Map<string, BlenderObject>();
  for (const obj of objects) {
    objectsByName.set(obj.object_name, obj);
  }

  // Stats
  const changedCount = diffEntries.filter((e) => e.status !== "unchanged").length;
  const addedCount = diffEntries.filter((e) => e.status === "added").length;
  const modifiedCount = diffEntries.filter((e) => e.status === "modified").length;
  const deletedCount = diffEntries.filter((e) => e.status === "deleted").length;

  const visibleEntries = showUnchanged
    ? diffEntries
    : diffEntries.filter((e) => e.status !== "unchanged");

  const shortHash = commit?.commit_hash?.slice(0, 10) || commitId.slice(0, 10);
  const commitDate = commit?.committed_at
    ? new Date(commit.committed_at).toLocaleString()
    : "";

  return (
    <div className="min-h-screen bg-[#0f172a] px-4 py-12">
      {/* Back Button */}
      <div className="absolute left-4 top-4">
        <Link
          href={`/projects/${projectId}`}
          className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-300 transition hover:border-sky-500 hover:text-sky-200"
        >
          ← Back to Project
        </Link>
      </div>

      <div className="mx-auto max-w-5xl pt-6">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="text-sm text-slate-400">Loading commit details...</div>
          </div>
        ) : error ? (
          <div className="flex items-center justify-center py-20">
            <div className="text-sm text-red-400">{error}</div>
          </div>
        ) : (
          <div className="space-y-5">
            {/* Commit Header */}
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
              <div className="flex items-start justify-between">
                <div>
                  <h1 className="text-lg font-semibold text-white">
                    {commit?.commit_message || "(no message)"}
                  </h1>
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-slate-400">
                    <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-[10px] text-slate-300">
                      {shortHash}
                    </span>
                    {commitDate && <span>{commitDate}</span>}
                    {commit?.parent_commit_id && (
                      <Link
                        href={`/projects/${projectId}/${commit.parent_commit_id}`}
                        className="text-sky-400 transition hover:text-sky-300"
                      >
                        parent: {commit.parent_commit_id.slice(0, 8)}…
                      </Link>
                    )}
                    {commit?.merge_commit && (
                      <span className="rounded-full border border-violet-500/30 bg-violet-500/10 px-2 py-0.5 text-[9px] font-medium text-violet-300">
                        MERGE
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1.5 rounded-full border border-slate-700 bg-slate-800/60 px-2.5 py-1 text-[10px] text-slate-400">
                  <span>⬡</span>
                  <span>{objects.length} objects</span>
                </div>
              </div>
            </div>

            {/* Diff Stats Bar */}
            {diffEntries.length > 0 && (
              <div className="flex items-center gap-3 text-[11px]">
                <span className="text-slate-400">Changes:</span>
                {addedCount > 0 && (
                  <span className="flex items-center gap-1 text-emerald-400">
                    <span className="font-bold">+{addedCount}</span> added
                  </span>
                )}
                {modifiedCount > 0 && (
                  <span className="flex items-center gap-1 text-amber-400">
                    <span className="font-bold">~{modifiedCount}</span> modified
                  </span>
                )}
                {deletedCount > 0 && (
                  <span className="flex items-center gap-1 text-red-400">
                    <span className="font-bold">−{deletedCount}</span> deleted
                  </span>
                )}
                {diffEntries.length - changedCount > 0 && (
                  <button
                    type="button"
                    onClick={() => setShowUnchanged(!showUnchanged)}
                    className="ml-auto rounded border border-slate-700 px-2 py-0.5 text-[10px] text-slate-400 transition hover:border-slate-500 hover:text-slate-300"
                  >
                    {showUnchanged ? "Hide" : "Show"} {diffEntries.length - changedCount} unchanged
                  </button>
                )}
              </div>
            )}

            {/* Objects Table */}
            <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60 text-xs">
              <div className="grid grid-cols-[auto_1fr_auto_1fr_auto] border-b border-slate-800 bg-slate-950 px-4 py-2 text-[11px] font-medium text-slate-400">
                <div className="w-8 text-center">Δ</div>
                <div className="pl-2 text-left">OBJECT</div>
                <div className="px-4 text-left">TYPE</div>
                <div className="text-left">BLOB HASH</div>
                <div className="text-right">ACTIONS</div>
              </div>
              <div className="divide-y divide-slate-800/50">
                {visibleEntries.length === 0 ? (
                  <div className="px-4 py-4 text-center text-xs text-slate-500">
                    No changes in this commit.
                  </div>
                ) : (
                  visibleEntries.map((entry) => {
                    const config = STATUS_CONFIG[entry.status];
                    const obj = objectsByName.get(entry.object_name);

                    return (
                      <div
                        key={entry.object_name}
                        className={`grid grid-cols-[auto_1fr_auto_1fr_auto] items-center border-l-2 px-4 py-2.5 transition hover:bg-slate-900/80 ${
                          entry.status === "added"
                            ? "border-l-emerald-500/50"
                            : entry.status === "modified"
                            ? "border-l-amber-500/50"
                            : entry.status === "deleted"
                            ? "border-l-red-500/50"
                            : "border-l-transparent"
                        }`}
                      >
                        {/* Status indicator */}
                        <div className="flex w-8 items-center justify-center">
                          <span
                            className={`flex h-5 w-5 items-center justify-center rounded text-[10px] font-bold ${config.color} border ${config.bg}`}
                          >
                            {config.label}
                          </span>
                        </div>

                        {/* Object name */}
                        <div className={`pl-2 font-medium ${entry.status === "deleted" ? "text-slate-500 line-through" : "text-slate-100"}`}>
                          {entry.object_name}
                        </div>

                        {/* Type badge */}
                        <div className="px-4">
                          <ObjectTypeIcon objectType={entry.object_type} showLabel />
                        </div>

                        {/* Blob hash */}
                        <div className="font-mono text-[10px] text-slate-500" title={entry.blob_hash}>
                          {entry.blob_hash.slice(0, 12)}…
                          {entry.parent_blob_hash && (
                            <span className="ml-1 text-slate-600">
                              ← {entry.parent_blob_hash.slice(0, 8)}…
                            </span>
                          )}
                        </div>

                        {/* Actions */}
                        <div className="flex items-center gap-1 justify-end">
                          {obj && entry.status !== "deleted" && (
                            <>
                              <button
                                type="button"
                                onClick={() => handleDownload(obj.json_data_path)}
                                className="rounded border border-sky-500/40 px-2 py-0.5 text-[10px] text-sky-300 transition hover:bg-sky-500/10"
                                title="Download JSON metadata"
                              >
                                JSON
                              </button>
                              {obj.mesh_data_path && (
                                <button
                                  type="button"
                                  onClick={() => handleDownload(obj.mesh_data_path!)}
                                  className="rounded border border-emerald-500/40 px-2 py-0.5 text-[10px] text-emerald-300 transition hover:bg-emerald-500/10"
                                  title="Download mesh binary"
                                >
                                  Mesh
                                </button>
                              )}
                            </>
                          )}
                          {entry.status === "deleted" && (
                            <span className="text-[10px] text-slate-600">removed</span>
                          )}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
