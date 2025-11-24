import Link from "next/link";

export default function CommitDetailPlaceholder({
                                                  params,
                                                }: {
  params: { projectId: string; commitId: string };
}) {
  const { projectId, commitId } = params;

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#0f172a] px-4">

      {/* Back Button */}
      <div className="absolute left-4 top-4">
        <Link
          href={`/projects/${projectId}`}
          className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:border-sky-500 hover:text-sky-200 transition"
        >
          ← Back to Project
        </Link>
      </div>

      {/* Content */}
      <div className="w-full max-w-md text-center">
        <h1 className="text-xl font-semibold text-white mb-2">
          Commit: {commitId}
        </h1>
        <p className="text-sm text-slate-400 mb-6">
          Project: {projectId}
        </p>

        <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-6">
          <p className="text-xs text-slate-400">
            Commit details and file previews will appear here.
          </p>
        </div>
      </div>
    </div>
  );
}
