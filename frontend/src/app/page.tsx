import Link from 'next/link';

export default function Home() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0f172a] px-4">
      <div className="w-full max-w-sm text-center">

        {/* Title */}
        <div className="flex flex-col items-center mb-8">
          <div className="flex items-center gap-2 text-lg font-semibold text-white">
            <div className="h-5 w-5 bg-sky-500 rounded-sm" />
            <span>Blender Collab</span>
          </div>

          <p className="mt-2 text-sm text-slate-400">
            A lightweight Blender collaboration system.
          </p>
        </div>

        {/* Buttons */}
        <div className="flex flex-col gap-3">
          <Link
            href="/login"
            className="w-full rounded-lg bg-sky-600 py-2 text-sm font-semibold text-white hover:bg-sky-500"
          >
            Log In
          </Link>

          <Link
            href="/signup"
            className="w-full rounded-lg bg-sky-600 py-2 text-sm font-semibold text-white hover:bg-sky-500"
          >
            Sign Up
          </Link>
        </div>

      </div>
    </div>
  );
}
