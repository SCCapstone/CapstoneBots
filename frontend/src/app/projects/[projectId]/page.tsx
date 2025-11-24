import Link from "next/link";

export default function ProjectPagePlaceholder({
                                                 params,
                                               }: {
  params: { projectId: string };
}) {
  const { projectId } = params;

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#0f172a] px-4">

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
        <h1 className="text-xl font-semibold text-white mb-2">
          Project: {projectId}
        </h1>

        <p className="text-sm text-slate-400 mb-6">
          Commit list will appear here (not implemented yet).
        </p>

        <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-6">
          <p className="text-xs text-slate-400">
            This page will show commit history for this project.
          </p>
        </div>
      </div>
    </div>
  );
}
