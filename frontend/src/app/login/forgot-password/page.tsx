"use client";

import { useState, FormEvent } from "react";
import Link from "next/link";
import { forgotPasswordApi } from "@/lib/authApi";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      await forgotPasswordApi(email);
      setSent(true);
    } catch {
      setError("Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

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
          <p className="mt-1 text-sm text-slate-400">Reset your password</p>
        </div>

        {sent ? (
          <div className="space-y-4">
            <div className="rounded-lg border border-sky-800 bg-sky-900/30 p-4 text-sm text-sky-200">
              If an account with that email exists, we&apos;ve sent a password reset
              link. Please check your inbox (and spam folder).
            </div>
            <Link
              href="/login"
              className="inline-block rounded-lg bg-slate-800 px-4 py-2 text-sm text-slate-200 hover:bg-slate-700 transition"
            >
              Back to Login
            </Link>
          </div>
        ) : (
          <>
            {error && <p className="mb-3 text-xs text-red-400">{error}</p>}

            <form onSubmit={handleSubmit} className="space-y-4 text-left">
              <div>
                <label className="block text-xs text-slate-300 mb-1">
                  Email address
                </label>
                <input
                  type="email"
                  required
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-sky-500"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full rounded-lg bg-sky-600 py-2 text-sm font-semibold text-white hover:bg-sky-500 disabled:opacity-60"
              >
                {loading ? "Sending…" : "Send Reset Link"}
              </button>
            </form>

            <p className="mt-4 text-xs text-slate-500">
              Remember your password?{" "}
              <Link
                href="/login"
                className="text-sky-400 hover:text-sky-300"
              >
                Log in
              </Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
}

