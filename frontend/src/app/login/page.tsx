"use client";

import { useState, FormEvent, useEffect } from "react";
import { useRouter } from "next/navigation";
import { loginApi } from "@/lib/authApi";
import { useAuth } from "@/components/AuthProvider";
import Link from "next/link";

export default function LoginPage() {
  const router = useRouter();
  const { login, isAuthenticated, hydrated } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // ⬇ Prevent login page flash
  useEffect(() => {
    if (hydrated && isAuthenticated) {
      router.replace("/projects");
    }
  }, [hydrated, isAuthenticated, router]);

  // ⬇ Show nothing until auth state is ready
  if (!hydrated) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#0f172a] text-slate-400">
        Loading...
      </div>
    );
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await loginApi(email, password);
      login(res.access_token);
      router.replace("/projects");
    } catch {
      setError("Invalid email or password.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0f172a] px-4">
      {/* Back Button */}
      <div className="absolute left-4 top-4">
        <Link
          href="/"
          className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:border-sky-500 hover:text-sky-200 transition"
        >
          ← Back to Home
        </Link>
      </div>
      <div className="w-full max-w-sm text-center">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="flex items-center gap-2 text-lg font-semibold text-white">
            <div className="h-5 w-5 bg-sky-500 rounded-sm" />
            <span>Blender Collab</span>
          </div>
          <p className="mt-1 text-sm text-slate-400">
            Log in to your account
          </p>
        </div>

        {/* Error */}
        {error && (
          <p className="mb-3 text-xs text-red-400">{error}</p>
        )}

        {/* Form */}
        <form
          onSubmit={handleSubmit}
          className="space-y-4 text-left"
          suppressHydrationWarning
        >
          <div>
            <label className="block text-xs text-slate-300 mb-1">
              Email
            </label>
            <input
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-sky-500"
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block text-xs text-slate-300">
                Password
              </label>
              <button
                type="button"
                onClick={() => router.push("/login/forgot-password")}
                className="text-xs text-sky-400 hover:text-sky-300"
              >
                Forgot password?
              </button>
            </div>

            <input
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-sky-500"
              suppressHydrationWarning
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-sky-600 py-2 text-sm font-semibold text-white hover:bg-sky-500 disabled:opacity-60"
          >
            {loading ? "Logging in..." : "Log In"}
          </button>
        </form>

        <p className="mt-4 text-xs text-slate-500">
          Don’t have an account?{" "}
          <Link
            href="/signup"
            className="text-sky-400 hover:text-sky-300"
          >
            Sign up
          </Link>
        </p>
      </div>
    </div>
  );
}
