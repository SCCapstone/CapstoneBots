"use client";

import { useState, FormEvent, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { resetPasswordApi } from "@/lib/authApi";

function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");

    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    if (!token) {
      setError("Missing reset token. Please use the link from your email.");
      return;
    }

    setLoading(true);
    try {
      await resetPasswordApi(token, password);
      setSuccess(true);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Something went wrong. The link may have expired.");
      }
    } finally {
      setLoading(false);
    }
  }

  if (!token) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-red-400">
          Invalid reset link. Please request a new one.
        </p>
        <Link
          href="/login/forgot-password"
          className="inline-block rounded-lg bg-slate-800 px-4 py-2 text-sm text-slate-200 hover:bg-slate-700 transition"
        >
          Request New Link
        </Link>
      </div>
    );
  }

  if (success) {
    return (
      <div className="space-y-4">
        <div className="rounded-lg border border-emerald-800 bg-emerald-900/30 p-4 text-sm text-emerald-200">
          Your password has been reset successfully!
        </div>
        <Link
          href="/login"
          className="inline-block rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-500 transition"
        >
          Log In
        </Link>
      </div>
    );
  }

  return (
    <>
      {error && <p className="mb-3 text-xs text-red-400">{error}</p>}

      <form onSubmit={handleSubmit} className="space-y-4 text-left">
        <div>
          <label className="block text-xs text-slate-300 mb-1">
            New Password
          </label>
          <input
            type="password"
            required
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-sky-500"
          />
        </div>

        <div>
          <label className="block text-xs text-slate-300 mb-1">
            Confirm Password
          </label>
          <input
            type="password"
            required
            placeholder="••••••••"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-sky-500"
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-sky-600 py-2 text-sm font-semibold text-white hover:bg-sky-500 disabled:opacity-60"
        >
          {loading ? "Resetting…" : "Reset Password"}
        </button>
      </form>

      <p className="mt-4 text-xs text-slate-500">
        Remember your password?{" "}
        <Link href="/login" className="text-sky-400 hover:text-sky-300">
          Log in
        </Link>
      </p>
    </>
  );
}

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

        <Suspense
          fallback={
            <p className="text-sm text-slate-400">Loading…</p>
          }
        >
          <ResetPasswordForm />
        </Suspense>
      </div>
    </div>
  );
}

