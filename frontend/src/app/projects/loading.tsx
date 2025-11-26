export default function LoadingProjects() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0f172a]">
      <div className="flex flex-col items-center gap-2">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-sky-500 border-t-transparent"></div>
        <p className="text-xs text-slate-400">Loading projects...</p>
      </div>
    </div>
  );
}
