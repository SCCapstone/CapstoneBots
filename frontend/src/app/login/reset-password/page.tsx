import Link from "next/link";
import ResetPasswordForm from "./ResetPasswordForm";

export default function ResetPasswordPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0f172a] px-4">
      {/* Back */}
      <div className="absolute left-4 top-4">
        <Link
          href="/login"
          className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:border-sky-500 hover:text-sky-200 transition"
        >
          ← Back to Login
        </Link>
      </div>

      <div className="w-full max-w-sm text-center">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="flex items-center gap-2 text-lg font-semibold text-white">
            <div className="h-5 w-5 bg-sky-500 rounded-sm" />
            <span>Blender Collab</span>
          </div>
          <p className="mt-1 text-sm text-slate-400">Choose a new password</p>
        </div>

        <ResetPasswordForm />
      </div>
    </div>
  );
}

